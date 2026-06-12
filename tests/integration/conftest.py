"""Shared fixtures for end-to-end pipeline integration tests.

Pattern: build a CapabilityVoiceController against a scripted mock
bridge + stub LLM, then exercise the routing layer end-to-end. This
gives us deterministic tests that cover the orchestrator's dispatch
logic without loading real models (which take minutes to load and
require GPU).

For tests that genuinely need the real Whisper / LLM / RVC / Piper
stack, see :mod:`tests.coding.test_orchestration_real` and
:mod:`scripts.measure_baseline_extended` — both gated on
``PYTEST_RUN_GPU_TESTS=1`` for explicit opt-in.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pytest

os.environ.setdefault("KENNING_CODING_MCP_ALLOW_ANY_ROOT", "1")

from kenning.coding import (
    CapabilityVoiceController,
    CodingTaskRunner,
    ProjectRegistry,
    ProjectResolver,
    StatusNarrator,
    KenningMCPServer,
)
from kenning.coding.coordinator import ConversationCoordinator
from kenning.coding.session import SessionStatus
from kenning.coding.verification import Verifier
from kenning.openclaw_routing import (
    RoutingDecisionLog,
    set_routing_log,
)
from kenning.resilience import (
    ErrorLog,
    set_error_log,
    reset_phrase_cache,
)
from tests.coding.mock_bridge import ClaudeScript, ScriptedClaudeBridge


# ---------------------------------------------------------------------------
# Stub LLM
# ---------------------------------------------------------------------------


class StubLLM:
    """Deterministic LLM stub. Set ``response_text`` for a single response;
    use ``push()`` for a script of replies (popped FIFO)."""

    def __init__(self, response_text: str = "Acknowledged."):
        self.response_text = response_text
        self.responses: List[str] = []
        self.prompts: List[str] = []

    def push(self, *responses: str) -> "StubLLM":
        self.responses.extend(responses)
        return self

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        return self.response_text


# ---------------------------------------------------------------------------
# Scoped logs (no leakage between tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def errors_log(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    set_error_log(log)
    yield log
    set_error_log(ErrorLog())


@pytest.fixture
def routing_log(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    set_routing_log(log)
    yield log
    set_routing_log(RoutingDecisionLog())


@pytest.fixture
def read_routing(routing_log):
    import json

    def _read():
        if not routing_log.path.is_file():
            return []
        records = []
        with routing_log.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records
    return _read


@pytest.fixture
def read_errors(errors_log):
    import json

    def _read():
        if not errors_log.path.is_file():
            return []
        records = []
        with errors_log.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records
    return _read


@pytest.fixture(autouse=True)
def _reset_phrase_cache():
    reset_phrase_cache()
    yield
    reset_phrase_cache()


@pytest.fixture(autouse=True)
def _reset_external_breakers():
    """Ensure breakers don't leak state between integration tests."""
    from kenning.web_search import brave as _brave_mod, jina as _jina_mod
    _brave_mod._BRAVE_BREAKER.reset()
    _jina_mod._JINA_BREAKER.reset()
    yield
    _brave_mod._BRAVE_BREAKER.reset()
    _jina_mod._JINA_BREAKER.reset()


# ---------------------------------------------------------------------------
# Capability voice stack — full controller wired to the mock bridge.
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_llm():
    return StubLLM()


@pytest.fixture
def cap_stack(tmp_path, stub_llm):
    """Construct a complete CapabilityVoiceController stack against the
    scripted mock bridge.

    Returns a small bag with:
      - voice: the CapabilityVoiceController
      - server: the MCP server (for direct state introspection)
      - runner: the CodingTaskRunner
      - llm: the StubLLM
      - registry / resolver / sandbox: project plumbing
      - new_session: helper to create a session + bridge it to a script
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    server = KenningMCPServer(host="127.0.0.1", port=0)
    verifier = Verifier(store=server.store)
    coordinator = ConversationCoordinator(
        store=server.store, llm=stub_llm, verifier=verifier,
    )
    server.set_clarification_responder(coordinator.decide_clarification)
    server.set_declare_complete_handler(coordinator.handle_declare_complete)
    narrator = StatusNarrator(llm=None)

    # Placeholder bridge — most tests that exercise routing don't actually
    # start a coding task. Tests that do supply their own ScriptedClaudeBridge.
    placeholder = ScriptedClaudeBridge(
        server, ClaudeScript(), session_id="__unset__",
    )
    runner = CodingTaskRunner(
        bridge=placeholder, log_path=tmp_path / "audit.jsonl",
        narrator=narrator, store=server.store,
    )
    registry = ProjectRegistry(path=tmp_path / "projects.json")
    resolver = ProjectResolver(registry, embedder=None)
    voice = CapabilityVoiceController(
        runner=runner, registry=registry, resolver=resolver,
        sandbox_root=sandbox, coordinator=coordinator,
    )

    class _Bag:
        pass
    bag = _Bag()
    bag.voice = voice
    bag.server = server
    bag.runner = runner
    bag.coordinator = coordinator
    bag.llm = stub_llm
    bag.registry = registry
    bag.resolver = resolver
    bag.sandbox = sandbox
    return bag


# ---------------------------------------------------------------------------
# Convenience: dispatch an utterance the way the orchestrator does.
# ---------------------------------------------------------------------------


def dispatch_utterance(cap_stack, utterance: str):
    """Mirror the orchestrator's main-loop dispatch hook for an utterance.

    Returns the VoiceResponse (or None for CONVERSATIONAL passthrough).
    Records routing-decision audit entries via the singleton.
    """
    from kenning.openclaw_routing import classify_routing
    routing_intent = classify_routing(
        utterance,
        has_active_coding_task=cap_stack.runner.has_active_task(),
        has_pending_clarification=cap_stack.voice.has_pending_clarification(),
    )
    return cap_stack.voice.handle_capability_intent(routing_intent)
