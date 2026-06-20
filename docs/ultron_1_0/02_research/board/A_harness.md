# E2E Harness Attach Points & Wake-Sample Location — Validation

**Validator:** Sonnet 4.6, 2026-06-20. Branch `claude/infallible-kepler-0a865d` tip `dfadb89`.
Sources read: `scripts/relay_test/audio_corpus/{gen_commands.py,inject.py,run_corpus.py,render_review.py}`,
`scripts/relay_test/{trace_corpus_full.py,corpus.py,corpus_packs.py,battery_cmds.txt}`,
`src/kenning/audio/capture.py`, `src/kenning/pipeline/orchestrator.py` (selected sections),
`docs/ultron_1_0/01_recon/raw/boardA_test_infra.md`, `docs/ultron_1_0/01_recon/00_codebase_map.md`.

---

## Confirmed attach points (path:line)

### 1. InjectableCapture — the mic swap seam

| Symbol | Path:line | Status |
|---|---|---|
| `class InjectableCapture(AudioCapture)` | `scripts/relay_test/audio_corpus/inject.py:26` | CONFIRMED |
| `InjectableCapture.__init__` — `_pending: deque`, `_frame_s`, `_silence` | `inject.py:27-34` | CONFIRMED |
| `InjectableCapture.start()` / `.stop()` — no-ops (never open real stream) | `inject.py:37-40` | CONFIRMED |
| `InjectableCapture.feed_pcm(pcm)` — enqueue 256-sample blocks | `inject.py:44-61` | CONFIRMED |
| `InjectableCapture.get_chunk()` — pop pending or return silence, sleep `~16ms` | `inject.py:75-80` | CONFIRMED |
| `InjectableCapture.drain()` — clears `self._queue` (the parent's `queue.Queue`, NOT `_pending`) | `inject.py:67-72` | CONFIRMED — drains the base-class queue only; `_pending` survives drain, correct by design |
| `AudioCapture._queue: queue.Queue[np.ndarray]` (parent) | `src/kenning/audio/capture.py:52` | CONFIRMED — `drain()` in InjectableCapture correctly accesses `.mutex` / `.queue.clear()` on the inherited queue.Queue |
| `orch.audio` assignment — replaced after `Orchestrator()` is built, before `run()` | `run_corpus.py:113-114` | CONFIRMED |
| `Orchestrator.__init__` creates `self.audio = AudioCapture()` | `src/kenning/pipeline/orchestrator.py:513` | CONFIRMED — the swap `orch.audio = inj` happens after `__init__` completes, safe |

### 2. Orchestrator boot + run seam

| Symbol | Path:line | Status |
|---|---|---|
| `Orchestrator.run()` — main event loop entry | `orchestrator.py:5790` | CONFIRMED |
| `self.audio.start()` called at run() top | `orchestrator.py:5795` | CONFIRMED — InjectableCapture.start() is a no-op, safe |
| Boot-detection: poll `kenning.log` for `"waiting_for_wake_word"` or `"loop:iteration_start"` | `run_corpus.py:154` | CONFIRMED — both strings appear in the actual log flow |
| `set_testing_mode_active(True)` before `orch.run()` | `run_corpus.py:115` | CONFIRMED |
| `KENNING_ALLOW_MULTIPLE_INSTANCES=1` env guard | `run_corpus.py:52` | CONFIRMED |

### 3. Turn-completion signal

| Symbol | Path:line | Status |
|---|---|---|
| `_trace_turn_flow()` — emits to `logs/usage_trace.jsonl` | `orchestrator.py:3380` | CONFIRMED |
| `run_corpus.py` polls `usage_trace.jsonl` line count (`_trace_count()`) + Kokoro quiescence `>1.8s` | `run_corpus.py:130-183` | CONFIRMED |
| `_hooked` — class-level `KokoroSpeech._synthesize` monkeypatch; captures response PCM + timestamps | `run_corpus.py:93-104` | CONFIRMED |
| `usage_trace.jsonl` path: `_ROOT / "logs" / "usage_trace.jsonl"` | `run_corpus.py:128` | NOTE: `_ROOT` resolves to the worktree root; `logs/usage_trace.jsonl` does NOT exist in the worktree today (only `logs/relay_test/` is present); the main repo has it. For the harness to work from the worktree, `logs/` must exist or be pre-created. See Risks. |

### 4. gen_commands.py — composite clip generator

| Symbol | Path:line | Status |
|---|---|---|
| `_ROOT` computation: `_HERE.parents[2]` from `scripts/relay_test/audio_corpus/` | `gen_commands.py:37` | CONFIRMED — resolves to worktree root |
| Wake samples glob: `_ROOT / "training/crosscheck_ultron/*.wav"` | `gen_commands.py:93` | CONFIRMED path logic — see Wake Sample Location below |
| `WAKE_RE = re.compile(r"^\s*ultron\b[\s,]*", re.IGNORECASE)` | `gen_commands.py:46` | CONFIRMED — strips "Ultron," / "Ultron " prefix from body |
| `LEAD_SILENCE_S=0.5`, `TAIL_SILENCE_S=1.3`, `GAP_COMMA_S=0.25`, `GAP_RUNON_S=0.06` | `gen_commands.py:41-45` | CONFIRMED |
| Exit code 2 on empty wakes: `print("!! no crosscheck_ultron wake samples found"); return 2` | `gen_commands.py:99-100` | CONFIRMED |
| Composite: `[lead] + wake[i%N] + [gap] + body_f32 + [tail]` | `gen_commands.py:121` | CONFIRMED |

### 5. trace_corpus_full.py — text-level 25k tracer

| Symbol | Path:line | Status |
|---|---|---|
| `build_corpus(seed, target)` → 25k Case objects | `trace_corpus_full.py:154` | CONFIRMED |
| `correct_callout_stt(text)` → `stt1` | `trace_corpus_full.py:161` | CONFIRMED |
| `normalize_command(text)` → `norm2` | `trace_corpus_full.py:165` | CONFIRMED |
| `match_relay_command(norm2)` → `cmd` | `trace_corpus_full.py:171` | CONFIRMED |
| `_snap_only(cmd)` → `snap` (calls `RS._as_snap_callout(cmd, None, flavor=False)`) | `trace_corpus_full.py:70-80` | CONFIRMED |
| `build_relay_line(cmd, llm=None, rephrase=False)` → `final` (NO live LLM calls) | `trace_corpus_full.py:199` | CONFIRMED |
| `_router_decision(text)` — optional, requires embedder sidecar; gated by `TRACE_WITH_ROUTER` | `trace_corpus_full.py:60-68, 131-145` | CONFIRMED |

### 6. relay_speech.py and orchestrator key line refs (verified against live source)

| Symbol | Claimed line | Actual line | Status |
|---|---|---|---|
| `match_relay_command()` | recon: 1704 | 1704 | CONFIRMED |
| `build_relay_line()` | recon: 6012 | 6012 | CONFIRMED |
| `_as_snap_callout()` | — | 4327 | CONFIRMED |
| `SNAP_REGISTRY` first use | recon: 2801 | 2801 | CONFIRMED |
| `TARGET_SNAP_REGISTRY` first use | recon: 2849 | 2849 | CONFIRMED |
| `normalize_command()` | recon: 975 | 975 | CONFIRMED |
| `_trace_turn_flow()` | recon: 3380 | 3380 | CONFIRMED |
| `_is_relay_command()` | recon: 3126 | 3126 | CONFIRMED |
| `_maybe_handle_relay_speech()` | recon: 3428 | 3428 | CONFIRMED |
| `_gaming_conversational_prompt()` | recon: 9006 | 9006 | CONFIRMED |
| `_respond()` | recon: 8756 | 8756 | CONFIRMED |
| `_build_response_stream()` | recon: 10031 | 10031 | CONFIRMED |
| `self.audio = AudioCapture()` | recon: ~513 | 513 | CONFIRMED |
| `Orchestrator.run()` | recon: 5790 | 5790 | CONFIRMED |
| `harness.py GAMING_PRESET` | recon: 324 | 324 | CONFIRMED |
| `harness.py _load_llm()` | recon: 327 | 327 | CONFIRMED |

### 7. corpus_packs.py discriminator classification

| Symbol | Path:line | Status |
|---|---|---|
| `_QUESTION_PACKS` (teammate-to-Ultron) | `corpus_packs.py:39` | CONFIRMED |
| `_NEGATIVE_PACKS` (false-relay gate) | `corpus_packs.py:45` | CONFIRMED |
| `_VERBATIM_PACKS` | `corpus_packs.py:34` | CONFIRMED |
| `_all_pack_names()` — auto-discovers `vocab_packs/*.py` | `corpus_packs.py:50` | CONFIRMED |

---

## Wake-sample directory — location & availability

### Where it is

`training/crosscheck_ultron/` **exists in the main repo checkout only**:
- Path: `C:\STC\ultronPrototype\training\crosscheck_ultron\`
- File count: **300 WAV files** (`0.wav` … `299.wav`-ish, numerically named)
- Sample rate: unknown from inspection, resampled to 16kHz by `gen_commands.py:_to_16k_f32`
- Wake fire rate on the live openWakeWord model: ~0.94 (documented in gen_commands.py and README)

### Why it is absent from the worktree

`.gitignore` line 81: `*.wav` blanket-ignores all WAV files repo-wide. The `training/crosscheck_ultron/` directory itself is also explicitly listed at `.gitignore:178`. Both rules apply. Since these are untracked local data blobs (~300 real-human speech recordings), they exist only in the main checkout and are never synced to worktrees via git.

### What gen_commands.py resolves

`gen_commands.py:37` computes `_ROOT = _HERE.parents[2]` where `_HERE` is the `audio_corpus/` directory. From a worktree run, `_ROOT` = `C:\STC\ultronPrototype\.claude\worktrees\infallible-kepler-0a865d`. The glob therefore targets:
```
C:\STC\ultronPrototype\.claude\worktrees\infallible-kepler-0a865d\training\crosscheck_ultron\*.wav
```
This directory does **not exist** in the worktree. `gen_commands.py` exits with code 2 if the glob returns empty.

### Resolution options for worktree use

1. **Run gen_commands.py from the main checkout** (`C:\STC\ultronPrototype\scripts\relay_test\audio_corpus\gen_commands.py`) — `_ROOT` will resolve to the main checkout where crosscheck_ultron exists. Generated `out/` artifacts live under `scripts/relay_test/audio_corpus/out/` of the main checkout.
2. **Symlink** `training/crosscheck_ultron` from worktree → main checkout (PowerShell: `New-Item -ItemType SymbolicLink`). Requires admin on Windows.
3. **Copy the 300 WAVs** into the worktree. ~few MB; a one-time setup step.
4. **Override via CLI arg**: `gen_commands.py` accepts `battery` and `outdir` positional args, but the wake-sample path is hardcoded to `_ROOT / "training/crosscheck_ultron/*.wav"` with no CLI override. Would require a one-line patch: `ap.add_argument("--wake-dir", default=str(_ROOT / "training/crosscheck_ultron"))`.

---

## Corrections to the recon/plan

1. **`logs/usage_trace.jsonl` path is worktree-relative but the file only exists in the main checkout.**
   `run_corpus.py:128` sets `usage_trace = _ROOT / "logs" / "usage_trace.jsonl"` where `_ROOT` is the worktree root. The worktree's `logs/` directory contains only `logs/relay_test/` (a `.gitkeep` placeholder). The live `usage_trace.jsonl` is under `C:\STC\ultronPrototype\logs\`. If `run_corpus.py` is invoked from the worktree, `_trace_count()` will never see a new row (file absent) and every command will time out as `NR`.
   Mitigation: run the harness from the main checkout, or add a `--trace-path` flag, or pre-create `logs/` in the worktree (orchestrator will create the file on boot if `testing_mode=True` and the directory exists).

2. **`InjectableCapture.drain()` accesses the parent's `self._queue` (a `queue.Queue`), not `self._pending`.**
   This is correct and intentional (comment in inject.py:67 says exactly this), but the recon doc description could be misread as "drains all pending audio." The actual behavior: `drain()` clears the base-class queue backlog only; `self._pending` (the harness feed buffer) is preserved. This is the right design — the orchestrator calls `audio.drain()` at turn start to flush stale real-mic audio, but the harness's pre-loaded command frames must survive.

3. **`harness.py GAMING_PRESET` is hardcoded to `"llama-3.2-3b-abliterated"` (not the 8B).**
   For u1.0 testing, `harness.py:324` must be updated to `"josiefied-qwen3-8b"` or made a CLI argument. The `_load_llm()` function at line 327 already accepts a `preset` parameter; only the default constant needs changing.

4. **`trace_corpus_full.py` does not emit LLM prompt or `<think>` trace fields** (codebase map §8 gap).
   Confirmed by inspection: the tracer calls `build_relay_line(cmd, llm=None, rephrase=False)` which skips the LLM path entirely. For u1.0 where the LLM is the primary author, either (a) the tracer must be extended to pass `llm=real_8B`, or (b) a new `trace_corpus_u10.py` variant is needed that emits `prompt_template_id`, `llm_system`, `llm_user`, `llm_output`, `<think>` stripped content, and `llm_call_count` per case.

5. **`corpus_packs.py` comment says "~29k unique payloads" and `build_corpus` caps to 20,000** — but environment variable `RELAY_CORPUS_TARGET` defaults to `25000` and the docstring mentions `25k`. The actual cap is whichever `target` is passed (default 25,000 for `trace_corpus_full.py`). The "20,000" in the `corpus_packs.py` module docstring is stale. Not a correctness issue but a documentation mismatch.

6. **The recon table `build_corpus_10k` = alias to `build_corpus(target=25000)`** is confirmed accurate. The name is a historic misnomer; the function always targets 25k.

---

## Risks & gotchas for the implementation

### R1 — CRITICAL: Wake samples absent from worktree (blocks gen_commands.py)
Any run of `gen_commands.py` from inside the worktree will exit 2 immediately. The u1.0 harness extension work (Phase 5) must either (a) run from the main checkout, (b) add a `--wake-dir` CLI arg with a default that points to the main checkout's crosscheck dir, or (c) copy/symlink the 300 WAVs. Recommended: add the CLI arg — one line, backward-compatible, no state duplication.

### R2 — CRITICAL: `logs/` directory not present in worktree
`run_corpus.py` polls `logs/usage_trace.jsonl` and `logs/kenning.log`. The orchestrator writes to those paths at runtime. If the `logs/` directory does not exist, the orchestrator will fail to create the trace file on boot. The worktree has only `logs/relay_test/.gitkeep`. Pre-creating `logs/` (mkdir) before launching is a required setup step for worktree-based harness runs.

### R3 — Turn-completion detector is racey and will be worse with 8B on CPU
`run_corpus.py`'s wait loop polls `usage_trace.jsonl` every 0.25s and declares completion when Kokoro has been quiescent for 1.8s. The default `turn_timeout=90s`. An 8B model on CPU with thinking enabled can easily exceed 90s for complex relay prompts. The `--turn-timeout` flag exists and should be raised to at least 300s for initial u1.0 harness runs on CPU. On GPU (RTX 4070 Ti) the 8B with q5_K_M is approximately 2-3x faster than CPU; 90s may still be tight for thinking-mode turns with long `<think>` blocks.

### R4 — `render_review.py` LLM-flag detection does not cover u1.0 route names
`render_review.py:46` flags `LLM` when `route.endswith("llm")` or `route == "conversational_llm"`. In u1.0, if all routes go through the 8B and route names are updated (e.g., `"relay_8b"`, `"snap_8b"`, `"gate_8b"`), the `LLM` flag will never fire. The flag logic needs to be updated to match the u1.0 route taxonomy, otherwise every u1.0 LLM turn will be silently unflagged.

### R5 — Short-callout TTS fidelity remains low (pre-existing, unchanged)
`am_michael @1.18x` garbles short Valorant jargon — "jett" → syllable artifacts, "sova" → "Silva". This is a pre-existing limitation documented in `README.md`. TX flags on short callouts are mostly harness artifacts. The u1.0 harness should distinguish TX flags on short callouts (≤3 content words) from TX flags on full tactical sentences when scoring — short TX is noise, long TX is a real regression.

### R6 — `InjectableCapture.get_chunk()` always returns a frame (never `None`)
The capture-stall watchdog in `orchestrator.py` fires after `_CAPTURE_STALL_TIMEOUTS=2` consecutive `get_chunk(timeout=0.5)` calls returning `None`. `InjectableCapture.get_chunk()` always returns either a pending frame or a silence frame — never `None`. The watchdog will therefore never fire during injection. This is the correct behavior for the harness. However, if a u1.0 harness extension changes the silence-return to a timeout-sensitive path, the watchdog could accidentally trigger. The existing behavior is safe; document it.

### R7 — Kokoro synth hook is class-level (global state)
`run_corpus.py:104` patches `KokoroSpeech._synthesize` as a class-level attribute. If the orchestrator constructs more than one `KokoroSpeech` instance (e.g., one for relay, one for desktop), both will be hooked. This is fine for the current harness since `_hooked` just passes through and records. For u1.0, if the 8B-authored relay path uses a different TTS voice or a different `KokoroSpeech` instance, the response capture still works correctly. No action needed, but note the global scope.

### R8 — `from inject import InjectableCapture` depends on sys.path including `_HERE`
`run_corpus.py:46` inserts `str(_HERE)` (the `audio_corpus/` dir) into `sys.path` before the Orchestrator import. This means `from inject import InjectableCapture` resolves to the local `inject.py`. If the u1.0 harness is restructured (different directory layout, or `inject.py` moved to a package), this import will break. Pin the import path explicitly or install inject.py as a package.

### R9 — `KENNING_SNAP_REGISTRY` env flag must be set for SnapRule registry to fire
The SNAP_REGISTRY path in `relay_speech.py:2801` is gated by `os.getenv("KENNING_SNAP_REGISTRY", "1")`. Default is `"1"` (on). However, any harness script that runs with `KENNING_SNAP_REGISTRY=0` will bypass all data-driven snaps and fall to the hardcoded paths. The trace output will not reflect SnapRule routing. Ensure harness invocations do not inadvertently disable this flag.

### R10 — u1.0 `Case` dataclass extension requires `corpus.py` edit and golden re-bless
Adding `intent`, `channel`, `verbosity` fields to `Case` (per codebase map §10 plan) changes the signature of `build_corpus()` and will break any existing code that constructs `Case` objects positionally. The `Case` dataclass uses `frozen=True` — adding fields with defaults is safe (keyword-only). The golden digest (`tests/data/voice_lines_golden_digest.json`) covers the voice-lines aggregate, not `Case` structure, so that gate is not at risk. But any test that constructs `Case(text, category, True, ...)` positionally will break.

---

## Concrete recommendations

1. **Add `--wake-dir` to `gen_commands.py`** (one line):
   ```python
   ap.add_argument("--wake-dir", default=str(_ROOT / "training/crosscheck_ultron"))
   ```
   Then update the glob: `glob.glob(str(Path(args.wake_dir) / "*.wav"))`. This makes the harness work from any checkout or worktree by passing the main repo path. Default behavior unchanged for main-checkout runs.

2. **Pre-create `logs/` before worktree harness runs.** Add a setup note to `audio_corpus/README.md` and/or add a `mkdir -p logs` call at the top of `run_corpus.py` before the orchestrator boots. The orchestrator itself should create the file, but only if the directory exists.

3. **Raise `--turn-timeout` to 300s for initial u1.0 CPU runs.** When the 8B is on CPU with thinking enabled, 90s is insufficient. Add a note to the README and consider making the default smarter (detect GPU vs CPU from the LLM device profile).

4. **Add u1.0 route names to `render_review.py` LLM-flag logic** before the first u1.0 corpus run. Proposed: flag `LLM` whenever `route` contains `"8b"` or `"llm"` or `"compose"` — or replace the exact-match with a set of known-LLM-route prefixes that is kept in sync with the u1.0 route taxonomy.

5. **Update `harness.py:GAMING_PRESET`** from `"llama-3.2-3b-abliterated"` to `"josiefied-qwen3-8b"` (or add a CLI `--preset` flag) before the u1.0 `rephrase` and `full` harness stages are run against the 8B.

6. **Extend `trace_corpus_full.py` for u1.0.** Specifically: pass `llm=real_8B` to `build_relay_line()` for a new `--mode llm` flag, emit `prompt_template_id`, capture stripped `<think>` content, and count `llm_call_count` per case. The text-level tracer otherwise has no visibility into the 8B output quality.

7. **Add `intent`, `channel`, `verbosity` fields to `corpus.py:Case`** using keyword-only defaults (`intent: str = "relay"`, `channel: str = "team"`, `verbosity: str = "low"`) to preserve backward compatibility. Add three new `vocab_packs/` files: `negative_discord.py`, `negative_stream.py`, `negative_me_only.py` classified into `_NEGATIVE_PACKS` or a new `_ME_ONLY_PACKS` set.

8. **Do not change `InjectableCapture.drain()`.** The existing behavior (clears base-class queue, preserves `_pending`) is correct. Document this invariant explicitly in the u1.0 harness design notes.
