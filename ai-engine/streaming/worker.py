from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import time
import structlog

from streaming.domain import (
    CameraStreamConfig,
    StreamFrame,
    StreamRuntimeSnapshot,
    StreamState,
)
from streaming.exceptions import (
    FrameQueueClosedError,
    ReconnectAttemptsExhaustedError,
    StreamSourceError,
    StreamWorkerDisposedError,
)
from streaming.frame_queue import (
    FrameQueueSnapshot,
    LatestFrameQueue,
)
from streaming.frame_sampler import (
    FrameSampler,
    FrameSamplerSnapshot,
)
from streaming.reconnect_policy import (
    ReconnectDecision,
    ReconnectPolicy,
    ReconnectPolicySnapshot,
)
from streaming.source import StreamSource

from integrations.backend.heartbeat_client import HeartbeatClient

logger = structlog.get_logger(__name__)


type FrameProcessingFunction = Callable[
    [StreamFrame, float],
    Awaitable[object],
]

type DetectionResultHandler = Callable[
    [StreamFrame, object],
    Awaitable[None],
]


@dataclass(
    frozen=True,
    slots=True,
)
class ContinuousDetectionWorkerSnapshot:
    """Combined worker, queue, sampler and retry state."""

    runtime: StreamRuntimeSnapshot
    queue: FrameQueueSnapshot
    sampler: FrameSamplerSnapshot
    reconnect: ReconnectPolicySnapshot

    running: bool
    disposed: bool


class ContinuousDetectionWorker:
    """Cancellation-safe continuous camera detection job.

    Capture and detection run independently:

    - Capture reads frames through a blocking StreamSource using
      asyncio.to_thread().
    - FrameSampler limits publication to the configured target FPS.
    - LatestFrameQueue applies bounded backpressure by discarding
      stale frames.
    - The detection loop processes only retained frames.
    - Stream failures invoke the configured ReconnectPolicy.
    """

    def __init__(
        self,
        *,
        config: CameraStreamConfig,
        source: StreamSource,
        sampler: FrameSampler,
        frame_queue: LatestFrameQueue,
        reconnect_policy: ReconnectPolicy,
        process_frame: FrameProcessingFunction,
        result_handler: DetectionResultHandler | None = None,
        heartbeat_client: HeartbeatClient | None = None,
    ) -> None:
        if source.config.camera_id != config.camera_id:
            raise ValueError("source camera_id does not match worker configuration")

        if sampler.target_fps != config.target_fps:
            raise ValueError("sampler target_fps does not match worker configuration")

        if frame_queue.capacity != config.queue_capacity:
            raise ValueError("frame queue capacity does not match worker configuration")

        self._config = config
        self._source = source
        self._sampler = sampler
        self._frame_queue = frame_queue
        self._reconnect_policy = reconnect_policy
        self._process_frame = process_frame
        self._result_handler = result_handler
        self._heartbeat_client = heartbeat_client

        self._task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._metrics_lock = asyncio.Lock()

        self._disposed = False
        self._state = StreamState.STOPPED if config.enabled else StreamState.DISABLED

        self._connected_at: datetime | None = None
        self._last_frame_at: datetime | None = None
        self._last_error: str | None = None

        self._frames_received = 0
        self._frames_published = 0
        self._frames_dropped = 0
        self._frames_processed = 0
        self._detection_failures = 0
        self._reconnect_attempts = 0
        
        # Heartbeat tracking
        self._last_heartbeat_at: datetime | None = None
        self._heartbeat_interval_seconds = 30  # Send heartbeat every 30 seconds

    @property
    def config(self) -> CameraStreamConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        task = self._task

        return task is not None and not task.done()

    @property
    def disposed(self) -> bool:
        return self._disposed

    async def start(self) -> None:
        """Start capture and detection tasks.

        Repeated calls while running are idempotent.
        """

        async with self._lifecycle_lock:
            if self._disposed:
                raise StreamWorkerDisposedError(
                    f"Camera worker {self._config.camera_id!r} has been disposed"
                )

            if not self._config.enabled:
                await self._set_state(StreamState.DISABLED)
                return

            if self.is_running:
                return

            await self._frame_queue.clear()

            self._sampler.reset_schedule()
            self._reconnect_policy.reset()

            await self._set_state(StreamState.CONNECTING)
            await self._clear_last_error()

            self._task = asyncio.create_task(
                self._run(),
                name=(f"continuous-detection:{self._config.camera_id}"),
            )

            logger.info(
                "camera_worker_started",
                camera_id=self._config.camera_id,
                source_uri=(self._config.redacted_source_uri),
                target_fps=self._config.target_fps,
                queue_capacity=(self._config.queue_capacity),
            )

    async def stop(self) -> None:
        """Cancel the worker and release its camera source."""

        async with self._lifecycle_lock:
            task = self._task

            if task is None:
                if not self._disposed:
                    await self._set_state(StreamState.STOPPED)
                return

            if task.done():
                self._task = None

                if not self._disposed and self._state is not StreamState.FAILED:
                    await self._set_state(StreamState.STOPPED)

                return

            await self._set_state(StreamState.STOPPING)

            task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        async with self._lifecycle_lock:
            if self._task is task:
                self._task = None

            if not self._disposed and self._state is not StreamState.FAILED:
                await self._set_state(StreamState.STOPPED)

        logger.info(
            "camera_worker_stopped",
            camera_id=self._config.camera_id,
        )

    async def dispose(self) -> None:
        """Permanently stop the worker and close its queue."""

        await self.stop()

        async with self._lifecycle_lock:
            if self._disposed:
                return

            self._disposed = True

        await self._frame_queue.close(discard_pending=True)
        
        # Send final OFFLINE heartbeat and close client
        if self._heartbeat_client:
            await asyncio.to_thread(
                self._heartbeat_client.send, 
                "OFFLINE", 
                "Worker disposed"
            )
            await asyncio.to_thread(self._heartbeat_client.close)

        logger.info(
            "camera_worker_disposed",
            camera_id=self._config.camera_id,
        )

    async def wait(self) -> None:
        """Wait for the current worker task to finish."""

        task = self._task

        if task is None:
            return

        await asyncio.shield(task)

    async def snapshot(
        self,
    ) -> ContinuousDetectionWorkerSnapshot:
        """Return an immutable worker status snapshot."""

        async with self._metrics_lock:
            runtime = StreamRuntimeSnapshot(
                camera_id=self._config.camera_id,
                state=self._state,
                updated_at=datetime.now(UTC),
                connected_at=self._connected_at,
                last_frame_at=self._last_frame_at,
                frames_received=(self._frames_received),
                frames_published=(self._frames_published),
                frames_dropped=(self._frames_dropped),
                frames_processed=(self._frames_processed),
                detection_failures=(self._detection_failures),
                reconnect_attempts=(self._reconnect_attempts),
                last_error=self._last_error,
            )

        return ContinuousDetectionWorkerSnapshot(
            runtime=runtime,
            queue=await self._frame_queue.snapshot(),
            sampler=self._sampler.snapshot(),
            reconnect=(self._reconnect_policy.snapshot()),
            running=self.is_running,
            disposed=self._disposed,
        )

    async def _run(self) -> None:
        capture_task = asyncio.create_task(
            self._capture_loop(),
            name=(f"camera-capture:{self._config.camera_id}"),
        )
        detection_task = asyncio.create_task(
            self._detection_loop(),
            name=(f"camera-detection:{self._config.camera_id}"),
        )

        tasks = (
            capture_task,
            detection_task,
        )

        try:
            done, _ = await asyncio.wait(
                tasks,
                return_when=(asyncio.FIRST_COMPLETED),
            )

            for completed_task in done:
                exception = completed_task.exception()

                if exception is not None:
                    raise exception
        except asyncio.CancelledError:
            raise
        except ReconnectAttemptsExhaustedError as exception:
            await self._record_terminal_failure(exception)

            logger.error(
                "camera_reconnect_attempts_exhausted",
                camera_id=self._config.camera_id,
                error=str(exception),
            )
        except Exception as exception:
            await self._record_terminal_failure(exception)

            logger.exception(
                "camera_worker_failed",
                camera_id=self._config.camera_id,
                error_type=(type(exception).__name__),
            )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            await self._close_source_safely()

    async def _capture_loop(self) -> None:
        consecutive_read_failures = 0

        while True:
            try:
                await self._set_state(StreamState.CONNECTING)

                await asyncio.to_thread(self._source.open)

                self._sampler.reset_schedule()

                consecutive_read_failures = 0
                connection_confirmed = False

                await self._record_connected()

                logger.info(
                    "camera_stream_connected",
                    camera_id=self._config.camera_id,
                    source_uri=(self._config.redacted_source_uri),
                )

                while True:
                    try:
                        frame = await asyncio.to_thread(self._source.read)
                    except asyncio.CancelledError:
                        raise
                    except StreamSourceError as exception:
                        consecutive_read_failures += 1

                        await self._record_error(exception)

                        logger.warning(
                            "camera_frame_read_failed",
                            camera_id=(self._config.camera_id),
                            consecutive_failures=(consecutive_read_failures),
                            maximum_failures=(
                                self._config.maximum_consecutive_read_failures
                            ),
                            error_type=(type(exception).__name__),
                        )

                        if (
                            consecutive_read_failures
                            >= self._config.maximum_consecutive_read_failures
                        ):
                            raise

                        continue

                    consecutive_read_failures = 0

                    if not connection_confirmed:
                        # Opening the capture does not prove the stream
                        # is healthy. Reset reconnect backoff only after
                        # receiving the first valid frame.
                        self._reconnect_policy.record_success()
                        connection_confirmed = True

                    await self._record_frame_received(frame)

                    # Send periodic heartbeat while streaming
                    await self._send_periodic_heartbeat()

                    if not self._sampler.should_sample():
                        continue

                    publish_result = await self._frame_queue.publish(frame)

                    await self._record_frame_published(
                        dropped_frames=(publish_result.dropped_frames)
                    )

            except asyncio.CancelledError:
                raise
            except StreamSourceError as exception:
                await self._record_error(exception)

                await self._close_source_safely()

                decision = await self._schedule_reconnect()

                logger.warning(
                    "camera_reconnect_scheduled",
                    camera_id=self._config.camera_id,
                    attempt_number=(decision.attempt_number),
                    delay_seconds=(decision.delay_seconds),
                    remaining_attempts=(decision.remaining_attempts),
                    error_type=(type(exception).__name__),
                )

    async def _detection_loop(self) -> None:
        while True:
            try:
                frame = await self._frame_queue.get()
            except asyncio.CancelledError:
                raise
            except FrameQueueClosedError:
                return

            try:
                result = await self._process_frame(
                    frame,
                    self._config.confidence_threshold,
                )

                if self._result_handler is not None:
                    await self._result_handler(
                        frame,
                        result,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exception:
                await self._record_detection_failure(exception)

                logger.exception(
                    "stream_frame_detection_failed",
                    camera_id=(self._config.camera_id),
                    sequence_number=(frame.sequence_number),
                    error_type=(type(exception).__name__),
                )

                continue

            await self._record_frame_processed()

    async def _schedule_reconnect(
        self,
    ) -> ReconnectDecision:
        await self._set_state(StreamState.RECONNECTING)
        
        # Send DEGRADED heartbeat during reconnect
        if self._heartbeat_client:
            await asyncio.to_thread(
                self._heartbeat_client.send,
                "DEGRADED",
                "Stream disconnected, attempting reconnect"
            )

        decision = await self._reconnect_policy.wait()

        async with self._metrics_lock:
            self._reconnect_attempts += 1

        return decision

    async def _close_source_safely(self) -> None:
        try:
            await asyncio.to_thread(self._source.close)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "camera_source_close_failed",
                camera_id=self._config.camera_id,
            )

    async def _set_state(
        self,
        state: StreamState,
    ) -> None:
        async with self._metrics_lock:
            self._state = state

    async def _clear_last_error(self) -> None:
        async with self._metrics_lock:
            self._last_error = None

    async def _record_connected(self) -> None:
        connected_at = datetime.now(UTC)

        async with self._metrics_lock:
            self._state = StreamState.CONNECTED
            self._connected_at = connected_at
            self._last_error = None
            
        # Send ONLINE heartbeat when connected
        if self._heartbeat_client:
            await asyncio.to_thread(
                self._heartbeat_client.send,
                "ONLINE",
                "Stream connected and receiving frames"
            )

    async def _record_frame_received(
        self,
        frame: StreamFrame,
    ) -> None:
        async with self._metrics_lock:
            self._frames_received += 1
            self._last_frame_at = frame.received_at

    async def _record_frame_published(
        self,
        *,
        dropped_frames: int,
    ) -> None:
        async with self._metrics_lock:
            self._frames_published += 1
            self._frames_dropped += dropped_frames

    async def _record_frame_processed(
        self,
    ) -> None:
        async with self._metrics_lock:
            self._frames_processed += 1

    async def _record_detection_failure(
        self,
        exception: Exception,
    ) -> None:
        async with self._metrics_lock:
            self._detection_failures += 1
            self._last_error = str(exception)

    async def _record_error(
        self,
        exception: Exception,
    ) -> None:
        async with self._metrics_lock:
            self._last_error = str(exception)
            
        # Send DEGRADED heartbeat on error
        if self._heartbeat_client:
            await asyncio.to_thread(
                self._heartbeat_client.send,
                "DEGRADED",
                f"Stream error: {str(exception)}"
            )

    async def _record_terminal_failure(
        self,
        exception: BaseException,
    ) -> None:
        async with self._metrics_lock:
            self._state = StreamState.FAILED
            self._last_error = str(exception)
            
        # Send OFFLINE heartbeat on terminal failure
        if self._heartbeat_client:
            await asyncio.to_thread(
                self._heartbeat_client.send,
                "OFFLINE",
                f"Terminal failure: {str(exception)}"
            )
            
    async def _send_periodic_heartbeat(self) -> None:
        """Send heartbeat every N seconds while streaming."""
        if not self._heartbeat_client:
            return
            
        now = datetime.now(UTC)
        
        async with self._metrics_lock:
            if self._last_heartbeat_at is None:
                # First heartbeat after connection
                self._last_heartbeat_at = now
                return
                
            elapsed = (now - self._last_heartbeat_at).total_seconds()
            if elapsed >= self._heartbeat_interval_seconds:
                self._last_heartbeat_at = now
                should_send = True
            else:
                should_send = False
        
        if should_send:
            await asyncio.to_thread(
                self._heartbeat_client.send,
                "ONLINE",
                f"Streaming normally (processed {self._frames_processed} frames)"
            )