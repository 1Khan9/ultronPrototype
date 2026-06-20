# Changelog

All notable changes to Kenning / Ultron. Dates are ISO-8601. The dev line is **Ultron 1.0** — every
behavioral change ships behind a flag (default **off**) so the stable shipped behavior is unchanged until an
increment is proven regression-clean against the frozen control baseline.

## [ultron-1.0] — 2026-06-20

The route-everything-through-an-8B pipeline is feature-complete behind its flags (`KENNING_U1_LLM_ROUTE` /
`addressing.always_listening`, default off). Live calibration of the gate thresholds and the latency pass
remain before the flags flip on by default.

### Added
- **Always-listening intent gate wired into the run loop.** Behind `addressing.always_listening` (default off,
  env override `KENNING_ALWAYS_LISTENING`), the loop can listen perpetually (no wake word) and routes every
  finalized transcript through a four-class intent gate — relay-to-team / private-reply / local-command /
  ignore — fail-closed to ignore on ambiguity. When off, the run loop is byte-identical to the wake-word path.
- **Private "me-only" reply routing.** A transcript the gate classifies as a private question is answered on
  the desktop channel (the player's own speakers — never the team mic), via the lean private-reply prompt.
- **Labeled audio end-to-end battery.** `scripts/relay_test/audio_corpus/u1_battery.py` +
  `run_corpus.py --u1` + `u1_score.py` drive a labeled corpus (positive / ignore / batched, with wake-free
  clips for the always-listening path) through the real pipeline and score scenario accuracy, ignore
  suppression, and a hallucination-pressure subset. Generator + scorer logic is unit-tested headless.

### Changed
- The verbosity command (`no` / `low` / `high` flavor) and the route-all-through-8B relay path are gated and
  default-off; the proven deterministic relay path still ships and is the active default.

### Notes
- All Ultron 1.0 behavior is flag-gated and default-off, so the runtime behavior of a standard boot is unchanged.
- Stable restorable baselines remain `ultron-0.1` (`816df7c`) and `ultron-0.1.1`.
