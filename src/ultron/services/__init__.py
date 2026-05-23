"""Dependency-injection primitives for ultron's service-shaped subsystems.

Pattern lineage attributed in ``THIRD_PARTY_NOTICES.md``.

The OpenHands V1 server uses an :class:`Injector[T]` ABC to lift
service construction out of caller code: every service (event store,
sandbox manager, conversation service, secrets store, etc.) has its
own injector subclass that knows how to build its concrete given a
``State`` blob + an optional ``Request``. The app server then picks
between filesystem / S3 / Google Cloud backends by selecting which
injector to use in ``AppServerConfig``.

Ultron's port is sync (voice-first, single-process, no FastAPI on the
hot path), but the contract is otherwise identical:

* Every service has an ``Injector[T]`` subclass implementing
  ``inject(state) -> T`` (or ``stream(state) -> Iterator[T]`` for
  generators).
* The orchestrator owns one ``InjectorState`` per startup that
  injectors can use to share intermediate state (e.g. the embedder
  used by both the memory and project-index services).
* Hot-swap is just "ask the injector again with a different state
  attribute" -- the gaming-mode engage path can flip
  ``state.mode = 'gaming'`` and the next STT/TTS resolution returns
  the gaming-variant concrete.

Two starter injectors ship: :class:`STTEngineInjector` and
:class:`TTSEngineInjector`. They wrap the existing
:func:`ultron.transcription.make_stt_engine` and
:func:`ultron.tts.make_tts_engine` factories so the migration is
purely additive -- the orchestrator's existing engine-construction
code path is untouched until operators opt into the injectors.
"""

from ultron.services.injector import (
    Injector,
    InjectorRegistry,
    InjectorState,
    SingletonInjector,
    StreamInjector,
    get_injector_registry,
    install_default_injectors,
    reset_injector_registry_for_testing,
    set_injector_registry,
)
from ultron.services.engine_injectors import (
    STTEngineInjector,
    TTSEngineInjector,
    build_stt_engine_injector,
    build_tts_engine_injector,
)

__all__ = [
    "Injector",
    "InjectorRegistry",
    "InjectorState",
    "STTEngineInjector",
    "SingletonInjector",
    "StreamInjector",
    "TTSEngineInjector",
    "build_stt_engine_injector",
    "build_tts_engine_injector",
    "get_injector_registry",
    "install_default_injectors",
    "reset_injector_registry_for_testing",
    "set_injector_registry",
]
