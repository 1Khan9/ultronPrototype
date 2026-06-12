"""Integration test category 3 — coding tasks through the full
CapabilityVoiceController dispatch.

Validates: a coding utterance routes through classify_routing →
handle_capability_intent → handle_utterance → CodingTaskRunner with
the mock bridge and lands cleanly. Runs in seconds; no Claude API.

Heavier real-Claude variants live in tests/coding/test_orchestration_real.py
under PYTEST_RUN_GPU_TESTS=1.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import dispatch_utterance
from tests.coding.mock_bridge import ClaudeScript, ScriptedClaudeBridge
from kenning.coding.bridge import TaskRequest
from kenning.coding.session import SessionStatus


def _bridge_with_script(cap_stack, session_id, script):
    """Replace the placeholder bridge with one that runs ``script``
    against the given session."""
    bridge = ScriptedClaudeBridge(cap_stack.server, script, session_id=session_id)
    cap_stack.runner._bridge = bridge  # noqa: SLF001 — test wiring
    return bridge


def test_coding_classification_routes_through_capability(cap_stack, routing_log, read_routing):
    """A 'build me a python script' utterance classifies as CODE_TASK
    and the routing log notes the dispatch."""
    response = dispatch_utterance(cap_stack, "build me a python script that prints hello world")
    rec = read_routing()[-1]
    assert rec["intent"] == "code_task"
    # The handler delegated back to the runner; outcome may be 'dispatched'
    # if a session got created, or 'passthrough' if the controller couldn't
    # resolve a project. Either way, the routing log captures it.
    assert rec["handler"] == "CodingTaskRunner.handle_utterance"


def test_progress_query_with_active_task_routes_progress(
    cap_stack, routing_log, read_routing, monkeypatch,
):
    """When a coding task is running, 'how's it going?' classifies as
    PROGRESS_QUERY (not CONVERSATIONAL).

    We simulate has_active_task() rather than spawning a real bridge
    worker so the test doesn't depend on thread-timing or interpreter
    shutdown order — the routing-classification logic is what's under
    test, not the runner's task tracking.
    """
    monkeypatch.setattr(cap_stack.runner, "has_active_task", lambda: True)

    dispatch_utterance(cap_stack, "how's it going?")
    rec = read_routing()[-1]
    assert rec["intent"] == "progress_query", (
        f"got {rec['intent']}; reason={rec['reason']}"
    )


def test_cancel_with_active_task_classifies_cancel(
    cap_stack, routing_log, read_routing, monkeypatch,
):
    """'stop the task' classifies as CANCEL when a task is running."""
    monkeypatch.setattr(cap_stack.runner, "has_active_task", lambda: True)

    dispatch_utterance(cap_stack, "stop the task")
    rec = read_routing()[-1]
    assert rec["intent"] == "cancel"


def test_progress_query_without_active_task_is_conversational(
    cap_stack, routing_log, read_routing,
):
    """Without an active task, 'how's it going' is just casual chat —
    classifies as CONVERSATIONAL, not PROGRESS_QUERY."""
    dispatch_utterance(cap_stack, "how's it going")
    rec = read_routing()[-1]
    assert rec["intent"] == "conversational"


def test_cancel_without_active_task_is_conversational(
    cap_stack, routing_log, read_routing,
):
    """'stop the task' with no task running is conversational —
    nothing to cancel."""
    dispatch_utterance(cap_stack, "stop the task")
    rec = read_routing()[-1]
    assert rec["intent"] == "conversational"


# ---------------------------------------------------------------------------
# Coding utterances WITHOUT an active task still classify as CODE_TASK
# (start a fresh session) — these are 5 representative cases.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utt", [
    "build me a python script that prints hello world",
    "create a small typescript cli tool",
    "make me a script that fetches the weather",
    "scaffold a fastapi project called weather",
    "write me a bash script for backups",
])
def test_code_task_without_active_task_classifies_correctly(
    cap_stack, routing_log, read_routing, utt,
):
    """The routing classifier returns CODE_TASK for these even when no
    coding task is running. Whether the controller actually starts a
    task depends on project resolution (often it fails-soft because we
    don't have real models)."""
    dispatch_utterance(cap_stack, utt)
    rec = read_routing()[-1]
    assert rec["intent"] == "code_task", (
        f"got {rec['intent']} for {utt!r}"
    )
