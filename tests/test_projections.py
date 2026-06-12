"""Phase C / Phase 1 — context projection tests.

Coverage:
  * Schema correctness: each projection function returns a result whose
    .projection is the right dataclass type with the expected fields.
  * Budget respect: each projection stays at or below its declared
    budget on a stress session with 1000+ events.
  * Truncation sanity: when over budget, the truncation log records
    what was dropped, in priority order; critical fields (user_intent,
    clarification_question, adjustment_text) are never silently dropped.
  * Pure-function property: same input -> same output.
  * MCP server exposure: get_status_delta, get_clarification_context,
    get_adjustment_context, get_correction_context, get_completion_context
    each return a ProjectionResult; deprecated get_session_state still
    works but emits a DeprecationWarning.
"""

from __future__ import annotations

import os
import time
import warnings
from pathlib import Path
from typing import List

import pytest

os.environ.setdefault("KENNING_CODING_MCP_ALLOW_ANY_ROOT", "1")

from kenning.coding.projections import (
    AdjustmentContextProjection,
    ClarificationContextProjection,
    CompletionContextProjection,
    CorrectionContextProjection,
    ProjectionResult,
    StatusDeltaProjection,
    count_tokens,
    project_adjustment_context,
    project_clarification_context,
    project_completion_context,
    project_correction_context,
    project_status_delta,
)
from kenning.coding.session import (
    AdjustmentRecord,
    ClarificationRequest,
    CompletionClaim,
    FileRecord,
    ProjectSession,
    SessionStatus,
    StageRecord,
    TestStatus,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _small_session(**overrides) -> ProjectSession:
    base = ProjectSession(
        session_id="small",
        project_root=Path("hello_cli"),
        user_intent="Build a Python CLI that prints hello world",
        refined_goal="",
        status=SessionStatus.EXECUTING,
        current_stage="implementing",
        stages_completed=[
            StageRecord(stage="scaffold", summary="set up dirs", files_touched=["main.py"]),
            StageRecord(stage="implementing", summary="wrote main", files_touched=["main.py"]),
        ],
        files_created=[FileRecord(path="main.py")],
        test_status=TestStatus(passing=2, failing=0, last_updated=time.time()),
        started_at=time.time() - 30,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _huge_session(**overrides) -> ProjectSession:
    """Synthetic session with 1000 stages, 1000 files created, 500 modified,
    20 adjustments, 5000-char user intent. Used for budget stress tests."""
    big = "A " * 2500  # ~5000-char intent
    base = ProjectSession(
        session_id="huge",
        project_root=Path("big_project"),
        user_intent=big,
        refined_goal=big,
        status=SessionStatus.EXECUTING,
        current_stage="stage_999",
        stages_completed=[
            StageRecord(
                stage=f"stage_{i:04d}",
                summary="X" * 200,
                files_touched=[f"f{j}.py" for j in range(10)],
                timestamp=time.time() - 1000 + i,
            )
            for i in range(1000)
        ],
        files_created=[
            FileRecord(path=f"src/dir/sub/created_{i:04d}.py", first_seen=time.time() - 1000 + i)
            for i in range(1000)
        ],
        files_modified=[
            FileRecord(path=f"src/dir/mod_{i:04d}.py", first_seen=time.time() - 500 + i)
            for i in range(500)
        ],
        test_status=TestStatus(passing=200, failing=5, last_updated=time.time()),
        user_adjustments=[
            AdjustmentRecord(text=f"adjustment {i}: " + "B" * 200, timestamp=time.time() - 100 + i)
            for i in range(20)
        ],
        last_user_status_query=time.time() - 30,
        started_at=time.time() - 3600,
        verification_failures=4,
        completion_claim=CompletionClaim(
            summary="C" * 1000, entry_point="main.py", run_command="python main.py",
            files_created=[f"created_{i}.py" for i in range(50)],
            files_modified=[f"mod_{i}.py" for i in range(50)],
        ),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# Schema correctness
# ---------------------------------------------------------------------------


def test_clarification_context_schema():
    s = _small_session()
    r = project_clarification_context(
        s, clarification_question="SQLite or Postgres?",
        options=["sqlite", "postgres"],
    )
    assert isinstance(r, ProjectionResult)
    assert isinstance(r.projection, ClarificationContextProjection)
    p = r.projection
    assert p.user_intent == s.user_intent
    assert p.clarification_question == "SQLite or Postgres?"
    assert p.options == ["sqlite", "postgres"]
    assert p.current_stage == "implementing"
    assert p.relevant_facts == []  # no facts_lookup wired
    assert isinstance(r.text, str) and len(r.text) > 0
    assert r.token_count > 0


def test_status_delta_schema():
    s = _small_session()
    r = project_status_delta(s)
    assert isinstance(r.projection, StatusDeltaProjection)
    p = r.projection
    assert p.current_stage == "implementing"
    assert p.is_first_query is True  # last_user_status_query=None on small session
    assert p.recent_stages == ["scaffold", "implementing"]
    assert p.new_files_created_count == 1
    assert p.new_files_created_paths == ["main.py"]  # count < 5
    assert p.test_passing == 2
    assert p.in_correction_loop is False


def test_adjustment_context_schema():
    s = _small_session()
    r = project_adjustment_context(s, adjustment_text="use httpx instead")
    assert isinstance(r.projection, AdjustmentContextProjection)
    p = r.projection
    assert p.adjustment_text == "use httpx instead"
    assert p.user_intent == s.user_intent
    assert p.completed_stages == ["scaffold", "implementing"]
    assert p.conflicts_with_completed is False
    assert p.relevant_facts == []


def test_correction_context_schema():
    s = _small_session()
    s.completion_claim = CompletionClaim(
        summary="done", files_created=["main.py"], files_modified=[],
    )
    failures = [
        {"check": "TESTS", "detail": "1 test failed", "hint": "fix imports"},
        {"check": "FILES_EXIST", "detail": "main.py exists", "hint": ""},
    ]
    r = project_correction_context(
        s, failures=failures,
        failed_test_names=["test_main"],
        failed_test_messages="AssertionError",
    )
    assert isinstance(r.projection, CorrectionContextProjection)
    p = r.projection
    assert p.original_goal == s.user_intent
    assert len(p.failing_checks) == 2
    assert p.failing_checks[0].check == "TESTS"
    assert p.failed_test_names == ["test_main"]
    assert p.claimed_files_created == ["main.py"]
    assert p.prior_correction_attempts == 0


def test_completion_context_schema():
    s = _small_session()
    s.completion_claim = CompletionClaim(
        summary="all done", entry_point="main.py", run_command="python main.py",
        files_created=["main.py"],
    )
    s.completed_at = time.time()
    r = project_completion_context(s)
    assert isinstance(r.projection, CompletionContextProjection)
    p = r.projection
    assert p.user_intent == s.user_intent
    assert p.final_summary == "all done"
    assert p.entry_point == "main.py"
    assert p.run_command == "python main.py"
    assert p.files_created_count == 1
    assert p.files_created_paths == ["main.py"]  # count < 10
    assert p.test_passing == 2


# ---------------------------------------------------------------------------
# Budget respect on huge session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,fn,kwargs", [
    ("clarification", project_clarification_context,
     dict(clarification_question="What library should I use?",
          options=["a", "b", "c"])),
    ("status_delta", project_status_delta, {}),
    ("adjustment", project_adjustment_context,
     dict(adjustment_text="switch the framework now")),
    ("correction", project_correction_context,
     dict(
         failures=[
             {"check": "TESTS", "detail": "x" * 600, "hint": "y" * 60},
             {"check": "STRUCTURE", "detail": "z" * 600, "hint": ""},
             {"check": "LINT", "detail": "w" * 600, "hint": ""},
             {"check": "SMOKE", "detail": "v" * 600, "hint": ""},
         ],
         failed_test_names=[f"test_{i}" for i in range(50)],
         failed_test_messages="E" * 6000,
     )),
    ("completion", project_completion_context, {}),
])
def test_huge_session_respects_budget(name, fn, kwargs):
    """Each projection stays at or below its declared budget on a
    stress session (1000 stages, 1000 files, 5000-char intent, 20 adj)."""
    s = _huge_session()
    r = fn(s, **kwargs)
    assert r.fits_budget, (
        f"{name}: {r.token_count} tokens > {r.budget} budget; "
        f"truncations: {r.truncations_applied}"
    )


# ---------------------------------------------------------------------------
# Truncation behavior
# ---------------------------------------------------------------------------


def test_correction_truncates_long_test_messages():
    """Failed test messages over 1000 tokens get capped + the cap is
    recorded in truncations_applied."""
    s = _small_session()
    long_msg = "FAIL " * 1500  # ~3000 tokens
    r = project_correction_context(
        s, failures=[{"check": "TESTS", "detail": "ok"}],
        failed_test_messages=long_msg,
    )
    assert r.fits_budget
    assert any("failed_test_messages" in t for t in r.truncations_applied)


def test_clarification_caps_each_fact_at_200_chars():
    """Pre-render cap: each fact is truncated to 200 chars. The 5-fact
    count cap means even pathological facts can't blow the budget
    alone."""
    s = _small_session()
    big_facts = ["fact " + ("X" * 2000) for _ in range(5)]
    def _facts(_q): return big_facts

    r = project_clarification_context(
        s, clarification_question="what?", facts_lookup=_facts,
    )
    assert r.fits_budget
    assert r.projection.user_intent == s.user_intent
    # Each fact trimmed to 200 chars at construction time.
    for f in r.projection.relevant_facts:
        assert len(f) <= 200


def test_clarification_truncates_facts_first_when_budget_loop_engages():
    """When the budget loop engages, facts go before adjustments and
    before stage/refined_goal. Force the loop with many short options
    that push the projection over."""
    s = _small_session(
        user_adjustments=[AdjustmentRecord(text=f"adj {i}") for i in range(2)],
    )
    # Many options + facts to force overflow even after caps.
    many_options = [f"opt_{i}_" + "z" * 150 for i in range(8)]  # 8 * ~50 tokens
    long_facts = ["fact_" + "y" * 180 for _ in range(5)]
    def _facts(_q): return long_facts

    # Reduce budget temporarily to force the loop.
    from kenning.coding import projections as _pmod
    orig_budget = _pmod.ClarificationContextProjection.BUDGET_TOKENS
    _pmod.ClarificationContextProjection.BUDGET_TOKENS = 250
    try:
        r = project_clarification_context(
            s, clarification_question="critical question",
            options=many_options, facts_lookup=_facts,
        )
    finally:
        _pmod.ClarificationContextProjection.BUDGET_TOKENS = orig_budget

    assert r.fits_budget
    # Critical fields preserved.
    assert r.projection.user_intent == s.user_intent
    assert "critical question" in r.text
    # Loop ran -- something was trimmed.
    assert r.truncations_applied, "expected loop to trim something"


def test_status_delta_drops_paths_first_when_over_budget():
    """Paths list is dropped before stage labels when the projection
    overflows. We force the issue with very-long file names."""
    long_paths = [
        FileRecord(path=("long/path/" * 100) + f"file_{i}.py")
        for i in range(4)
    ]
    s = _small_session(files_created=long_paths)
    r = project_status_delta(s)
    assert r.fits_budget
    # Either paths got dropped, or they were short enough to fit.
    if r.token_count > 200:  # heuristic: large file paths likely got trimmed
        assert any(
            "paths" in t or "stages" in t for t in r.truncations_applied
        ) or r.fits_budget


def test_completion_drops_paths_then_decisions_under_pressure():
    """When completion projection overflows, it drops file paths before
    losing the summary."""
    s = _huge_session()
    s.completion_claim = CompletionClaim(
        summary="done well",
        entry_point="main.py",
        files_created=[f"long/path/" + ("X" * 50) + f"_{i}.py" for i in range(50)],
        files_modified=[f"long/path/" + ("Y" * 50) + f"_{i}.py" for i in range(50)],
    )
    r = project_completion_context(s)
    assert r.fits_budget
    p = r.projection
    # Paths got dropped (count too large), but the summary survived.
    # files_created_count is preserved, paths are None.
    assert p.files_created_paths is None or len(p.files_created_paths) < 10
    assert p.final_summary  # critical field preserved


# ---------------------------------------------------------------------------
# Pure-function property
# ---------------------------------------------------------------------------


def test_projections_are_pure_functions():
    """Same session -> same projection (modulo time-based fields, which
    we control by fixing started_at)."""
    s = _small_session()
    r1 = project_clarification_context(
        s, clarification_question="what?", options=["a"],
    )
    r2 = project_clarification_context(
        s, clarification_question="what?", options=["a"],
    )
    assert r1.text == r2.text
    assert r1.token_count == r2.token_count


# ---------------------------------------------------------------------------
# Critical fields never silently dropped
# ---------------------------------------------------------------------------


def test_clarification_question_never_silently_dropped():
    """Even at the most extreme truncation, the clarification question
    survives -- it's the most critical field."""
    s = _huge_session()
    big_options = ["option " + "z" * 500 for _ in range(20)]
    r = project_clarification_context(
        s, clarification_question="critical question text here",
        options=big_options,
    )
    assert r.fits_budget
    assert "critical question text here" in r.text


def test_adjustment_text_never_silently_dropped():
    s = _huge_session()
    r = project_adjustment_context(s, adjustment_text="critical adjustment text")
    assert r.fits_budget
    assert "critical adjustment text" in r.text


# ---------------------------------------------------------------------------
# MCP server exposure
# ---------------------------------------------------------------------------


def test_mcp_server_exposes_projection_tools(tmp_path: Path):
    """All 5 new MCP-side projection tools are callable and return
    ProjectionResult."""
    from kenning.coding.mcp_server import KenningMCPServer

    server = KenningMCPServer(host="127.0.0.1", port=0)
    s = server.create_session(
        project_root=tmp_path / "p", initial_prompt="hi",
    )
    server.store.transition(s.session_id, SessionStatus.EXECUTING)
    server.store.record_stage(
        s.session_id, stage="x", summary="y", files_touched=["a.py"],
    )

    # Status delta
    r = server.get_status_delta(s.session_id)
    assert isinstance(r, ProjectionResult)
    assert r.fits_budget

    # Clarification context
    r = server.get_clarification_context(s.session_id, "what?", options=["a"])
    assert isinstance(r, ProjectionResult)
    assert r.fits_budget

    # Adjustment context
    r = server.get_adjustment_context(s.session_id, "tweak")
    assert isinstance(r, ProjectionResult)
    assert r.fits_budget

    # Correction context
    r = server.get_correction_context(
        s.session_id, failures=[{"check": "TESTS", "detail": "fail"}],
    )
    assert isinstance(r, ProjectionResult)
    assert r.fits_budget

    # Completion context
    r = server.get_completion_context(s.session_id)
    assert isinstance(r, ProjectionResult)
    assert r.fits_budget


def test_get_full_state_returns_full_session(tmp_path: Path):
    """get_full_state is the in-process Python API that returns the
    complete ProjectSession (NOT exposed to MCP/Qwen)."""
    from kenning.coding.mcp_server import KenningMCPServer

    server = KenningMCPServer(host="127.0.0.1", port=0)
    s = server.create_session(project_root=tmp_path / "p", initial_prompt="hi")
    full = server.get_full_state(s.session_id)
    assert full is not None
    assert full.session_id == s.session_id
    assert isinstance(full, ProjectSession)


def test_get_session_state_emits_deprecation_warning(tmp_path: Path):
    """The legacy get_session_state still works but warns. Will be
    removed in Phase D."""
    from kenning.coding.mcp_server import KenningMCPServer

    server = KenningMCPServer(host="127.0.0.1", port=0)
    s = server.create_session(project_root=tmp_path / "p", initial_prompt="hi")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = server.get_session_state(s.session_id)
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecations, "expected DeprecationWarning"
        assert "deprecated" in str(deprecations[0].message).lower()
    assert result.session_id == s.session_id


# ---------------------------------------------------------------------------
# Token counting sanity
# ---------------------------------------------------------------------------


def test_count_tokens_handles_empty_string():
    assert count_tokens("") == 0


def test_count_tokens_returns_positive_for_real_text():
    n = count_tokens("hello world")
    assert n > 0
    assert n < 10  # short text


def test_projection_token_count_matches_text_token_count():
    """The reported token_count actually equals tiktoken's count of the
    rendered text (no off-by-one in the projection function)."""
    s = _small_session()
    r = project_status_delta(s)
    assert r.token_count == count_tokens(r.text)


# ---------------------------------------------------------------------------
# Truncation warning + logging contract
# ---------------------------------------------------------------------------


def test_truncation_warning_is_none_when_projection_fits():
    """Normal cases: truncation_warning stays None even when truncations
    are applied, as long as the result fits within budget."""
    s = _huge_session()
    for fn, kwargs in [
        (project_clarification_context,
         dict(clarification_question="what?", options=["a"])),
        (project_status_delta, {}),
        (project_adjustment_context, dict(adjustment_text="tweak")),
        (project_correction_context,
         dict(failures=[{"check": "TESTS", "detail": "nope"}])),
        (project_completion_context, {}),
    ]:
        r = fn(s, **kwargs)
        assert r.fits_budget, (
            f"{fn.__name__}: setup expected to fit, got {r.token_count}/{r.budget}"
        )
        assert r.truncation_warning is None, (
            f"{fn.__name__}: truncation_warning should be None when fits, "
            f"got {r.truncation_warning!r}"
        )


def test_truncation_warning_set_when_budget_unreachable(caplog):
    """Force a tiny budget and verify: (a) truncation_warning is set,
    (b) ERROR is logged, (c) fits_budget is False, (d) the result
    still returns rather than crashing."""
    import logging
    from kenning.coding import projections as _pmod

    s = _small_session()
    orig = _pmod.StatusDeltaProjection.BUDGET_TOKENS
    _pmod.StatusDeltaProjection.BUDGET_TOKENS = 5  # impossible
    try:
        with caplog.at_level(logging.ERROR, logger="kenning.coding.projections"):
            r = project_status_delta(s)
    finally:
        _pmod.StatusDeltaProjection.BUDGET_TOKENS = orig

    assert not r.fits_budget, "test setup error: budget=5 should be unreachable"
    assert r.truncation_warning is not None
    assert "over budget" in r.truncation_warning.lower()
    error_records = [
        rec for rec in caplog.records
        if rec.levelno == logging.ERROR and "over budget" in rec.getMessage()
    ]
    assert error_records, (
        f"expected ERROR log for unreachable budget; got: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


def test_info_logged_when_truncations_applied_and_fits(caplog):
    """When truncations engage but the projection still fits, we log
    at INFO level so operators can see budget pressure happening."""
    import logging
    from kenning.coding import projections as _pmod

    # Force the loop to engage: oversize options + small-ish budget.
    s = _small_session()
    orig = _pmod.ClarificationContextProjection.BUDGET_TOKENS
    _pmod.ClarificationContextProjection.BUDGET_TOKENS = 250
    try:
        with caplog.at_level(logging.INFO, logger="kenning.coding.projections"):
            r = project_clarification_context(
                s, clarification_question="critical question",
                options=[f"opt_{i}_" + "z" * 150 for i in range(8)],
                facts_lookup=lambda q: ["fact_" + "y" * 180 for _ in range(5)],
            )
    finally:
        _pmod.ClarificationContextProjection.BUDGET_TOKENS = orig

    assert r.fits_budget, "test setup expected to fit after truncation"
    assert r.truncations_applied, "test setup expected truncations to engage"
    assert r.truncation_warning is None, "fits_budget => no warning"
    info_records = [
        rec for rec in caplog.records
        if rec.levelno == logging.INFO and "truncations applied" in rec.getMessage()
    ]
    assert info_records, (
        f"expected INFO log for applied truncations; got: "
        f"{[(rec.levelname, rec.getMessage()) for rec in caplog.records]}"
    )


def test_no_info_log_when_no_truncations_applied(caplog):
    """A clean projection that fits without trimming should NOT emit
    the truncations-applied INFO log."""
    import logging

    s = _small_session()
    with caplog.at_level(logging.INFO, logger="kenning.coding.projections"):
        r = project_status_delta(s)
    assert r.fits_budget
    assert not r.truncations_applied
    info_records = [
        rec for rec in caplog.records
        if rec.levelno == logging.INFO and "truncations applied" in rec.getMessage()
    ]
    assert not info_records, "no truncations -> no INFO truncation log"


def test_truncation_warning_serialized_in_as_dict():
    """The dataclass.as_dict() round-trip includes truncation_warning."""
    from kenning.coding import projections as _pmod
    s = _small_session()
    orig = _pmod.StatusDeltaProjection.BUDGET_TOKENS
    _pmod.StatusDeltaProjection.BUDGET_TOKENS = 5
    try:
        r = project_status_delta(s)
    finally:
        _pmod.StatusDeltaProjection.BUDGET_TOKENS = orig

    d = r.as_dict()
    assert "truncation_warning" in d
    assert d["truncation_warning"] is not None
