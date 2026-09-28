from __future__ import annotations

import importlib as stdlib_importlib
from types import SimpleNamespace

import pytest

from detection.device import is_cuda_available, select_device
from detection.exceptions import (
    DeviceUnavailableError,
)
from detection.schemas import DeviceType


def test_cpu_device_is_always_available() -> None:
    selected = select_device(
        DeviceType.CPU,
        cuda_probe=lambda: False,
    )

    assert selected is DeviceType.CPU


def test_auto_falls_back_to_cpu() -> None:
    selected = select_device(
        DeviceType.AUTO,
        cuda_probe=lambda: False,
    )

    assert selected is DeviceType.CPU


def test_auto_selects_cuda_when_available() -> None:
    selected = select_device(
        DeviceType.AUTO,
        cuda_probe=lambda: True,
    )

    assert selected is DeviceType.CUDA


def test_explicit_cuda_fails_when_unavailable() -> None:
    with pytest.raises(DeviceUnavailableError):
        select_device(
            DeviceType.CUDA,
            cuda_probe=lambda: False,
        )


def test_cuda_probe_detects_installed_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import(name: str) -> object:
        if name != "torch":
            return stdlib_importlib.import_module(name)
        return SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True),
        )
    monkeypatch.setattr(
        stdlib_importlib,
        "import_module",
        fake_import
    )
    assert is_cuda_available() is True


def test_cuda_probe_degrades_when_runtime_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> bool:
        raise RuntimeError("CUDA runtime is unavailable")

    def fake_import(name: str) -> object:
        if name != "torch":
            return stdlib_importlib.import_module(name)
        return SimpleNamespace(
            cuda=SimpleNamespace(is_available=unavailable),
        )

    monkeypatch.setattr(
        stdlib_importlib,
        "import_module",
        fake_import
    )

    assert is_cuda_available() is False
    assert (
        select_device(DeviceType.AUTO, cuda_probe=is_cuda_available)
        is DeviceType.CPU
    )


def test_cuda_probe_degrades_when_runtime_import_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(name: str) -> object:
        if name == "torch":
            raise OSError("CUDA runtime libraries are unavailable")
        return stdlib_importlib.import_module(name)

    monkeypatch.setattr(stdlib_importlib, "import_module", unavailable)

    assert is_cuda_available() is False
    with pytest.raises(DeviceUnavailableError):
        select_device(DeviceType.CUDA, cuda_probe=is_cuda_available)
