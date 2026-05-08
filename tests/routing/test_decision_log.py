"""RoutingDecisionLog tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultron.openclaw_routing import (
    RoutingDecisionLog,
    classify_routing,
    get_routing_log,
    set_routing_log,
)
from ultron.openclaw_routing.intents import (
    HybridSubtask,
    RoutingIntent,
    RoutingIntentKind,
)


def test_record_writes_one_jsonl_line(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    intent = classify_routing("open hacker news")
    log.record(intent, handler="OpenClawDispatcher.handle_browser",
               outcome="stub")
    lines = (tmp_path / "routing.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["intent"] == "browser_automation"
    assert rec["handler"] == "OpenClawDispatcher.handle_browser"
    assert rec["outcome"] == "stub"
    assert rec["rule_based"] is True


def test_record_appends(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    log.record(classify_routing("open hacker news"),
               handler="x", outcome="stub")
    log.record(classify_routing("good morning"),
               handler="voice.respond", outcome="passthrough")
    records = [
        json.loads(line)
        for line in (tmp_path / "routing.jsonl").read_text("utf-8").splitlines()
    ]
    assert len(records) == 2
    assert records[0]["intent"] == "browser_automation"
    assert records[1]["intent"] == "conversational"


def test_record_includes_subtasks(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    intent = RoutingIntent(
        kind=RoutingIntentKind.HYBRID_TASK,
        raw_text="set up a dev env",
        confidence=0.85,
        source="rule",
        reason="hybrid pattern matched",
        subtasks=[
            HybridSubtask(order=1, type="automation", subtype="file_op",
                          description="read pyproject"),
            HybridSubtask(order=2, type="coding",
                          description="install deps via pip"),
        ],
    )
    log.record(intent, handler="HybridTaskDecomposer", outcome="stub")
    rec = json.loads(
        (tmp_path / "routing.jsonl").read_text("utf-8").strip()
    )
    assert "subtasks" in rec
    assert len(rec["subtasks"]) == 2
    assert rec["subtasks"][0]["type"] == "automation"


def test_record_truncates_long_utterance(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    long_text = "x" * 10000
    intent = RoutingIntent(
        kind=RoutingIntentKind.CONVERSATIONAL,
        raw_text=long_text,
        source="default",
    )
    log.record(intent, handler="voice.respond", outcome="passthrough")
    rec = json.loads(
        (tmp_path / "routing.jsonl").read_text("utf-8").strip()
    )
    assert len(rec["utterance"]) <= 500


def test_record_extra_merges_into_record(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    intent = classify_routing("open hacker news")
    log.record(
        intent,
        handler="OpenClawDispatcher.handle_browser",
        outcome="stub",
        extra={"stub_reason": "OpenClaw integration not yet complete"},
    )
    rec = json.loads(
        (tmp_path / "routing.jsonl").read_text("utf-8").strip()
    )
    assert rec["stub_reason"] == "OpenClaw integration not yet complete"


def test_record_extra_does_not_clobber_structural_keys(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    log.record(
        classify_routing("open hacker news"),
        handler="X",
        outcome="stub",
        extra={"intent": "BAD", "handler": "BAD"},
    )
    rec = json.loads(
        (tmp_path / "routing.jsonl").read_text("utf-8").strip()
    )
    assert rec["intent"] == "browser_automation"
    assert rec["handler"] == "X"


def test_record_swallows_write_errors(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing.jsonl")
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    log._path = blocked  # appending to a directory raises
    log.record(classify_routing("test"), handler="x", outcome="stub")
    # Did not raise.


def test_singleton_round_trip(tmp_path):
    """get_routing_log() returns a singleton; set_routing_log injects."""
    custom = RoutingDecisionLog(path=tmp_path / "custom.jsonl")
    set_routing_log(custom)
    assert get_routing_log() is custom
    set_routing_log(RoutingDecisionLog())  # restore default
