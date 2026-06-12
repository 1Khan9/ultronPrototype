"""Tests for kenning.memory.dual_history."""

from __future__ import annotations

import pytest

from kenning.memory import dual_history as dh


# ---------------------------------------------------------------------------
# new_turn_id
# ---------------------------------------------------------------------------

class TestTurnId:
    def test_unique(self) -> None:
        assert dh.new_turn_id() != dh.new_turn_id()

    def test_hex_format(self) -> None:
        out = dh.new_turn_id()
        assert len(out) == 32
        int(out, 16)  # raises on non-hex


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_record_verbatim_only(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(dh.ROLE_USER, "hello")
        assert store.verbatim_turn_count() == 1
        assert store.api_turn_count() == 0
        entry = store.get_verbatim(turn_id)
        assert entry is not None
        assert entry.text == "hello"
        assert entry.role == dh.ROLE_USER

    def test_record_verbatim_and_api(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(
            dh.ROLE_USER,
            "hi",
            api_content="[Style: terse]\n\nhi",
        )
        assert store.verbatim_turn_count() == 1
        assert store.api_turn_count() == 1
        api = store.get_api(turn_id)
        assert api is not None
        assert api.content == "[Style: terse]\n\nhi"

    def test_record_uses_provided_turn_id(self) -> None:
        store = dh.DualHistoryStore()
        fixed_id = "0" * 32
        returned = store.record(dh.ROLE_ASSISTANT, "ack", turn_id=fixed_id)
        assert returned == fixed_id

    def test_record_image_refs_preserved(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(
            dh.ROLE_USER,
            "look at this screenshot",
            image_refs=["sha256:abc", "sha256:def"],
        )
        entry = store.get_verbatim(turn_id)
        assert entry is not None
        assert entry.image_refs == ("sha256:abc", "sha256:def")

    def test_record_metadata(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(
            dh.ROLE_USER,
            "what time is it",
            metadata={"intent": "TIME_QUERY", "confidence": 0.92},
        )
        entry = store.get_verbatim(turn_id)
        assert entry is not None
        assert entry.metadata["intent"] == "TIME_QUERY"


class TestRecordApi:
    def test_record_api_separate(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(dh.ROLE_USER, "x")
        # Add the api shape afterwards.
        store.record_api(turn_id, dh.ROLE_USER, "[Style: terse]\nx")
        api = store.get_api(turn_id)
        assert api is not None
        assert api.content == "[Style: terse]\nx"

    def test_record_api_with_compacted_flag(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = "f" * 32
        store.record_api(
            turn_id, dh.ROLE_SYSTEM, "<summary>old 8 turns</summary>",
            compacted=True, elided_count=8,
        )
        api = store.get_api(turn_id)
        assert api is not None
        assert api.compacted is True
        assert api.elided_count == 8


# ---------------------------------------------------------------------------
# Read surface
# ---------------------------------------------------------------------------

class TestRead:
    def test_recent_verbatim(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(5):
            store.record(dh.ROLE_USER, f"msg-{i}")
        recent = store.recent_verbatim(3)
        assert [e.text for e in recent] == ["msg-2", "msg-3", "msg-4"]

    def test_recent_api(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(3):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        assert [e.content for e in store.recent_api(2)] == ["a-1", "a-2"]

    def test_recent_zero_returns_empty(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "x")
        assert store.recent_verbatim(0) == ()
        assert store.recent_api(-1) == ()

    def test_get_missing_returns_none(self) -> None:
        store = dh.DualHistoryStore()
        assert store.get_verbatim("nope") is None
        assert store.get_api("nope") is None

    def test_find_verbatim_by_substring(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "discuss the BUDGET for Q1")
        store.record(dh.ROLE_USER, "what's the weather")
        store.record(dh.ROLE_USER, "remember our budget call")
        hits = store.find_verbatim_by_substring("budget")
        # Newest-first: 'remember our budget call' should come before
        # the older 'discuss the BUDGET' entry.
        assert hits[0].text.startswith("remember")
        assert len(hits) == 2

    def test_find_verbatim_case_sensitive(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "BUDGET")
        hits = store.find_verbatim_by_substring("budget", case_insensitive=False)
        assert hits == ()

    def test_snapshot_includes_indices(self) -> None:
        store = dh.DualHistoryStore()
        turn_id = store.record(dh.ROLE_USER, "x", api_content="api-x")
        snap = store.snapshot()
        assert snap.turn_id_to_verbatim_index[turn_id] == 0
        assert snap.turn_id_to_api_index[turn_id] == 0


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

class TestTruncation:
    def test_truncate_after_turn(self) -> None:
        store = dh.DualHistoryStore()
        ids = [
            store.record(dh.ROLE_USER, f"m-{i}", api_content=f"a-{i}")
            for i in range(5)
        ]
        # Truncate after id index 1 → keep first 2 entries.
        verbatim_drop, api_drop = store.truncate_after_turn(ids[1])
        assert verbatim_drop == 3
        assert api_drop == 3
        assert store.verbatim_turn_count() == 2
        assert store.api_turn_count() == 2

    def test_truncate_after_turn_unknown_id_no_op(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(3):
            store.record(dh.ROLE_USER, f"m-{i}")
        verbatim_drop, api_drop = store.truncate_after_turn("unknown")
        assert verbatim_drop == 0
        assert api_drop == 0

    def test_truncate_after_empty_clears_all(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(4):
            store.record(dh.ROLE_USER, f"m-{i}", api_content=f"a-{i}")
        verbatim_drop, api_drop = store.truncate_after_turn("")
        assert verbatim_drop == 4
        assert api_drop == 4

    def test_truncate_to_offset(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(5):
            store.record(dh.ROLE_USER, f"m-{i}", api_content=f"a-{i}")
        verbatim_drop, api_drop = store.truncate_to_offset(offset_from_end=2)
        assert verbatim_drop == 2
        assert api_drop == 2
        assert store.verbatim_turn_count() == 3

    def test_truncate_to_offset_clamps(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "x")
        verbatim_drop, _ = store.truncate_to_offset(offset_from_end=99)
        assert verbatim_drop == 1
        assert store.verbatim_turn_count() == 0

    def test_truncate_zero_no_op(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "x")
        out = store.truncate_to_offset(offset_from_end=0)
        assert out == (0, 0)


# ---------------------------------------------------------------------------
# Compaction shape
# ---------------------------------------------------------------------------

class TestCompaction:
    def test_replace_api_range_drops(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(5):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        removed = store.replace_api_range(1, 3)
        assert removed == 2
        assert store.api_turn_count() == 3
        # The verbatim record is UNCHANGED — that's the whole point.
        assert store.verbatim_turn_count() == 5

    def test_replace_api_range_with_summary(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(5):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        summary = dh.ApiTurn(
            turn_id="summary-1",
            role=dh.ROLE_SYSTEM,
            content="<summary>3 turns</summary>",
            compacted=True,
            elided_count=3,
        )
        removed = store.replace_api_range(1, 4, replacement=summary)
        assert removed == 3
        assert store.api_turn_count() == 3  # 5 - 3 + 1 = 3
        # Summary entry is searchable.
        assert store.get_api("summary-1") is not None
        # Verbatim untouched.
        assert store.verbatim_turn_count() == 5

    def test_replace_api_range_bounds(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(3):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        # Out-of-bounds: clamped, no removals.
        assert store.replace_api_range(10, 20) == 0
        # Start > stop: no removals.
        assert store.replace_api_range(2, 1) == 0


# ---------------------------------------------------------------------------
# Drift report
# ---------------------------------------------------------------------------

class TestDriftReport:
    def test_report_when_all_aligned(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(3):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        report = store.drift_report()
        assert report["shared"] == 3
        assert report["verbatim_only"] == 0
        assert report["api_only"] == 0

    def test_report_when_api_compacted(self) -> None:
        store = dh.DualHistoryStore()
        for i in range(5):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        store.replace_api_range(1, 4)  # drop 3 api entries
        report = store.drift_report()
        assert report["verbatim_only"] == 3
        assert report["shared"] == 2


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

class TestCaps:
    def test_verbatim_cap_evicts(self) -> None:
        store = dh.DualHistoryStore(verbatim_cap=2)
        store.record(dh.ROLE_USER, "a")
        store.record(dh.ROLE_USER, "b")
        store.record(dh.ROLE_USER, "c")
        assert store.verbatim_turn_count() == 2
        texts = [e.text for e in store.verbatim()]
        assert texts == ["b", "c"]

    def test_api_cap_evicts(self) -> None:
        store = dh.DualHistoryStore(api_cap=2)
        for i in range(3):
            store.record(dh.ROLE_USER, f"v-{i}", api_content=f"a-{i}")
        assert store.api_turn_count() == 2

    def test_clear_drops_everything(self) -> None:
        store = dh.DualHistoryStore()
        store.record(dh.ROLE_USER, "x", api_content="api-x")
        store.clear()
        assert store.verbatim_turn_count() == 0
        assert store.api_turn_count() == 0
