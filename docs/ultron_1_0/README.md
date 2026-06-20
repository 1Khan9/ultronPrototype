# Ultron 1.0 — Development Context Directory

This directory is the **single source of truth** for the Ultron 1.0 evolution (the
"route-everything-through-the-LLM, optional-wakeword, always-listening" pivot). It is
maintained continuously so that no information is lost across context compaction, and so
that reasoning does not degrade as the conversation grows. **Reground here frequently.**

> Binding rule (see `feedback_ultron_1_0_process.md` in memory): log from the first action,
> reground from these docs before major decisions, never let context loss degrade quality.

## Layout

| Folder | Purpose |
|---|---|
| `00_process_log/` | Chronological session logs. One file per working session/date. Every phase, decision, command, and result is appended here as it happens. |
| `01_recon/` | Outputs of the two codebase-scanning boards: pipeline data-flow maps, module inventories, routing/normalization/semantics maps, test-infra inventory. The ground truth about *what exists today*. |
| `02_research/` | All deep-research findings (mine + the agent board), uncut, with sources and synthesis. The ground truth about *what's possible / frontier*. |
| `03_plan/` | The comprehensive Ultron 1.0 architecture, framework, and implementation roadmap derived from recon + research. The ground truth about *what we will build*. |
| `04_implementation/` | Per-batch implementation logs: what changed, why, test results, commits, regressions found+fixed. The ground truth about *what we have built so far*. |
| `05_testing/` | Test-harness design, the enhanced MP3 battery spec, trace-format spec, and per-run reports. |
| `06_decisions/` | Architecture Decision Records (ADRs). One file per significant, hard-to-reverse decision, with context/options/decision/consequences. |

## Status snapshot

See `00_process_log/STATUS.md` for the always-current high-level status (phase, last green
test run, last commit, open risks). Update it at every phase boundary and every commit.

## Version / rewind

Every meaningful increment is a git commit on branch `claude/infallible-kepler-0a865d`
(worktree off `main`). Tags mark phase boundaries (`u1.0-phaseN-*`). To rewind, check out the
tag or the prior commit. The legacy Ultron 0.1 / 0.1.1 standalone builds on `E:\Ultron-0.1*`
remain untouched as ultimate fallbacks.
