from __future__ import annotations
from collections import deque
from time import monotonic
from .contracts import PoseObservation

class PoseConfirmation:
    def __init__(self, required_frames: int=3, expiry_seconds: float=5.0, confidence_threshold: float=0.75):
        if required_frames<1 or expiry_seconds<=0 or not 0<=confidence_threshold<=1: raise ValueError("invalid temporal configuration")
        self.required_frames=required_frames; self.expiry_seconds=expiry_seconds; self.confidence_threshold=confidence_threshold
        self._history: dict[str,tuple[float,deque[str]]]={}
    def update(self, track_id: str, observations: tuple[PoseObservation,...], now: float|None=None) -> tuple[PoseObservation,...]:
        timestamp=monotonic() if now is None else now
        previous=self._history.get(track_id)
        history=previous[1] if previous and timestamp-previous[0] <= self.expiry_seconds else deque(maxlen=self.required_frames)
        result=[]
        for observation in observations:
            if observation.confidence < self.confidence_threshold:
                history.clear()
                result.append(observation.model_copy(update={"confirmed":False}))
                continue
            if history and history[-1] != observation.posture: history.clear()
            history.append(observation.posture)
            confirmed=len(history)==self.required_frames and len(set(history))==1
            result.append(observation.model_copy(update={"confirmed":confirmed}))
        self._history[track_id]=(timestamp,history)
        return tuple(result)
    def reset(self, track_id: str|None=None) -> None:
        if track_id is None: self._history.clear()
        else: self._history.pop(track_id,None)
