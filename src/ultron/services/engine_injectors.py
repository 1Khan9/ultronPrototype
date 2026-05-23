"""Starter injectors for the STT + TTS engines.

These wrap the existing :func:`ultron.transcription.make_stt_engine` and
:func:`ultron.tts.make_tts_engine` factories so the orchestrator can
migrate to the Injector pattern in one place without touching the
engine construction code itself. The catalog's "gaming-mode hot-swap
as an injector state attribute" is implemented here -- when the
``state.mode`` attribute is set to ``"gaming"``, the injectors return
the gaming variant (Moonshine on CPU + Kokoro on CPU) rather than
the standby variant.

This module imports lazily because the engine factories pull in heavy
deps (kokoro, parakeet, etc.); a registry that only wires the LLM
injector shouldn't pay the audio-stack import cost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ultron.services.injector import Injector, InjectorState

logger = logging.getLogger(__name__)


def _resolve_mode(state: InjectorState | None) -> str:
    """Return the active mode label (``"standby"`` / ``"gaming"`` / custom)."""

    if state is None:
        return "standby"
    return str(state.get("mode", "standby")) or "standby"


@dataclass
class STTEngineInjector(Injector[Any]):
    """Resolve the STT engine for the active state.

    The constructor accepts two optional factory callables -- one for
    standby (default), one for gaming. When the active ``state.mode``
    is ``"gaming"`` the gaming factory wins; otherwise the standby
    factory is used.

    Defaults call :func:`ultron.transcription.make_stt_engine` and let
    the live config decide which engine to construct. To force a
    specific engine regardless of config, pass an explicit factory
    that constructs the engine you want.
    """

    standby_factory: Callable[[InjectorState], Any] | None = None
    gaming_factory: Callable[[InjectorState], Any] | None = None

    def inject(self, state: InjectorState) -> Any:
        mode = _resolve_mode(state)
        if mode == "gaming" and self.gaming_factory is not None:
            try:
                return self.gaming_factory(state)
            except Exception as exc:                              # noqa: BLE001
                logger.warning(
                    "STT gaming factory raised; falling back to standby: %r", exc,
                )
        if self.standby_factory is not None:
            return self.standby_factory(state)
        # Default behaviour: delegate to the existing factory + live config.
        from ultron.transcription import make_stt_engine

        return make_stt_engine()


@dataclass
class TTSEngineInjector(Injector[Any]):
    """Resolve the TTS engine for the active state.

    Same shape as :class:`STTEngineInjector`: standby + gaming factory
    callables; default falls through to :func:`ultron.tts.make_tts_engine`.

    Note: :func:`ultron.tts.make_tts_engine` returns ``(rvc, engine)``;
    the injector preserves that shape so the orchestrator's existing
    call site is byte-identical.
    """

    standby_factory: Callable[[InjectorState], Any] | None = None
    gaming_factory: Callable[[InjectorState], Any] | None = None

    def inject(self, state: InjectorState) -> Any:
        mode = _resolve_mode(state)
        if mode == "gaming" and self.gaming_factory is not None:
            try:
                return self.gaming_factory(state)
            except Exception as exc:                              # noqa: BLE001
                logger.warning(
                    "TTS gaming factory raised; falling back to standby: %r", exc,
                )
        if self.standby_factory is not None:
            return self.standby_factory(state)
        from ultron.tts import make_tts_engine

        return make_tts_engine()


def build_stt_engine_injector(
    *,
    standby_factory: Callable[[InjectorState], Any] | None = None,
    gaming_factory: Callable[[InjectorState], Any] | None = None,
) -> STTEngineInjector:
    """Construct a default :class:`STTEngineInjector`."""

    return STTEngineInjector(
        standby_factory=standby_factory,
        gaming_factory=gaming_factory,
    )


def build_tts_engine_injector(
    *,
    standby_factory: Callable[[InjectorState], Any] | None = None,
    gaming_factory: Callable[[InjectorState], Any] | None = None,
) -> TTSEngineInjector:
    """Construct a default :class:`TTSEngineInjector`."""

    return TTSEngineInjector(
        standby_factory=standby_factory,
        gaming_factory=gaming_factory,
    )
