"""Local monitor -- tee relay clips to the user's OWN default output device.

Relay / team callouts normally play only to the mic B-bus (so teammates hear
them) and the broadcast mirror (so OBS viewers hear them). The user themselves
never hears their own callouts locally -- there is no path from the relay clip
to the desktop speakers. This module adds that path: it tees the SAME already-
synthesized clip to the user's default output device, in parallel, so the user
hears everything Ultron says.

It reuses :class:`~kenning.audio.broadcast.BroadcastSink` verbatim -- the same
non-blocking, drop-oldest, fail-open daemon tee -- just pointed at a different
device (the user's normal output rather than the OBS capture strip). Normal
conversation already plays on the default device via the speaker path, so the
monitor only needs to cover the relay path.

Gated by ``relay_speech.echo_to_user``, read LIVE per callout (like
``relay_speech.output_device``) so the settings-GUI "Echo to me" toggle
hot-applies on the next callout with no restart. The target device follows
``audio.output_device`` (``None`` -> the system default output), i.e. the very
same device the user hears normal conversation on. When the toggle is off,
``maybe_submit`` is a cheap early return and no output device is ever opened.
"""
from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from kenning.audio.broadcast import BroadcastSink
from kenning.utils.logging import get_logger

logger = get_logger("audio.monitor")

_SINK: Optional[BroadcastSink] = None
_SINK_LOCK = threading.Lock()


def get_monitor_sink() -> BroadcastSink:
    """Return the shared local-monitor sink, creating it on first use."""
    global _SINK
    if _SINK is None:
        with _SINK_LOCK:
            if _SINK is None:
                _SINK = BroadcastSink(name="monitor")
    return _SINK


def _resolve_output_index(out_device) -> Optional[int]:
    """The user's normal output as a concrete index (None -> default)."""
    try:
        from kenning.audio.devices import resolve_device

        return resolve_device(out_device, "output")
    except Exception as e:  # noqa: BLE001
        logger.debug("monitor device resolve failed (%s)", e)
        return None


def maybe_submit(pcm: np.ndarray, sample_rate: int) -> None:
    """Tee one relay clip to the user's default speakers IFF echo_to_user.

    Reads ``relay_speech.echo_to_user`` + ``audio.output_device`` LIVE, so a
    GUI toggle (or device change) hot-applies on the next callout. Lazily
    (re)points the sink at the resolved output device; non-blocking, fail-open.
    A no-op (one config read) when the toggle is off -- the monitor device is
    never opened until echo is actually enabled.
    """
    try:
        from kenning.config import get_config

        cfg = get_config()
        if not bool(getattr(cfg.relay_speech, "echo_to_user", False)):
            return
        # LIVE speaker mute: skip the relay echo on the default speakers (the
        # callout still reaches teammates on B1 + OBS on B3). GUI-toggleable.
        if bool(getattr(cfg.audio, "mute_speakers", False)):
            return
        out_device = getattr(cfg.audio, "output_device", None)
    except Exception as e:  # noqa: BLE001
        logger.debug("monitor maybe_submit: config read failed (%s)", e)
        return
    idx = _resolve_output_index(out_device)
    if idx is None:
        return
    sink = get_monitor_sink()
    if sink._device_spec != idx:                       # noqa: SLF001
        sink.configure(idx)
    sink.submit(pcm, sample_rate)


def cancel_current() -> None:
    """Module-level "stop" hook: abort the monitor's current clip on the user's
    own speakers. No-op when the monitor was never created. Fail-open."""
    sink = _SINK
    if sink is None:
        return
    try:
        sink.cancel_current()
    except Exception:                                  # noqa: BLE001
        pass


def configure_from_config() -> None:
    """Startup pre-warm: arm the monitor to the user's output iff echo_to_user,
    else release it. Runtime toggles are still picked up live by
    :func:`maybe_submit`; this just avoids a first-callout configure hitch and
    releases the device when the feature is off. Fail-open.
    """
    try:
        from kenning.config import get_config

        cfg = get_config()
        on = bool(getattr(cfg.relay_speech, "echo_to_user", False))
        out_device = getattr(cfg.audio, "output_device", None)
    except Exception as e:  # noqa: BLE001
        logger.debug("monitor configure_from_config: config read failed (%s)", e)
        return
    sink = get_monitor_sink()
    if not on:
        sink.configure(None)
        return
    idx = _resolve_output_index(out_device)
    sink.configure(idx)  # None -> stays off, fail-open
