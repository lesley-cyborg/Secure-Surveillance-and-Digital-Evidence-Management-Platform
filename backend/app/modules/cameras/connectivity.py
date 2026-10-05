from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse


async def probe_camera_endpoint(
    *,
    ip_address: str,
    protocol: str,
    stream_url: str,
    timeout_seconds: float = 3.0,
) -> tuple[bool, float | None, str]:
    """
    Best-effort reachability probe.
    TCP connect to host:port from stream URL or default protocol port.
    """
    host = ip_address
    protocol_upper = protocol.upper()
    
    # Default ports based on protocol
    port = 554 if protocol_upper == "RTSP" else 80

    parsed = urlparse(stream_url)
    if parsed.hostname:
        host = parsed.hostname
    if parsed.port:
        port = parsed.port
    elif protocol_upper == "HTTPS":
        port = 443
    elif protocol_upper == "ONVIF":
        port = 80  # parsed.port is already falsy here due to the 'elif'

    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_seconds,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return True, latency_ms, f"TCP connect to {host}:{port} succeeded"
        
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, latency_ms, f"Timeout connecting to {host}:{port} after {timeout_seconds}s"
        
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return False, latency_ms, f"TCP connect to {host}:{port} failed: {exc}"