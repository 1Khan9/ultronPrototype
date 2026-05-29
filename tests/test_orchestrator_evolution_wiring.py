"""Tests for the catalog-13 evolution wiring in the orchestrator.

Orchestrator.__new__ pattern; no voice stack. The real construction
round-trip redirects ultron.config.PROJECT_ROOT to tmp_path so nothing
touches the repo data/ dir (binding rule R9).

Covers:
* _load_evolution_if_enabled -- disabled -> None; enabled -> a real
  EvolutionService with its proposal dir created.
* _maybe_handle_evolution_command -- strict match -> status / run-cycle
  dispatch (with the fail-open paths); no-match / no-service -> False.
* _record_evolution_turn + _consume_last_barge_in -- per-turn recorder
  feeds the service + consumes the barge-in flag; no-op when disabled.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

# Import at module load (before any monkeypatch of get_config) so the
# transitive ``config.settings`` module -- which reads get_config().audio
# at import time -- loads against the REAL config, not a per-test stub.
from ultron.pipeline.orchestrator import Orchestrator


def _bare_orchestrator() -> Any:
    o = Orchestrator.__new__(Orchestrator)
    o.evolution = None
    o.llm = None
    o._last_turn_barged_in = False
    o._spoken = []
    o._speak = lambda text: o._spoken.append(text)  # type: ignore[attr-defined]
    return o


class _FakeEvolution:
    def __init__(
        self,
        *,
        run_result: dict | None = None,
        status: str = "Evolution is active.",
        hint: str = "",
        raise_run: bool = False,
    ) -> None:
        self._run_result = run_result or {"status": "no_proposal"}
        self._status = status
        self._hint = hint
        self._raise_run = raise_run
        self.recorded: list[dict] = []
        self.autonomous_calls = 0
        self.shutdown_called = False
        self.command_failures: list[dict] = []

    def run_cycle(self) -> dict:
        if self._raise_run:
            raise RuntimeError("cycle boom")
        return self._run_result

    def status_line(self) -> str:
        return self._status

    def temperament_hint(self) -> str:
        return self._hint

    def record_turn(self, **kwargs: Any) -> None:
        self.recorded.append(kwargs)

    def record_command_failure(self, command: str = "", output: str = "", *, exit_code=None) -> None:
        self.command_failures.append(
            {"command": command, "output": output, "exit_code": exit_code}
        )

    def pre_turn_system_hint(self) -> str:
        return self._hint

    def maybe_run_autonomous_cycle(self) -> None:
        self.autonomous_calls += 1

    def shutdown(self) -> None:
        self.shutdown_called = True


# ---------------------------------------------------------------------------
# _load_evolution_if_enabled
# ---------------------------------------------------------------------------


class TestLoadEvolution:
    def test_disabled_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ultron.config as cfgmod

        cfg = SimpleNamespace(evolution=SimpleNamespace(enabled=False))
        monkeypatch.setattr(cfgmod, "get_config", lambda: cfg)
        o = _bare_orchestrator()
        assert o._load_evolution_if_enabled() is None

    def test_missing_section_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ultron.config as cfgmod

        monkeypatch.setattr(cfgmod, "get_config", lambda: SimpleNamespace())
        o = _bare_orchestrator()
        assert o._load_evolution_if_enabled() is None

    def test_enabled_real_round_trip(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod
        from ultron.config import UltronConfig
        from ultron.evolution.service import EvolutionService

        monkeypatch.setattr(cfgmod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(cfgmod, "get_config", lambda: UltronConfig())
        o = _bare_orchestrator()
        svc = o._load_evolution_if_enabled()
        assert isinstance(svc, EvolutionService)
        # The proposal directory is created under the redirected root.
        assert (tmp_path / "data" / "evolution" / "skills").is_dir()


# ---------------------------------------------------------------------------
# _maybe_handle_evolution_command
# ---------------------------------------------------------------------------


class TestMaybeHandleEvolutionCommand:
    def test_no_service_returns_false(self) -> None:
        o = _bare_orchestrator()
        o.evolution = None
        assert o._maybe_handle_evolution_command("run evolution") is False

    def test_non_match_returns_false(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution()
        assert o._maybe_handle_evolution_command("what's the weather today") is False
        assert o._spoken == []

    def test_status_command_speaks_status(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution(status="I've recorded 12 learning samples.")
        handled = o._maybe_handle_evolution_command("evolution status")
        assert handled is True
        assert o._spoken == ["I've recorded 12 learning samples."]

    def test_run_command_no_proposal(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution(run_result={"status": "no_proposal"})
        handled = o._maybe_handle_evolution_command("run an evolution cycle")
        assert handled is True
        assert "more experience" in o._spoken[0]

    def test_run_command_kept_announces_slug(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution(
            run_result={"status": "kept", "slug": "summarize_pdfs", "reasons": []}
        )
        handled = o._maybe_handle_evolution_command("evolve yourself now")
        assert handled is True
        assert "summarize_pdfs" in o._spoken[0]

    def test_run_command_reverted_message(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution(run_result={"status": "reverted"})
        handled = o._maybe_handle_evolution_command("self-improve now")
        assert handled is True
        assert "rolled it back" in o._spoken[0]

    def test_run_command_fail_open_on_raise(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution(raise_run=True)
        # run_cycle raising must not propagate; the turn is still handled.
        handled = o._maybe_handle_evolution_command("run evolution")
        assert handled is True
        assert o._spoken  # a graceful message was spoken


# ---------------------------------------------------------------------------
# _record_evolution_turn + _consume_last_barge_in
# ---------------------------------------------------------------------------


class TestRecordEvolutionTurn:
    def test_noop_when_disabled(self) -> None:
        o = _bare_orchestrator()
        o.evolution = None
        # Must not raise.
        o._record_evolution_turn("anything at all")

    def test_records_and_triggers_cycle(self) -> None:
        o = _bare_orchestrator()
        fake = _FakeEvolution()
        o.evolution = fake
        o._record_evolution_turn("can you do this thing for me")
        assert len(fake.recorded) == 1
        assert fake.recorded[0]["user_text"] == "can you do this thing for me"
        # signals is a (possibly empty) sequence extracted from the text.
        assert "signals" in fake.recorded[0]
        assert fake.autonomous_calls == 1

    def test_consumes_barge_in_flag(self) -> None:
        o = _bare_orchestrator()
        fake = _FakeEvolution()
        o.evolution = fake
        o._last_turn_barged_in = True
        o._record_evolution_turn("hello there")
        assert fake.recorded[0]["barged_in"] is True
        # The flag is consumed (reset) so it doesn't leak to later turns.
        assert o._last_turn_barged_in is False

    def test_passes_prior_response_for_correction(self) -> None:
        # Catalog 14 (T1): the prior turn's response is threaded in as the
        # agent claim a correction would be correcting.
        o = _bare_orchestrator()
        fake = _FakeEvolution()
        o.evolution = fake
        o._last_response_text = "Fixtures are session scoped by default."
        o._record_evolution_turn("no, that's wrong")
        assert fake.recorded[0]["prior_response"] == "Fixtures are session scoped by default."

    def test_prior_response_defaults_empty_when_unset(self) -> None:
        o = _bare_orchestrator()
        fake = _FakeEvolution()
        o.evolution = fake
        # _last_response_text not set on the bare orchestrator -> getattr "".
        o._record_evolution_turn("hello there")
        assert fake.recorded[0]["prior_response"] == ""

    def test_record_fail_open_on_raise(self) -> None:
        o = _bare_orchestrator()

        class _Boom(_FakeEvolution):
            def record_turn(self, **kwargs: Any) -> None:
                raise RuntimeError("record boom")

        o.evolution = _Boom()
        # Must swallow the error.
        o._record_evolution_turn("hello")


class TestConsumeLastBargeIn:
    def test_resets_flag(self) -> None:
        o = _bare_orchestrator()
        o._last_turn_barged_in = True
        assert o._consume_last_barge_in() is True
        assert o._consume_last_barge_in() is False

    def test_missing_attr_defaults_false(self) -> None:
        from ultron.pipeline.orchestrator import Orchestrator

        o = Orchestrator.__new__(Orchestrator)
        # No _last_turn_barged_in set at all -> defaults to False.
        assert o._consume_last_barge_in() is False


# ---------------------------------------------------------------------------
# _drain_evolution_command_failures (catalog 14, T1)
# ---------------------------------------------------------------------------


class TestDrainEvolutionCommandFailures:
    @staticmethod
    def _voice_with_failures(failures: list) -> Any:
        runner = SimpleNamespace(drain_command_failures=lambda: list(failures))
        return SimpleNamespace(runner=runner)

    def test_noop_when_evolution_disabled(self) -> None:
        o = _bare_orchestrator()
        o.evolution = None
        o.coding_voice = self._voice_with_failures([("pytest", "boom", 1)])
        o._drain_evolution_command_failures()  # must not raise

    def test_noop_when_coding_disabled(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution()
        o.coding_voice = None
        o._drain_evolution_command_failures()
        assert o.evolution.command_failures == []

    def test_feeds_failures_to_service(self) -> None:
        o = _bare_orchestrator()
        fake = _FakeEvolution()
        o.evolution = fake
        o.coding_voice = self._voice_with_failures(
            [("pytest", "Traceback: boom", 1), ("npm", "err", None)]
        )
        o._drain_evolution_command_failures()
        assert len(fake.command_failures) == 2
        assert fake.command_failures[0] == {
            "command": "pytest",
            "output": "Traceback: boom",
            "exit_code": 1,
        }

    def test_fail_open_on_runner_raise(self) -> None:
        o = _bare_orchestrator()
        o.evolution = _FakeEvolution()

        def _boom() -> list:
            raise RuntimeError("drain boom")

        o.coding_voice = SimpleNamespace(runner=SimpleNamespace(drain_command_failures=_boom))
        o._drain_evolution_command_failures()  # swallowed
        assert o.evolution.command_failures == []
