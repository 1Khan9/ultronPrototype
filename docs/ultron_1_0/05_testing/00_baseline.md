# Ultron 1.0 — Pre-change test BASELINE (regression yardstick)

**Captured:** 2026-06-20 at pristine docs-only commit `f236d1b` (NO source changes yet).
**Env:** `PYTHONPATH=<worktree>/src`, `KENNING_ROUTER_WAIT_SECONDS=0`, main venv
`C:\STC\ultronPrototype\.venv\Scripts\python.exe`. Command: `python -m pytest -q -p no:cacheprovider`.
Full log: `baseline_pretest.txt`.

## Result: **10966 passed · 22 failed · 39 skipped** (145.24s)

(README badge "10 failing" is stale for this branch — the true baseline on `6064e5f` is 22 fails.)

**Regression rule:** after any change, re-run the same suite/slice in the same env. A failure is a
**regression ONLY if it is NOT in the 22 below**. The 8 relay/normalizer fails are in my work area and
confirmed deterministic (reproduce in isolation); the LLM-routing pivot is expected to FIX several
(e.g. "kill the enemy team" false-relay) — track that as improvement, not regression.

## The 22 pre-existing failures (frozen baseline)

### A. Relay / normalizer (8) — MY WORK AREA, deterministic (re-confirmed in isolation)
1. `tests/audio/test_corpus_audit_fixes.py::TestC6Disfluency::test_value_swap_keeps_last_buy`
2. `tests/audio/test_corpus_audit_fixes.py::TestC4ReportedDirective::test_say_to_delivers_literal_payload`
3. `...::TestFlavorOffSets::test_flavor_off_pool_member[Sage told you to stop-pool5-Sage]`
4. `...::TestSayHelloDefaultAndStop::test_stop_command_deterministic[Sage told you to stop]`
5. `...::test_stop_command_deterministic[Sage told me to stop]`
6. `...::test_stop_command_deterministic[my Sage told me to stop responding]`
7. `...::TestMangledTeamLeadNoDeterminer::test_real_phrases_not_hijacked[kill the enemy team]`
8. `...::test_real_phrases_not_hijacked[push with the team]`

### B. Env / infra-sensitive (14) — outside my work area (likely worktree-via-PYTHONPATH / config.yaml / optional-dep sensitivity; do NOT attribute to my changes)
9. `tests/error_recovery/test_audio_failures.py::test_whisper_transcribe_failure_returns_empty`
10. `tests/error_recovery/test_audio_failures.py::test_whisper_subsequent_transcribe_works_after_failure`
11. `tests/test_main_single_instance.py::test_duplicate_exits_3_without_constructing_orchestrator`
12. `tests/test_main_single_instance.py::test_lock_released_in_finally_on_happy_path`
13. `tests/test_main_single_instance.py::test_lock_released_when_run_raises`
14. `tests/test_main_single_instance.py::test_lock_released_on_missing_model`
15. `tests/test_orchestrator_background_summary.py::test_loader_builds_summarizer_when_enabled`
16. `tests/test_orchestrator_background_summary.py::test_loader_summarizer_calls_llm_isolated`
17. `tests/test_orchestrator_background_summary.py::test_recent_turns_fn_fail_open_when_memory_raises`
18. `tests/test_orchestrator_evolution_wiring.py::TestLoadEvolution::test_enabled_real_round_trip`
19. `tests/test_speculative_llm.py::TestLLMEngineHistoryDefer::test_record_history_true_records_turn`
20. `tests/test_speculative_llm.py::TestLLMEngineHistoryDefer::test_record_history_false_skips_auto_record`
21. `tests/test_stt_engine_swap.py::test_stt_default_engine_is_auto`
22. `tests/test_web_search_readers.py::test_playwright_reader_fetch_returns_none_when_unavailable`

> NOTE: the Group-B fails may be artifacts of running the worktree code through the main checkout's
> venv (editable install points elsewhere; some tests read the live `config.yaml` or optional deps).
> They are STABLE across runs, so they serve as a valid control. If time permits during M0, I'll
> confirm a few against the main checkout to separate "branch-real" from "env-artifact" — but either
> way they are the frozen control set for regression detection.
