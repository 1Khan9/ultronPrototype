"""Sync :class:`Injector[T]` ABC + state + registry.

The injector contract is intentionally minimal: each subclass
implements either ``inject(state) -> T`` (single-instance) or
``stream(state) -> Iterator[T]`` (generator yielding one or more
instances, useful for fixtures that need teardown). A
:func:`context` helper wraps either form in a context manager so
callers can ``with injector.context(state) as service:`` regardless
of which method the concrete uses.

The :class:`InjectorRegistry` lets the orchestrator look up the
injector for a given service type at runtime. This is the single
config knob the catalog points at: swap a registry entry to swap an
entire subsystem's implementation. Mode-aware hot-swap (gaming-mode
engage flipping STT from Parakeet to Moonshine) is one keyword on
:class:`InjectorState` away.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Generator,
    Generic,
    Iterator,
    TypeVar,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class InjectorState:
    """Free-form key/value blob shared across nested injections.

    Modelled after the Starlette ``State`` object the OpenHands ABC
    references, but without the framework dependency. Callers set
    attributes (``state.mode = "gaming"``, ``state.session_id = ...``)
    and injectors read them.

    Thread-safe via an internal lock; attribute reads/writes are
    serialised so two callers asking for the same service
    concurrently see consistent state.
    """

    def __init__(self, **initial: Any) -> None:
        # We store entries on a private dict to avoid clashing with
        # ``__getattr__`` semantics; the ``_lock`` lives there too.
        super().__setattr__("_storage", dict(initial))
        super().__setattr__("_lock", threading.RLock())

    def __getattr__(self, name: str) -> Any:
        if name in ("_storage", "_lock"):
            raise AttributeError(name)
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            if name in storage:
                return storage[name]
        raise AttributeError(f"InjectorState has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            storage[name] = value

    def __contains__(self, name: str) -> bool:
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            return name in storage

    def get(self, name: str, default: Any = None) -> Any:
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            return storage.get(name, default)

    def update(self, **values: Any) -> None:
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            storage.update(values)

    def snapshot(self) -> dict[str, Any]:
        storage = super().__getattribute__("_storage")
        lock = super().__getattribute__("_lock")
        with lock:
            return dict(storage)


class Injector(Generic[T], ABC):
    """Sync ABC. Subclasses implement ``inject`` (default) or override ``stream``.

    The default ``stream`` invokes ``inject`` once + yields the single
    result without teardown. Subclasses that need teardown (release
    GPU memory, close sockets) override ``stream`` and yield from a
    ``try/finally`` block; the :meth:`context` helper consumes the
    generator so the teardown runs on context exit.
    """

    @abstractmethod
    def inject(self, state: InjectorState) -> T:
        """Construct one instance.

        Subclasses needing teardown should override :meth:`stream`
        instead -- ``inject`` is the single-instance shortcut.
        """

    def stream(self, state: InjectorState) -> Iterator[T]:
        """Yield one or more instances; default delegates to :meth:`inject`."""

        yield self.inject(state)

    @contextlib.contextmanager
    def context(self, state: InjectorState | None = None) -> Generator[T, None, None]:
        """Context manager that yields the constructed service.

        Default state is a fresh empty :class:`InjectorState` so
        callers can ``with injector.context() as service:`` without
        pre-creating the state blob.
        """

        active_state = state if state is not None else InjectorState()
        iterator = self.stream(active_state)
        first: T
        try:
            first = next(iterator)
        except StopIteration as exc:                              # pragma: no cover
            raise RuntimeError("injector.stream yielded no value") from exc
        try:
            yield first
        finally:
            try:
                # Drain any remaining items so teardown finally-blocks run.
                for _ in iterator:                                # pragma: no cover
                    pass
            except Exception as exc:                              # noqa: BLE001
                logger.warning("injector teardown raised: %r", exc)


class SingletonInjector(Injector[T]):
    """Construct once + cache. Subsequent ``inject`` calls return the same instance.

    Useful for heavy-to-construct services that don't need per-call
    state (the embedder, the safety validator, etc.).
    """

    def __init__(self, build_fn: Callable[[InjectorState], T]) -> None:
        self._build_fn = build_fn
        self._instance: T | None = None
        self._lock = threading.RLock()

    def inject(self, state: InjectorState) -> T:
        with self._lock:
            if self._instance is None:
                self._instance = self._build_fn(state)
            return self._instance

    def reset(self) -> None:
        """Drop the cached instance. Next ``inject`` rebuilds."""

        with self._lock:
            self._instance = None


class StreamInjector(Injector[T]):
    """Wrap a generator factory so callers don't have to subclass."""

    def __init__(self, stream_fn: Callable[[InjectorState], Iterator[T]]) -> None:
        self._stream_fn = stream_fn

    def inject(self, state: InjectorState) -> T:
        iterator = self._stream_fn(state)
        try:
            value = next(iterator)
        except StopIteration as exc:                              # pragma: no cover
            raise RuntimeError("stream_fn yielded no value") from exc
        return value

    def stream(self, state: InjectorState) -> Iterator[T]:
        yield from self._stream_fn(state)


@dataclass
class InjectorRegistry:
    """Per-process registry of service-type -> injector mappings.

    Keys are arbitrary string labels (``"stt"``, ``"tts"``, ...) so
    callers can register multiple variants of the same Python type.
    """

    _entries: dict[str, Injector[Any]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register(self, key: str, injector: Injector[Any]) -> None:
        if not isinstance(injector, Injector):
            raise TypeError(f"injector must be an Injector instance, got {type(injector).__name__}")
        with self._lock:
            self._entries[key] = injector

    def unregister(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def get(self, key: str) -> Injector[Any] | None:
        with self._lock:
            return self._entries.get(key)

    def require(self, key: str) -> Injector[Any]:
        injector = self.get(key)
        if injector is None:
            raise KeyError(f"no injector registered for key {key!r}")
        return injector

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._entries.keys())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# -- module-level singleton --


_REGISTRY: InjectorRegistry | None = None
_REGISTRY_LOCK = threading.RLock()


def get_injector_registry() -> InjectorRegistry | None:
    with _REGISTRY_LOCK:
        return _REGISTRY


def set_injector_registry(registry: InjectorRegistry | None) -> None:
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = registry


def reset_injector_registry_for_testing() -> None:
    set_injector_registry(None)


def install_default_injectors(
    *,
    registry: InjectorRegistry | None = None,
    stt_injector: Injector[Any] | None = None,
    tts_injector: Injector[Any] | None = None,
) -> InjectorRegistry:
    """Register the starter STT + TTS injectors on the singleton registry.

    Callers can override the per-service injector by passing explicit
    instances; missing args fall to the default
    :func:`build_stt_engine_injector` /
    :func:`build_tts_engine_injector`. Returns the active registry.
    """

    from kenning.services.engine_injectors import (
        build_stt_engine_injector,
        build_tts_engine_injector,
    )

    active = registry if registry is not None else InjectorRegistry()
    active.register("stt", stt_injector or build_stt_engine_injector())
    active.register("tts", tts_injector or build_tts_engine_injector())
    set_injector_registry(active)
    return active
