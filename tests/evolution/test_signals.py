"""Tests for ultron.evolution.signals -- local signal extraction +
history-aware post-processing. All hermetic (pure functions)."""

from __future__ import annotations

from ultron.evolution import signals as S
from ultron.evolution.models import BlastRadius, EvolutionEvent, Outcome, OutcomeStatus


def _event(*, intent="", sigs=(), status="success", files=1, lines=1, gene=""):
    return {
        "intent": intent,
        "signals": list(sigs),
        "outcome": {"status": status, "score": 0.5},
        "blast_radius": {"files": files, "lines": lines},
        "gene": gene,
    }


# --- taxonomy ---------------------------------------------------------------


def test_opportunity_signals_count_and_membership():
    assert len(S.OPPORTUNITY_SIGNALS) == 17
    assert "user_feature_request" in S.OPPORTUNITY_SIGNALS
    assert "force_innovation_after_repair_loop" in S.OPPORTUNITY_SIGNALS
    assert "explore_opportunity" in S.OPPORTUNITY_SIGNALS


def test_signal_profiles_present():
    assert set(S.SIGNAL_PROFILES) == {
        "perf_bottleneck",
        "capability_gap",
        "user_feature_request",
        "user_improvement_suggestion",
        "recurring_error",
        "tool_bypass",
        "evolution_stagnation_detected",
    }


def test_signal_base():
    assert S.signal_base("errsig:TypeError: boom") == "errsig"
    assert S.signal_base("log_error") == "log_error"
    assert S.signal_base("ban_gene:gene_x") == "ban_gene"


# --- layer 2: keyword scoring ----------------------------------------------


def test_single_weak_keyword_does_not_fire_perf_bottleneck():
    assert "perf_bottleneck" not in S.extract_keyword_signals("it is a bit slow")


def test_accumulated_weak_keywords_fire_perf_bottleneck():
    out = S.extract_keyword_signals("everything is so slow and laggy with delay today")
    assert "perf_bottleneck" in out


def test_keyword_capability_gap():
    out = S.extract_keyword_signals("it is not supported and there is no way to do it")
    assert "capability_gap" in out


# --- layer 1: regex ---------------------------------------------------------


def test_regex_log_error_and_errsig():
    out = S.extract_regex_signals("TypeError: boom happened here")
    assert "log_error" in out
    assert any(s.startswith("errsig:") for s in out)


def test_regex_recurring_error():
    corpus = "TypeError: boom\nTypeError: boom\nTypeError: boom\n"
    out = S.extract_regex_signals(corpus)
    assert "recurring_error" in out
    assert any(s.startswith("recurring_errsig(") for s in out)


def test_regex_memory_missing():
    assert "memory_missing" in S.extract_regex_signals("MEMORY.md missing on disk")


def test_regex_perf_bottleneck_timeout_and_slow():
    assert "perf_bottleneck" in S.extract_regex_signals("the request timeout was slow")


def test_regex_path_escape():
    assert "path_outside_workspace" in S.extract_regex_signals("reading ../../../etc/passwd")


def test_regex_windows_shell_incompatible_only_on_windows():
    corpus = "I ran pgrep python to find it"
    assert "windows_shell_incompatible" in S.extract_regex_signals(corpus, is_windows=True)
    assert "windows_shell_incompatible" not in S.extract_regex_signals(corpus, is_windows=False)


def test_regex_high_tool_usage_and_repeated_exec():
    corpus = "".join("[TOOL: exec]\n" for _ in range(12))
    out = S.extract_regex_signals(corpus)
    assert "high_tool_usage:exec" in out
    assert "repeated_tool_usage:exec" in out


def test_regex_tool_bypass():
    assert "tool_bypass" in S.extract_regex_signals("$ curl https://example.com/x")


# --- multilingual user requests --------------------------------------------


def test_user_feature_request_english_with_snippet():
    out = S.extract_user_requests("Hello. Please add a dark mode toggle to the UI. Thanks.")
    fr = [s for s in out if s.startswith("user_feature_request:")]
    assert fr
    assert "dark mode" in fr[0]


def test_user_improvement_suggestion_english():
    out = S.extract_user_requests("You should make it faster overall.")
    assert any(s.startswith("user_improvement_suggestion:") for s in out)


def test_user_request_chinese_trigger():
    out = S.extract_user_requests("我想要一个新功能")
    assert any(s.startswith("user_feature_request:") for s in out)


def test_snippet_truncation():
    long_request = "Please add " + ("x" * 500)
    out = S.extract_user_requests(long_request)
    fr = [s for s in out if s.startswith("user_feature_request:")][0]
    payload = fr.split(":", 1)[1]
    assert len(payload) <= S.SNIPPET_MAX_CHARS


# --- merge ------------------------------------------------------------------


def test_merge_dedups_exact_but_keeps_distinct_payloads():
    merged = S.merge_signals(
        ["log_error", "errsig:a"],
        ["log_error", "errsig:b"],
    )
    assert merged.count("log_error") == 1
    assert "errsig:a" in merged and "errsig:b" in merged


# --- history analysis -------------------------------------------------------


def test_analyze_consecutive_repair_count():
    events = [
        _event(intent="optimize"),
        _event(intent="repair"),
        _event(intent="repair"),
        _event(intent="repair"),
    ]
    a = S.analyze_recent_history(events)
    assert a.consecutive_repair_count == 3


def test_analyze_consecutive_empty_and_failure():
    events = [
        _event(files=1, lines=1, status="success"),
        _event(files=0, lines=0, status="failed"),
        _event(files=0, lines=0, status="failed"),
    ]
    a = S.analyze_recent_history(events)
    assert a.consecutive_empty_cycles == 2
    assert a.consecutive_failure_count == 2
    assert a.empty_cycle_count == 2
    assert a.recent_failure_count == 2


def test_analyze_failure_ratio_and_top_failing_gene():
    events = [
        _event(status="failed", gene="gene_bad"),
        _event(status="failed", gene="gene_bad"),
        _event(status="failed", gene="gene_other"),
        _event(status="success", gene="gene_good"),
    ]
    a = S.analyze_recent_history(events)
    assert a.recent_failure_ratio == 0.75
    assert a.top_failing_gene == "gene_bad"


def test_analyze_suppressed_signals():
    events = [_event(sigs=["perf_bottleneck"]) for _ in range(3)]
    a = S.analyze_recent_history(events)
    assert "perf_bottleneck" in a.suppressed_signals


def test_analyze_accepts_evolution_event_objects():
    ev = EvolutionEvent(
        id="evt_1",
        intent="repair",
        signals=["log_error"],
        outcome=Outcome(status=OutcomeStatus.FAILED, score=0.0),
        blast_radius=BlastRadius(files=0, lines=0),
        genes_used=["gene_x"],
    )
    a = S.analyze_recent_history([ev])
    assert a.consecutive_failure_count == 1
    assert a.consecutive_empty_cycles == 1


# --- post-processing --------------------------------------------------------


def test_post_cosmetic_dropped_when_actionable_present():
    out = S.apply_post_processing(["memory_missing", "log_error"], S.RecentHistoryAnalysis())
    assert "log_error" in out
    assert "memory_missing" not in out


def test_post_cosmetic_kept_when_alone():
    out = S.apply_post_processing(["memory_missing"], S.RecentHistoryAnalysis())
    assert out == ["memory_missing"]


def test_post_suppression_injects_stagnation_when_empties():
    analysis = S.RecentHistoryAnalysis(suppressed_signals=frozenset({"log_error"}))
    out = S.apply_post_processing(["log_error"], analysis)
    assert "evolution_stagnation_detected" in out
    assert "stable_success_plateau" in out
    assert "log_error" not in out


def test_post_repair_loop_strips_errors_and_forces_innovation():
    analysis = S.RecentHistoryAnalysis(consecutive_repair_count=3)
    out = S.apply_post_processing(["log_error", "errsig:x", "perf_bottleneck"], analysis)
    assert "log_error" not in out
    assert not any(s.startswith("errsig:") for s in out)
    assert "perf_bottleneck" in out
    assert "repair_loop_detected" in out
    assert "force_innovation_after_repair_loop" in out


def test_post_empty_cycle_loop():
    analysis = S.RecentHistoryAnalysis(empty_cycle_count=4)
    out = S.apply_post_processing(["perf_bottleneck"], analysis)
    assert "empty_cycle_loop_detected" in out


def test_post_saturation_and_steady_state():
    out3 = S.apply_post_processing([], S.RecentHistoryAnalysis(consecutive_empty_cycles=3))
    assert "evolution_saturation" in out3
    assert "explore_opportunity" in out3
    assert "force_steady_state" not in out3
    out5 = S.apply_post_processing([], S.RecentHistoryAnalysis(consecutive_empty_cycles=5))
    assert "force_steady_state" in out5


def test_post_failure_streak_and_ban_gene():
    a3 = S.RecentHistoryAnalysis(consecutive_failure_count=3)
    out3 = S.apply_post_processing(["perf_bottleneck"], a3)
    assert "consecutive_failure_streak_3" in out3
    assert "failure_loop_detected" not in out3
    a5 = S.RecentHistoryAnalysis(consecutive_failure_count=5, top_failing_gene="gene_bad")
    out5 = S.apply_post_processing(["perf_bottleneck"], a5)
    assert "failure_loop_detected" in out5
    assert "ban_gene:gene_bad" in out5


def test_post_high_failure_ratio():
    analysis = S.RecentHistoryAnalysis(recent_failure_ratio=0.8, recent_intents=("repair",))
    out = S.apply_post_processing(["perf_bottleneck"], analysis)
    assert "high_failure_ratio" in out
    assert "force_innovation_after_repair_loop" in out


def test_post_empty_fallback():
    out = S.apply_post_processing([], S.RecentHistoryAnalysis())
    assert out == ["stable_success_plateau"]


# --- end-to-end -------------------------------------------------------------


def test_extract_signals_end_to_end_repair_loop():
    corpus = "TypeError: boom\nTypeError: boom\nTypeError: boom"
    events = [_event(intent="repair") for _ in range(3)]
    out = S.extract_signals(recent_session_transcript=corpus, recent_events=events)
    # error present in corpus but repair-loop strips it and forces innovation
    assert "log_error" not in out
    assert "repair_loop_detected" in out
    assert "force_innovation_after_repair_loop" in out


def test_extract_signals_returns_fallback_when_quiet():
    out = S.extract_signals(recent_session_transcript="all good, nothing to report")
    assert out  # never empty
    assert "stable_success_plateau" in out


def test_has_opportunity_signal():
    assert S.has_opportunity_signal(["log_error"]) is True
    assert S.has_opportunity_signal(["perf_bottleneck"]) is True
    assert S.has_opportunity_signal(["stable_success_plateau"]) is False
    assert S.has_opportunity_signal(["memory_missing"]) is False
