"""Helpers for resolving PortAudio device settings."""

from __future__ import annotations

from typing import Literal, Optional

import sounddevice as sd

DeviceKind = Literal["input", "output"]


class AudioDeviceError(ValueError):
    """Raised when a configured audio device cannot be resolved."""


def resolve_device(configured: Optional[str | int], kind: DeviceKind) -> Optional[int]:
    """Resolve an env/config device value to a PortAudio index.

    ``sounddevice`` accepts strings directly, but resolving here lets us validate
    the direction, support numeric strings, and log the exact device in use.
    """
    if configured is None:
        return _default_device_index(kind)
    if isinstance(configured, int):
        return _validate_device_index(configured, kind)

    value = configured.strip()
    if not value:
        return _default_device_index(kind)
    try:
        index = int(value)
    except ValueError:
        index = None
    if index is not None:
        return _validate_device_index(index, kind)

    needle = value.casefold()
    devices = list(sd.query_devices())
    matches = [
        index
        for index, device in enumerate(devices)
        if _supports_kind(device, kind)
        and needle in str(device.get("name", "")).casefold()
    ]
    exact = [
        index
        for index in matches
        if str(devices[index].get("name", "")).casefold() == needle
    ]
    if exact:
        return exact[0]
    if matches:
        return matches[0]

    available = ", ".join(_available_devices(kind)[:20])
    raise AudioDeviceError(
        f"No {kind} audio device matches {configured!r}. "
        f"Available {kind} devices: {available}"
    )


def describe_device(device: Optional[int], kind: DeviceKind) -> str:
    """Return a compact human-readable label for logs."""
    if device is None:
        return "system default"
    try:
        info = sd.query_devices(device, kind)
    except Exception:
        return str(device)
    return f"[{device}] {info['name']}"


def _default_device_index(kind: DeviceKind) -> Optional[int]:
    try:
        default = sd.default.device
    except Exception:
        return None

    slot = 0 if kind == "input" else 1
    if isinstance(default, int):
        index = default
    else:
        try:
            index = default[slot]
        except (TypeError, IndexError, KeyError):
            return None

    if index is None or int(index) < 0:
        return None
    return _validate_device_index(int(index), kind)


def _validate_device_index(index: int, kind: DeviceKind) -> int:
    try:
        device = sd.query_devices(index)
    except Exception as e:
        raise AudioDeviceError(f"No audio device exists at index {index}") from e
    if not _supports_kind(device, kind):
        raise AudioDeviceError(f"Audio device [{index}] is not an {kind} device")
    return index


def _supports_kind(device: dict, kind: DeviceKind) -> bool:
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    return int(device.get(key, 0) or 0) > 0


def _available_devices(kind: DeviceKind) -> list[str]:
    devices = list(sd.query_devices())
    return [
        f"[{index}] {device.get('name', '')}"
        for index, device in enumerate(devices)
        if _supports_kind(device, kind)
    ]
