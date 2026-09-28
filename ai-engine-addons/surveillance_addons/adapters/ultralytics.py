"""Optional Ultralytics adapter hooks.

Keep runtime-specific imports inside methods so the add-on package remains importable
when model dependencies are not installed.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from . import __name__ as _package_name

class UltralyticsTaskAdapter:
    def __init__(self, model_path: Path, task: str) -> None:
        self.model_path = model_path
        self.task = task
        self._model: Any = None

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        from ultralytics import YOLO
        self._model = YOLO(str(self.model_path), task=self.task)

