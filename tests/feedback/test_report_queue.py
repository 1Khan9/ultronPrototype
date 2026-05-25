"""Tests for the T12 user-initiated report queue."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ultron.feedback.report_queue import (
    FinalAction,
    IllegalTriageError,
    Report,
    ReportQueue,
    ReportStatus,
    ReportTargetKind,
    UnknownReportError,
    new_report_id,
)


EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self, start: datetime = EPOCH) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: int = 1) -> None:
        self.now = self.now + timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# new_report_id


def test_new_report_id_is_32_hex_chars() -> None:
    rid = new_report_id()
    assert len(rid) == 32
    assert all(c in "0123456789abcdef" for c in rid)


def test_new_report_id_is_unique() -> None:
    a = new_report_id()
    b = new_report_id()
    assert a != b


# ---------------------------------------------------------------------------
# file_report


def test_file_report_creates_open_report() -> None:
    q = ReportQueue(now_fn=_Clock())
    report = q.file_report(
        target_kind=ReportTargetKind.TURN,
        target_id="turn-42",
        reason="wrong answer",
    )
    assert report.status is ReportStatus.OPEN
    assert report.target_kind is ReportTargetKind.TURN
    assert report.target_id == "turn-42"
    assert report.reason == "wrong answer"
    assert report.created_at != ""


def test_file_report_rejects_empty_target() -> None:
    q = ReportQueue(now_fn=_Clock())
    with pytest.raises(ValueError):
        q.file_report(target_kind=ReportTargetKind.TURN, target_id="")


def test_file_report_writes_extras_through() -> None:
    q = ReportQueue(now_fn=_Clock())
    extras = {"channel": "voice", "confidence": 0.7}
    report = q.file_report(
        target_kind=ReportTargetKind.SKILL,
        target_id="skill-x",
        extras=extras,
    )
    assert report.extras["channel"] == "voice"
    assert report.extras["confidence"] == 0.7


def test_file_report_assigns_unique_ids() -> None:
    q = ReportQueue(now_fn=_Clock())
    a = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t1")
    b = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t1")
    assert a.id != b.id


# ---------------------------------------------------------------------------
# triage


def test_triage_to_confirmed_with_final_action() -> None:
    q = ReportQueue(now_fn=_Clock())
    report = q.file_report(
        target_kind=ReportTargetKind.SKILL,
        target_id="@user/example",
    )
    triaged = q.triage(
        report.id,
        status=ReportStatus.CONFIRMED,
        note="legitimate concern",
        final_action=FinalAction.QUARANTINE,
    )
    assert triaged.status is ReportStatus.CONFIRMED
    assert triaged.final_action is FinalAction.QUARANTINE
    assert triaged.triage_note == "legitimate concern"
    assert triaged.triaged_at != ""


def test_triage_to_dismissed() -> None:
    q = ReportQueue(now_fn=_Clock())
    report = q.file_report(
        target_kind=ReportTargetKind.RESPONSE,
        target_id="r-1",
    )
    triaged = q.triage(report.id, status=ReportStatus.DISMISSED)
    assert triaged.status is ReportStatus.DISMISSED
    assert triaged.final_action is FinalAction.NONE


def test_triage_rejects_open_status() -> None:
    q = ReportQueue(now_fn=_Clock())
    report = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    with pytest.raises(ValueError):
        q.triage(report.id, status=ReportStatus.OPEN)


def test_triage_unknown_report_raises() -> None:
    q = ReportQueue(now_fn=_Clock())
    with pytest.raises(UnknownReportError):
        q.triage("no-such-id", status=ReportStatus.DISMISSED)


def test_triage_already_closed_raises() -> None:
    q = ReportQueue(now_fn=_Clock())
    report = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-2")
    q.triage(report.id, status=ReportStatus.CONFIRMED)
    with pytest.raises(IllegalTriageError):
        q.triage(report.id, status=ReportStatus.DISMISSED)


# ---------------------------------------------------------------------------
# listing helpers


def test_list_reports_filter_by_status() -> None:
    q = ReportQueue(now_fn=_Clock())
    r1 = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    r2 = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-2")
    q.triage(r1.id, status=ReportStatus.CONFIRMED)
    opens = q.list_reports(status=ReportStatus.OPEN)
    confirmed = q.list_reports(status=ReportStatus.CONFIRMED)
    assert len(opens) == 1
    assert opens[0].id == r2.id
    assert len(confirmed) == 1
    assert confirmed[0].id == r1.id


def test_list_reports_filter_by_kind() -> None:
    q = ReportQueue(now_fn=_Clock())
    q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    q.file_report(target_kind=ReportTargetKind.SKILL, target_id="skill")
    out = q.list_reports(target_kind=ReportTargetKind.SKILL)
    assert len(out) == 1
    assert out[0].target_kind is ReportTargetKind.SKILL


def test_list_reports_filter_by_target_id() -> None:
    q = ReportQueue(now_fn=_Clock())
    q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-2")
    out = q.list_reports(target_id="t-2")
    assert len(out) == 1
    assert out[0].target_id == "t-2"


def test_count_reports() -> None:
    q = ReportQueue(now_fn=_Clock())
    assert q.count() == 0
    r = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    assert q.count() == 1
    assert q.count(status=ReportStatus.OPEN) == 1
    assert q.count(status=ReportStatus.CONFIRMED) == 0
    q.triage(r.id, status=ReportStatus.CONFIRMED)
    assert q.count(status=ReportStatus.OPEN) == 0
    assert q.count(status=ReportStatus.CONFIRMED) == 1


def test_get_returns_none_for_unknown() -> None:
    q = ReportQueue(now_fn=_Clock())
    assert q.get("no-such") is None


# ---------------------------------------------------------------------------
# Persistence


def test_persistence_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "reports.jsonl"
    q = ReportQueue(audit_log_path=log, now_fn=_Clock())
    r = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1", reason="x")
    q.triage(r.id, status=ReportStatus.DISMISSED, note="not a real issue")
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_replay_recovers_state(tmp_path: Path) -> None:
    log = tmp_path / "reports.jsonl"
    clock = _Clock()
    q1 = ReportQueue(audit_log_path=log, now_fn=clock)
    r = q1.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1", reason="oops")
    clock.advance()
    q1.triage(r.id, status=ReportStatus.CONFIRMED, final_action=FinalAction.HIDE)

    q2 = ReportQueue(audit_log_path=log, now_fn=_Clock())
    restored = q2.get(r.id)
    assert restored is not None
    assert restored.status is ReportStatus.CONFIRMED
    assert restored.final_action is FinalAction.HIDE


def test_chain_verification_clean(tmp_path: Path) -> None:
    log = tmp_path / "reports.jsonl"
    q = ReportQueue(audit_log_path=log, now_fn=_Clock())
    r = q.file_report(target_kind=ReportTargetKind.TURN, target_id="t-1")
    q.triage(r.id, status=ReportStatus.DISMISSED)
    assert q.verify_log_chain() is True


def test_chain_verification_detects_tamper(tmp_path: Path) -> None:
    log = tmp_path / "reports.jsonl"
    q = ReportQueue(audit_log_path=log, now_fn=_Clock())
    r = q.file_report(
        target_kind=ReportTargetKind.TURN,
        target_id="t-1",
        reason="original",
    )
    q.triage(r.id, status=ReportStatus.DISMISSED)
    # Tamper: rewrite the file with a flipped reason field.
    raw = log.read_text(encoding="utf-8")
    tampered = raw.replace("original", "mallory", 1)
    log.write_text(tampered, encoding="utf-8")
    assert q.verify_log_chain() is False


def test_round_trip_preserves_all_fields(tmp_path: Path) -> None:
    log = tmp_path / "reports.jsonl"
    q = ReportQueue(audit_log_path=log, now_fn=_Clock())
    r = q.file_report(
        target_kind=ReportTargetKind.MEMORY,
        target_id="mem-1",
        reason="stale fact",
        version="v3",
        reporter_voice_session="vs-9",
        extras={"k": "v"},
    )
    q2 = ReportQueue(audit_log_path=log, now_fn=_Clock())
    restored = q2.get(r.id)
    assert restored is not None
    assert restored.target_kind is ReportTargetKind.MEMORY
    assert restored.target_id == "mem-1"
    assert restored.reason == "stale fact"
    assert restored.version == "v3"
    assert restored.reporter_voice_session == "vs-9"
    assert restored.extras["k"] == "v"


# ---------------------------------------------------------------------------
# Report dataclass


def test_report_json_round_trip() -> None:
    r = Report(
        id="abc",
        target_kind=ReportTargetKind.SKILL,
        target_id="x",
        reason="r",
        status=ReportStatus.CONFIRMED,
        version="v1",
        reporter_voice_session="vs",
        created_at="2026-01-01T00:00:00+00:00",
        triaged_at="2026-01-02T00:00:00+00:00",
        triage_note="ok",
        final_action=FinalAction.HIDE,
        extras={"key": "value"},
    )
    out = r.to_json_dict()
    restored = Report.from_json_dict(out)
    assert restored == r


def test_report_from_json_unknown_enum_falls_back() -> None:
    out = {
        "id": "abc",
        "target_kind": "future-kind",
        "target_id": "x",
        "status": "future-status",
        "final_action": "future-action",
    }
    restored = Report.from_json_dict(out)
    assert restored.target_kind is ReportTargetKind.OTHER
    assert restored.status is ReportStatus.OPEN
    assert restored.final_action is FinalAction.NONE
