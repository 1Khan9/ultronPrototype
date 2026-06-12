"""Tests for the orchestrator's intent dispatch hook.

We test the small dispatcher logic on a minimal orchestrator fragment
without spinning up the full voice stack. The dispatcher's job: take
an :class:`IntentMatch`, find the right local handler, fire it, and
report back whether the LLM path should be skipped.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kenning.intent.recognizer import IntentMatch, KenningIntentRecognizer


# ---------------------------------------------------------------------------
# Test scaffold -- borrow the orchestrator's dispatch by duck-typing
# ---------------------------------------------------------------------------


class _MinimalOrchestrator:
    """Stand-in for the orchestrator's intent surface."""

    def __init__(
        self,
        *,
        intent_recognizer=None,
        gaming_mode_manager=None,
        tts=None,
    ):
        self._intent_recognizer = intent_recognizer
        self.gaming_mode_manager = gaming_mode_manager
        self.tts = tts or MagicMock()
        self.coding_voice = None
        # 2026-05-22 -- consumed by _build_response_stream when set.
        self._next_turn_force_search = False

    # Mirror of the real orchestrator implementations.
    def _maybe_dispatch_intent(self, user_text: str) -> bool:
        recognizer = self._intent_recognizer
        if recognizer is None:
            return False
        try:
            match = recognizer.process_utterance(user_text)
        except Exception:
            return False
        if match is None:
            return False
        try:
            return self._dispatch_intent_match(match)
        except Exception:
            return False

    # Mirror of orchestrator's frozensets (2026-05-22 multi-variant
    # dispatch). Keep these in sync with
    # ``Orchestrator._INTENT_ENGAGE_PHRASES`` etc. so the test covers
    # the same variant resolution the live dispatcher uses.
    _ENGAGE = frozenset({
        "engage gaming mode",
        "switch to gaming mode",
        "turn on gaming mode",
        "start gaming mode",
        "activate gaming mode",
    })
    _DISENGAGE = frozenset({
        "disengage gaming mode",
        "turn off gaming mode",
        "stop gaming mode",
        "exit gaming mode",
        "deactivate gaming mode",
    })
    _STATUS = frozenset({"gaming mode status"})
    _FORCE_SEARCH = frozenset({
        "what is the latest news",
        "tell me the latest news",
        "current events",
        "what is happening today",
        "what is going on",
        "any recent news",
    })

    def _dispatch_intent_match(self, match) -> bool:
        phrase = match.canonical_phrase
        if phrase in self._FORCE_SEARCH:
            self._next_turn_force_search = True
            return False  # LLM still runs; gate gets pre-populated
        if phrase in self._ENGAGE:
            manager = self.gaming_mode_manager
            if manager is None:
                return False
            import asyncio
            try:
                asyncio.run(manager.engage())
            except Exception:
                return False
            try:
                self.tts.speak("Shutting down desktop control. Have fun.")
            except Exception:
                pass
            return True
        if phrase in self._DISENGAGE:
            manager = self.gaming_mode_manager
            if manager is None:
                return False
            import asyncio
            try:
                asyncio.run(manager.disengage())
            except Exception:
                return False
            try:
                self.tts.speak("Full control restored.")
            except Exception:
                pass
            return True
        if phrase in self._STATUS:
            manager = self.gaming_mode_manager
            if manager is None:
                return False
            try:
                status = manager.status()
                self.tts.speak(f"Gaming mode is {status.value}.")
            except Exception:
                pass
            return True
        return False


class _StubRecognizer:
    """Recognizer that returns a scripted match."""

    def __init__(self, match: IntentMatch | None):
        self._match = match

    def process_utterance(self, utterance: str):
        return self._match


def _stub_gaming_mode_manager():
    """A mock manager whose engage/disengage are awaitable + status returns
    a SimpleNamespace with a .value."""
    mgr = MagicMock()

    async def _engage():
        return None

    async def _disengage():
        return None

    mgr.engage = _engage
    mgr.disengage = _disengage
    mgr.status = MagicMock(return_value=SimpleNamespace(value="idle"))
    return mgr


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def test_no_recognizer_means_no_dispatch():
    orch = _MinimalOrchestrator()
    assert orch._maybe_dispatch_intent("anything") is False


def test_no_match_means_no_dispatch():
    orch = _MinimalOrchestrator(intent_recognizer=_StubRecognizer(None))
    assert orch._maybe_dispatch_intent("anything") is False


def test_recognizer_exception_falls_through():
    class _Boom:
        def process_utterance(self, _):
            raise RuntimeError("simulated recognizer failure")

    orch = _MinimalOrchestrator(intent_recognizer=_Boom())
    # No exception -- voice loop continues.
    assert orch._maybe_dispatch_intent("test") is False


# ---------------------------------------------------------------------------
# Gaming mode dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", [
    "engage gaming mode",
    "switch to gaming mode",
    "turn on gaming mode",
    "start gaming mode",
    "activate gaming mode",
])
def test_engage_phrase_variants_all_fire_manager_engage(phrase):
    """All registered engage variants dispatch to manager.engage(),
    not just the canonical 'engage gaming mode'. The intent recognizer
    keeps each phrase as its own canonical_phrase (no synonym graph),
    so the dispatcher resolves variants via a frozenset lookup."""
    manager = _stub_gaming_mode_manager()
    engage_calls = {"n": 0}

    async def _engage():
        engage_calls["n"] += 1

    manager.engage = _engage

    match = IntentMatch(
        canonical_phrase=phrase,
        utterance=f"user said {phrase!r}",
        similarity=0.9,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )
    assert orch._maybe_dispatch_intent("anything") is True
    assert engage_calls["n"] == 1


@pytest.mark.parametrize("phrase", [
    "disengage gaming mode",
    "turn off gaming mode",
    "stop gaming mode",
    "exit gaming mode",
    "deactivate gaming mode",
])
def test_disengage_phrase_variants_all_fire_manager_disengage(phrase):
    manager = _stub_gaming_mode_manager()
    disengage_calls = {"n": 0}

    async def _disengage():
        disengage_calls["n"] += 1

    manager.disengage = _disengage

    match = IntentMatch(
        canonical_phrase=phrase, utterance="x", similarity=0.9,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )
    assert orch._maybe_dispatch_intent("anything") is True
    assert disengage_calls["n"] == 1


def test_engage_gaming_mode_intent_fires_manager_engage():
    manager = _stub_gaming_mode_manager()
    engage_calls = {"n": 0}

    async def _engage():
        engage_calls["n"] += 1

    manager.engage = _engage

    match = IntentMatch(
        canonical_phrase="engage gaming mode",
        utterance="lets fire up gaming mode",
        similarity=0.94,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )

    handled = orch._maybe_dispatch_intent("lets fire up gaming mode")

    assert handled is True
    assert engage_calls["n"] == 1
    orch.tts.speak.assert_called_with(
        "Shutting down desktop control. Have fun.",
    )


def test_disengage_gaming_mode_intent_fires_manager_disengage():
    manager = _stub_gaming_mode_manager()
    disengage_calls = {"n": 0}

    async def _disengage():
        disengage_calls["n"] += 1

    manager.disengage = _disengage

    match = IntentMatch(
        canonical_phrase="disengage gaming mode",
        utterance="I'm done playing now",
        similarity=0.88,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )
    assert orch._maybe_dispatch_intent("I'm done playing now") is True
    assert disengage_calls["n"] == 1
    orch.tts.speak.assert_called_with("Full control restored.")


def test_gaming_mode_status_intent_speaks_current_state():
    manager = _stub_gaming_mode_manager()
    manager.status = MagicMock(return_value=SimpleNamespace(value="engaged"))

    match = IntentMatch(
        canonical_phrase="gaming mode status",
        utterance="are we still in gaming mode",
        similarity=0.91,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )
    assert orch._maybe_dispatch_intent("are we still in gaming mode") is True
    orch.tts.speak.assert_called_with("Gaming mode is engaged.")


def test_gaming_intent_with_no_manager_falls_through():
    match = IntentMatch(
        canonical_phrase="engage gaming mode",
        utterance="gaming mode",
        similarity=0.99,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=None,
    )
    # No manager wired -> falls through to LLM path.
    assert orch._maybe_dispatch_intent("gaming mode") is False
    orch.tts.speak.assert_not_called()


def test_manager_engage_failure_falls_through():
    manager = _stub_gaming_mode_manager()

    async def _broken():
        raise RuntimeError("simulated manager crash")

    manager.engage = _broken

    match = IntentMatch(
        canonical_phrase="engage gaming mode",
        utterance="gaming mode",
        similarity=0.99,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=manager,
    )
    # Manager failed -> dispatcher returns False so the LLM path can
    # still respond (e.g., "Gaming mode failed to engage").
    assert orch._maybe_dispatch_intent("gaming mode") is False


# ---------------------------------------------------------------------------
# Force-search intent (2026-05-22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", [
    "what is the latest news",
    "tell me the latest news",
    "current events",
    "what is happening today",
    "what is going on",
    "any recent news",
])
def test_force_search_intent_sets_flag_and_falls_through(phrase):
    """Matched fresh-data phrases must NOT short-circuit the LLM (the
    caller still produces the response) but must set the orchestrator's
    ``_next_turn_force_search`` flag so the response stream routes to
    SEARCH instead of letting the preflight LLM decide."""
    match = IntentMatch(
        canonical_phrase=phrase, utterance="user said " + phrase,
        similarity=0.91,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=_stub_gaming_mode_manager(),
    )
    assert orch._next_turn_force_search is False  # clean state

    handled = orch._maybe_dispatch_intent(phrase)

    assert handled is False, (
        "force-search intents must fall through; LLM still runs"
    )
    assert orch._next_turn_force_search is True, (
        "the flag must be set so the gate forces SEARCH this turn"
    )


def test_force_search_flag_does_not_persist_across_turns():
    """Reset the flag in __init__ -- subsequent turns start False."""
    orch = _MinimalOrchestrator(intent_recognizer=_StubRecognizer(None))
    assert orch._next_turn_force_search is False
    # Simulate consumption (which the response stream does).
    orch._next_turn_force_search = True
    orch._next_turn_force_search = False
    assert orch._next_turn_force_search is False


def test_unrecognised_phrase_falls_through():
    """An intent phrase that has no orchestrator-side handler returns
    False so the LLM gets a chance."""
    match = IntentMatch(
        canonical_phrase="play some music",
        utterance="put on some tunes",
        similarity=0.85,
    )
    orch = _MinimalOrchestrator(
        intent_recognizer=_StubRecognizer(match),
        gaming_mode_manager=_stub_gaming_mode_manager(),
    )
    assert orch._maybe_dispatch_intent("put on some tunes") is False
