"""HybridTaskDecomposer tests.

The decomposer calls the local LLM with a JSON-output prompt and parses
the response. We mock the LLM with a stub so tests are deterministic.
"""

from __future__ import annotations

import json

import pytest

from ultron.openclaw_routing.decomposer import (
    DecompositionResult,
    HybridTaskDecomposer,
)


class _StubLLM:
    """Returns a fixed string from generate(). Overrideable per-test."""
    def __init__(self, response: str = ""):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_well_formed_json_parses_into_subtasks():
    payload = {
        "subtasks": [
            {"order": 1, "type": "automation", "subtype": "file_op",
             "description": "Read C:/data.csv"},
            {"order": 2, "type": "coding",
             "description": "Build a Python script that processes the data"},
        ]
    }
    llm = _StubLLM(response=json.dumps(payload))
    decomposer = HybridTaskDecomposer(llm)

    result = _run(decomposer.decompose("read the csv and build a script"))
    assert isinstance(result, DecompositionResult)
    assert result.fallback_used is False
    assert len(result.subtasks) == 2
    assert result.subtasks[0].order == 1
    assert result.subtasks[0].type == "automation"
    assert result.subtasks[0].subtype == "file_op"
    assert result.subtasks[1].type == "coding"


def test_json_in_markdown_fence_is_extracted():
    """LLMs sometimes wrap the JSON in ```json ... ```."""
    payload = {"subtasks": [
        {"order": 1, "type": "coding",
         "description": "Build a CLI for X"},
    ]}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    decomposer = HybridTaskDecomposer(_StubLLM(response=fenced))
    result = _run(decomposer.decompose("build me a cli for X"))
    assert result.fallback_used is False
    assert len(result.subtasks) == 1


def test_thinking_block_is_stripped():
    """Qwen's thinking-mode wrapper should be ignored."""
    payload = {"subtasks": [
        {"order": 1, "type": "coding",
         "description": "Implement the feature"},
    ]}
    response = "<think>some reasoning</think>\n" + json.dumps(payload)
    decomposer = HybridTaskDecomposer(_StubLLM(response=response))
    result = _run(decomposer.decompose("implement that feature"))
    assert result.fallback_used is False
    assert len(result.subtasks) == 1


def test_malformed_json_falls_back_to_single_coding_subtask():
    decomposer = HybridTaskDecomposer(_StubLLM(response="not json at all"))
    result = _run(decomposer.decompose("set up environment for the demo"))
    assert result.fallback_used is True
    assert len(result.subtasks) == 1
    assert result.subtasks[0].type == "coding"
    assert "set up environment" in result.subtasks[0].description


def test_empty_response_falls_back():
    decomposer = HybridTaskDecomposer(_StubLLM(response=""))
    result = _run(decomposer.decompose("automate the workflow"))
    assert result.fallback_used is True
    assert len(result.subtasks) == 1


def test_llm_exception_falls_back_gracefully():
    class _ThrowingLLM:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("LLM crashed")
    decomposer = HybridTaskDecomposer(_ThrowingLLM())
    result = _run(decomposer.decompose("deploy this to staging"))
    assert result.fallback_used is True
    assert len(result.subtasks) == 1


def test_subtasks_sorted_by_order():
    """Even if the LLM returns subtasks out of order, decomposer sorts them."""
    payload = {"subtasks": [
        {"order": 3, "type": "coding", "description": "Step three"},
        {"order": 1, "type": "automation", "description": "Step one"},
        {"order": 2, "type": "coding", "description": "Step two"},
    ]}
    decomposer = HybridTaskDecomposer(_StubLLM(response=json.dumps(payload)))
    result = _run(decomposer.decompose("do these things"))
    assert [s.order for s in result.subtasks] == [1, 2, 3]


def test_invalid_subtask_type_is_dropped():
    """Subtasks with unknown ``type`` are silently dropped; remaining
    valid subtasks survive."""
    payload = {"subtasks": [
        {"order": 1, "type": "coding", "description": "Valid"},
        {"order": 2, "type": "magic_pony", "description": "Bogus"},
    ]}
    decomposer = HybridTaskDecomposer(_StubLLM(response=json.dumps(payload)))
    result = _run(decomposer.decompose("anything"))
    assert result.fallback_used is False
    assert len(result.subtasks) == 1
    assert result.subtasks[0].type == "coding"


def test_decomposition_disabled_in_config_uses_fallback(monkeypatch):
    """When config.routing.hybrid_task_decomposition_enabled is False,
    the decomposer never calls the LLM and returns a fallback."""
    payload = {"subtasks": [
        {"order": 1, "type": "automation", "description": "Should be ignored"},
    ]}
    llm = _StubLLM(response=json.dumps(payload))
    from ultron.config import get_config
    cfg = get_config()
    monkeypatch.setattr(cfg.routing, "hybrid_task_decomposition_enabled", False)
    decomposer = HybridTaskDecomposer(llm)
    result = _run(decomposer.decompose("automate the deploy"))
    assert result.fallback_used is True
    assert len(llm.prompts) == 0  # never called
