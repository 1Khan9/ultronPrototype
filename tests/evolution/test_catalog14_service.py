"""Catalog 14 -- EvolutionService runtime: qualitative capture, recurrence
counters, the bounded pre-turn nudge, digest/status surfacing, command-failure
observation, and ledger-reload. Hermetic (SimpleNamespace config + tmp_path).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ultron.evolution.service import EvolutionService


def _cfg(**kw):
    ev = SimpleNamespace(
        enabled=True,
        max_steps=3,
        cycle_check_interval_turns=1000,
        pause_on_demote=False,
        apply_temperament=True,
        correction_detection_enabled=True,
        feature_request_capture_enabled=True,
        command_failure_capture_enabled=True,
        pre_turn_nudge_enabled=True,
        pre_turn_nudge_max_chars=240,
        recurrence_threshold=3,
    )
    for k, v in kw.items():
        setattr(ev, k, v)
    return SimpleNamespace(evolution=ev)


def _svc(tmp_path, **kw):
    return EvolutionService.from_config(_cfg(**kw), project_root=tmp_path)


def _ledger(tmp_path, name):
    p = Path(tmp_path) / "data" / "evolution" / name
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_record_turn_captures_correction_and_feeds_repair(tmp_path):
    svc = _svc(tmp_path)
    svc.record_turn(
        user_text="No, that's wrong, fixtures are function scoped.",
        prior_response="They are session scoped by default.",
    )
    assert len(_ledger(tmp_path, "corrections.jsonl")) == 1
    # correction feeds the repair (failed_capsules) ledger
    assert len(_ledger(tmp_path, "failed_capsules.jsonl")) == 1
    svc.shutdown()


def test_record_turn_captures_feature_request(tmp_path):
    svc = _svc(tmp_path)
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    assert len(_ledger(tmp_path, "feature_requests.jsonl")) == 1
    assert svc._pending_feature_requests == 1
    # feature requests are NEVER distilled -> no repair-ledger row
    assert len(_ledger(tmp_path, "failed_capsules.jsonl")) == 0
    svc.shutdown()


def test_capture_gating_off(tmp_path):
    svc = _svc(
        tmp_path,
        correction_detection_enabled=False,
        feature_request_capture_enabled=False,
        command_failure_capture_enabled=False,
    )
    svc.record_turn(user_text="No that's wrong.", prior_response="claim")
    svc.record_turn(user_text="I wish you could export to CSV")
    svc.record_command_failure(command="pytest", output="Traceback: boom", exit_code=1)
    assert _ledger(tmp_path, "corrections.jsonl") == []
    assert _ledger(tmp_path, "feature_requests.jsonl") == []
    assert _ledger(tmp_path, "command_failures.jsonl") == []
    svc.shutdown()


def test_record_command_failure_captures_and_feeds_repair(tmp_path):
    svc = _svc(tmp_path)
    svc.record_command_failure(
        command="python run.py", output="Traceback (most recent call last):\nboom", exit_code=1
    )
    assert len(_ledger(tmp_path, "command_failures.jsonl")) == 1
    assert len(_ledger(tmp_path, "failed_capsules.jsonl")) == 1
    # a clean command records nothing
    svc.record_command_failure(command="pytest", output="3 passed", exit_code=0)
    assert len(_ledger(tmp_path, "command_failures.jsonl")) == 1
    svc.shutdown()


def test_pre_turn_nudge_fires_for_feature_requests_and_caps(tmp_path):
    svc = _svc(tmp_path)
    assert svc.pre_turn_system_hint() == ""  # idle -> empty (prompt byte-identical)
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    hint = svc.pre_turn_system_hint()
    assert "[Evolution:" in hint and "feature request" in hint
    svc.shutdown()
    # cap enforced
    svc2 = _svc(tmp_path, pre_turn_nudge_max_chars=20)
    svc2.record_turn(user_text="I wish you could add a CSV export option")
    assert len(svc2.pre_turn_system_hint()) <= 20
    svc2.shutdown()


def test_pre_turn_nudge_fires_for_recurring_pattern(tmp_path):
    svc = _svc(tmp_path)
    for _ in range(3):
        svc.record_turn(user_text="the search felt slow and laggy", signals=["perf_bottleneck"])
    hint = svc.pre_turn_system_hint()
    assert "recurring pattern" in hint
    svc.shutdown()


def test_pre_turn_nudge_gated_off(tmp_path):
    svc = _svc(tmp_path, pre_turn_nudge_enabled=False)
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    assert svc.pre_turn_system_hint() == ""
    svc.shutdown()


def test_digest_surfaces_feature_requests_and_corrections(tmp_path):
    svc = _svc(tmp_path)
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    svc.record_turn(user_text="No, that's wrong.", prior_response="claim about X")
    digest = svc.digest()
    assert "Feature requests:" in digest
    assert "2x" in digest  # asked twice
    assert "User corrections recorded: 1" in digest
    assert "feature request" in svc.status_line()
    svc.shutdown()


def test_counters_rebuilt_on_reload(tmp_path):
    svc = _svc(tmp_path)
    svc.record_turn(user_text="I wish you could export the report to CSV.")
    svc.record_turn(user_text="No, that's wrong.", prior_response="claim")
    svc.record_turn(user_text="the search felt slow", signals=["perf_bottleneck"])
    svc.shutdown()
    svc2 = _svc(tmp_path)  # fresh instance reads the ledgers
    assert svc2._pending_feature_requests == 1
    assert svc2._pending_corrections == 1
    assert any(k.startswith("feature_request:") for k in svc2._pattern_recurrence)
    assert any(k.startswith("correction:") for k in svc2._pattern_recurrence)
    svc2.shutdown()
