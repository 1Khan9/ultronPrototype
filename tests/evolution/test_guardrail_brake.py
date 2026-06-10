"""Tests for the guardrail auto-revert brake (#15 + #65).

Service-level coverage of the post-apply monitoring half: from_config
building the metrics ring, record_turn feeding the quality flags, the
watch arm/tick/expiry countdown, the relative (pre-vs-post snapshot)
evaluation, the data-only revert of a kept-then-regressed skill, and the
queued voice narration. All hermetic (tmp_path stores, fake loop, no
voice stack, no subprocess -- the VRAM probe is stubbed out).
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from ultron.evolution.autonomy import TieredAutonomyController
from ultron.evolution.evolution_loop import ApplyStatus, EvolutionState
from ultron.evolution.guardrails import GuardrailSample
from ultron.evolution.personality import PersonalityTuner
from ultron.evolution.service import (
    POST_APPLY_MIN_LATENCY_SAMPLES,
    EvolutionService,
    EvolutionStore,
)
from ultron.evolution.turn_metrics import TurnMetricsRing


def _ev_config(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "enabled": True,
        "guardrail_monitoring_enabled": True,
        "post_apply_monitor_turns": 3,
        "apply_temperament": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_service(
    tmp_path: Path,
    *,
    ring: Optional[TurnMetricsRing] = None,
    sampler: Any = None,
    config: Optional[SimpleNamespace] = None,
) -> tuple[EvolutionService, list[int], Path]:
    """Directly-constructed service with a fake loop + recording reloader."""
    proposal_dir = tmp_path / "skills"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    reloads: list[int] = []
    svc = EvolutionService(
        config=config or _ev_config(),
        store=EvolutionStore(tmp_path),
        autonomy=TieredAutonomyController(),
        personality=PersonalityTuner.from_dict({}),
        loop=SimpleNamespace(run_once=lambda: None),  # type: ignore[arg-type]
        state=EvolutionState(),
        proposal_dir=proposal_dir,
        registry_reloader=lambda: reloads.append(1),
        turn_metrics=ring,
        guardrail_sampler=sampler,
    )
    # Keep the post-apply evaluation hermetic: never spawn nvidia-smi.
    svc._post_apply_vram_probe = lambda: None  # type: ignore[method-assign]
    return svc, reloads, proposal_dir


def _kept_result(slug: str = "test-skill") -> SimpleNamespace:
    return SimpleNamespace(
        status=ApplyStatus.KEPT,
        proposal=SimpleNamespace(
            slug=slug, filename=f"{slug}.md", gene=SimpleNamespace(id="gene-1")
        ),
        reasons=(),
    )


# ---------------------------------------------------------------------------
# from_config -- ring construction
# ---------------------------------------------------------------------------


class TestFromConfigRing:
    def test_monitoring_on_builds_ring(self, tmp_path: Path) -> None:
        cfg = SimpleNamespace(evolution=_ev_config())
        svc = EvolutionService.from_config(cfg, project_root=tmp_path)
        assert svc is not None
        assert isinstance(svc.turn_metrics, TurnMetricsRing)

    def test_monitoring_off_leaves_ring_none(self, tmp_path: Path) -> None:
        cfg = SimpleNamespace(
            evolution=_ev_config(guardrail_monitoring_enabled=False)
        )
        svc = EvolutionService.from_config(cfg, project_root=tmp_path)
        assert svc is not None
        assert svc.turn_metrics is None

    def test_explicit_sampler_wins_over_ring(self, tmp_path: Path) -> None:
        marker = GuardrailSample(ttft_ms=42.0)
        cfg = SimpleNamespace(evolution=_ev_config())
        svc = EvolutionService.from_config(
            cfg, project_root=tmp_path, guardrail_sampler=lambda: marker
        )
        assert svc is not None
        # An injected sampler is honoured and no internal ring is built.
        assert svc.turn_metrics is None

    def test_window_knob_respected(self, tmp_path: Path) -> None:
        cfg = SimpleNamespace(evolution=_ev_config(guardrail_window_turns=7))
        svc = EvolutionService.from_config(cfg, project_root=tmp_path)
        assert svc is not None
        assert svc.turn_metrics.window == 7


# ---------------------------------------------------------------------------
# record_turn -- quality feed + watch tick
# ---------------------------------------------------------------------------


class TestRecordTurnFeeds:
    def test_quality_flags_reach_the_ring(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, _, _ = _make_service(tmp_path, ring=ring)
        svc.record_turn(user_text="hello there how are you", corrected=True)
        svc.record_turn(user_text="tell me about ducks please")
        assert ring.totals() == (0, 2)
        sample = ring.sample(min_latency_samples=1, min_rate_samples=2)
        assert sample.correction_rate == pytest.approx(0.5)

    def test_no_ring_is_a_noop(self, tmp_path: Path) -> None:
        svc, _, _ = _make_service(tmp_path, ring=None)
        svc.record_turn(user_text="hello there how are you")  # must not raise

    def test_broken_ring_is_fail_open(self, tmp_path: Path) -> None:
        class _Broken:
            def note_quality(self, **kwargs: Any) -> None:
                raise RuntimeError("ring boom")

            def totals(self) -> tuple[int, int]:
                return (0, 0)

        svc, _, _ = _make_service(tmp_path, ring=_Broken())  # type: ignore[arg-type]
        svc.record_turn(user_text="hello there how are you")  # must not raise


# ---------------------------------------------------------------------------
# the watch -- arm / tick / expiry
# ---------------------------------------------------------------------------


class TestPostApplyWatch:
    def test_arm_requires_ring_and_sampler(self, tmp_path: Path) -> None:
        svc, _, _ = _make_service(tmp_path, ring=None, sampler=None)
        svc._arm_post_apply_watch(_kept_result())
        assert svc._post_apply_watch is None

    def test_arm_snapshots_pre_state(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=100.0)
        pre = GuardrailSample(ttft_ms=100.0)
        svc, _, _ = _make_service(tmp_path, ring=ring, sampler=lambda: pre)
        svc._arm_post_apply_watch(_kept_result())
        watch = svc._post_apply_watch
        assert watch is not None
        assert watch["slug"] == "test-skill"
        assert watch["pre_sample"] is pre
        assert watch["markers"] == (1, 0)
        assert watch["turns_remaining"] == 3

    def test_arm_disabled_by_config(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, _, _ = _make_service(
            tmp_path,
            ring=ring,
            sampler=lambda: GuardrailSample(),
            config=_ev_config(guardrail_monitoring_enabled=False),
        )
        svc._arm_post_apply_watch(_kept_result())
        assert svc._post_apply_watch is None

    def test_tick_counts_down_and_evaluates_at_expiry(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, _, _ = _make_service(
            tmp_path,
            ring=ring,
            sampler=lambda: GuardrailSample(),
            config=_ev_config(post_apply_monitor_turns=2),
        )
        svc._arm_post_apply_watch(_kept_result())
        captured: list[dict] = []
        done = threading.Event()

        def _capture(watch: dict) -> None:
            captured.append(watch)
            done.set()

        svc._evaluate_post_apply_watch = _capture  # type: ignore[method-assign]
        svc._tick_post_apply_watch()
        assert svc._post_apply_watch is not None  # one turn left
        svc._tick_post_apply_watch()
        assert done.wait(2.0), "evaluation thread never fired"
        assert svc._post_apply_watch is None
        assert captured and captured[0]["slug"] == "test-skill"

    def test_record_turn_ticks_the_watch(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, _, _ = _make_service(
            tmp_path,
            ring=ring,
            sampler=lambda: GuardrailSample(),
            config=_ev_config(post_apply_monitor_turns=5),
        )
        svc._arm_post_apply_watch(_kept_result())
        svc.record_turn(user_text="tell me about golden retrievers")
        assert svc._post_apply_watch is not None
        assert svc._post_apply_watch["turns_remaining"] == 4


# ---------------------------------------------------------------------------
# evaluation -- keep vs revert
# ---------------------------------------------------------------------------


def _post_records(ring: TurnMetricsRing, ttft: float, n: int = POST_APPLY_MIN_LATENCY_SAMPLES) -> None:
    for _ in range(n):
        ring.note_response(ttft_ms=ttft)


class TestEvaluation:
    def _armed_service(
        self, tmp_path: Path, *, pre_ttft: float
    ) -> tuple[EvolutionService, list[int], Path, TurnMetricsRing, dict]:
        ring = TurnMetricsRing()
        pre = GuardrailSample(ttft_ms=pre_ttft, correction_rate=0.0, error_rate=0.0)
        svc, reloads, proposal_dir = _make_service(
            tmp_path, ring=ring, sampler=lambda: pre
        )
        svc._arm_post_apply_watch(_kept_result())
        watch = svc._post_apply_watch
        assert watch is not None
        svc._post_apply_watch = None  # simulate expiry pop
        skill_file = proposal_dir / "test-skill.md"
        skill_file.write_text("# distilled skill\n", encoding="utf-8")
        return svc, reloads, skill_file, ring, watch

    def test_no_regression_keeps_the_skill(self, tmp_path: Path) -> None:
        svc, reloads, skill_file, ring, watch = self._armed_service(
            tmp_path, pre_ttft=100.0
        )
        _post_records(ring, 102.0)
        svc._evaluate_post_apply_watch(watch)
        assert skill_file.exists()
        assert reloads == []
        assert svc.pop_pending_narration() is None

    def test_latency_regression_reverts(self, tmp_path: Path) -> None:
        svc, reloads, skill_file, ring, watch = self._armed_service(
            tmp_path, pre_ttft=100.0
        )
        _post_records(ring, 200.0)  # 2x the pre-apply median; 1.15x trips
        svc._evaluate_post_apply_watch(watch)
        assert not skill_file.exists()
        assert reloads == [1]
        narration = svc.pop_pending_narration()
        assert narration is not None and "rolled back" in narration
        assert svc.autonomy.state("skills").reverted >= 1

    def test_revert_appends_audit_and_failure_records(self, tmp_path: Path) -> None:
        svc, _, _, ring, watch = self._armed_service(tmp_path, pre_ttft=100.0)
        _post_records(ring, 300.0)
        svc._evaluate_post_apply_watch(watch)
        events = svc.store.events_path.read_text(encoding="utf-8")
        assert "post_apply_revert" in events
        failures = svc.store.load_failures()
        assert any(f.get("reason_class") == "post_apply_guardrail" for f in failures)
        ok, _break = svc.store.verify_event_chain()
        assert ok

    def test_unobserved_pre_ttft_skips_latency_check(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        pre = GuardrailSample()  # nothing observed pre-apply
        svc, reloads, proposal_dir = _make_service(tmp_path, ring=ring, sampler=lambda: pre)
        svc._arm_post_apply_watch(_kept_result())
        watch = svc._post_apply_watch
        svc._post_apply_watch = None
        skill_file = proposal_dir / "test-skill.md"
        skill_file.write_text("# distilled skill\n", encoding="utf-8")
        _post_records(ring, 5000.0)  # huge -- but no pre baseline -> skipped
        svc._evaluate_post_apply_watch(watch)
        assert skill_file.exists()
        assert reloads == []

    def test_quality_regression_reverts(self, tmp_path: Path) -> None:
        svc, reloads, skill_file, ring, watch = self._armed_service(
            tmp_path, pre_ttft=100.0
        )
        # Post window: every turn dissatisfied (rate 1.0 vs pre 0.0).
        for _ in range(5):
            ring.note_quality(corrected=True)
        _post_records(ring, 100.0)
        svc._evaluate_post_apply_watch(watch)
        assert not skill_file.exists()
        assert reloads == [1]

    def test_containment_blocks_path_escape(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, reloads, proposal_dir = _make_service(
            tmp_path, ring=ring, sampler=lambda: GuardrailSample()
        )
        outside = tmp_path / "evil.md"
        outside.write_text("precious user data", encoding="utf-8")
        watch = {
            "slug": "evil",
            "filename": "../evil.md",
            "gene": "g",
            "pre_sample": GuardrailSample(ttft_ms=100.0),
            "markers": (0, 0),
        }
        verdict = SimpleNamespace(
            should_revert=True, tripped_guards=("latency",), details=("boom",)
        )
        svc._revert_kept_proposal(watch, verdict)
        assert outside.exists()  # escape attempt did NOT delete the file

    def test_pop_pending_narration_clears(self, tmp_path: Path) -> None:
        svc, _, _ = _make_service(
            tmp_path, ring=TurnMetricsRing(), sampler=lambda: GuardrailSample()
        )
        svc._pending_narration = "test line"
        assert svc.pop_pending_narration() == "test line"
        assert svc.pop_pending_narration() is None


# ---------------------------------------------------------------------------
# _do_cycle arms the watch on KEPT
# ---------------------------------------------------------------------------


class TestDoCycleArm:
    def test_kept_result_arms_watch(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, reloads, _ = _make_service(
            tmp_path, ring=ring, sampler=lambda: GuardrailSample()
        )
        svc._loop = SimpleNamespace(run_once=lambda: _kept_result())  # type: ignore[assignment]
        out = svc._do_cycle()
        assert out["status"] == "kept"
        assert reloads == [1]  # registry reloaded for the kept skill
        assert svc._post_apply_watch is not None
        assert svc._post_apply_watch["slug"] == "test-skill"

    def test_non_kept_result_does_not_arm(self, tmp_path: Path) -> None:
        ring = TurnMetricsRing()
        svc, _, _ = _make_service(
            tmp_path, ring=ring, sampler=lambda: GuardrailSample()
        )
        blocked = SimpleNamespace(
            status=ApplyStatus.BLOCKED,
            proposal=SimpleNamespace(
                slug="s", filename="s.md", gene=SimpleNamespace(id="g")
            ),
            reasons=("tier-3 hard wall",),
        )
        svc._loop = SimpleNamespace(run_once=lambda: blocked)  # type: ignore[assignment]
        out = svc._do_cycle()
        assert out["status"] == "blocked"
        assert svc._post_apply_watch is None
