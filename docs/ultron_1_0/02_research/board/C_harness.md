# Adversarial Verification: Does the MP3-Battery E2E Harness Actually Validate Routing/Intent, or Does STT Noise Dominate?

**Layer:** C (Adversarial)
**Date:** 2026-06-20
**Cluster:** Eval Methodology (B_eval_methodology.md), Streaming STT Biasing (B_streaming_stt_biasing.md), Compound Commands (B_compound_commands.md)
**Adversarial goal:** Refute or qualify the harness validity claim that the MP3-battery E2E harness validates routing/intent in a meaningful way. Find evidence that STT transcription noise dominates and the test numbers are misleading.

---

## Claims Examined

The B-layer documents collectively assert:

1. **B-Eval Claim 1:** Pre-rendering test utterances to WAV via Kokoro and injecting via `InjectableCapture` / `sounddevice` callback mock constitutes a trustworthy E2E harness that exercises "real VAD, real STT, and real routing."
2. **B-Eval Claim 2:** faster-whisper large-v3-turbo is reliable enough that STT transcription quality on synthetic TTS audio is representative of live STT quality on real user speech.
3. **B-STT Claim 3:** The `initial_prompt` / `_DOMAIN_PROMPT` mechanism reliably fixes Valorant jargon misrecognition (agent names like "Jett", site letters "A"/"B", callout terms like "tree"), with cited 17% WER improvement.
4. **B-STT Claim 4:** Whisper is robust enough for always-on short gaming utterances if `_DOMAIN_PROMPT` is active.
5. **B-Compound Claim 5:** ClauseCompose-style discourse segmentation + LLM structured extraction generalizes to unseen compound Valorant callouts, with cited 95.7% exact match on unseen pairs.
6. **B-Eval Claim 6:** The harness as designed catches routing failures: routing accuracy numbers from the battery predict real-world intent routing correctness.

---

## Verdict Per Claim

### Claim 1 — QUALIFIED: Harness exercises real pipeline but audio distribution is systematically wrong

**What the harness actually does (from `gen_commands.py` + `run_corpus.py`):**
- Generates composite audio: `[0.5s silence] + [real openWakeWord training sample] + [gap] + [Kokoro am_michael TTS body at speed 1.18] + [1.3s trailing silence]`
- The harness's own docstring acknowledges the core validity problem: *"stock Kokoro 'Ultron' scores ~0.27 (< 0.65 threshold) on the openWakeWord detector, so a Kokoro wake word would NEVER fire."* Therefore a real human wake sample is spliced in for the wake word detection, but the **command body is still Kokoro TTS**.
- The harness therefore tests: (a) wake-word detection on real speech — valid; (b) VAD segmentation on clean Kokoro TTS — not representative; (c) STT on clean Kokoro TTS — not representative of real user speech.

**Counter-evidence — the distribution shift is documented and severe:**
- The τ-Voice benchmark (February 2026) found voice agents score **51% under clean audio vs. 38% under realistic conditions** — a 24-point absolute drop. OpenAI's system dropped 28 points (49% → 35%). This is for commercial production systems with large training corpora; Ultron's custom routing is more fragile, not less.
- Industry consensus (Hamming AI 2026, testdevlab.com): *"If you are only testing on clean audio, you are testing a demo, not production."* Clean-audio STT benchmarks can be **2–66x worse** with overlapping speech or noise.
- Deepgram Nova-3: 5.26% WER on internal clean benchmarks vs. 12.8% WER on third-party diverse-audio benchmarks — a 2.4x gap for a commercial system.
- Kokoro TTS audio is clean, studio-quality, lossless digital audio at 24kHz resampled to 16kHz. Real user speech in Valorant is: gaming headset (variable quality), PortAudio buffered capture with 256-sample blocks, Discord/VoiceMeeter signal chain, potential clipping/noise from teammates in Discord call, game audio bleed, and the user's own microphone characteristics.

**What this means for Ultron:** Battery numbers derived from Kokoro TTS command bodies are an upper-bound on routing accuracy, not a production estimate. STT on the TTS audio will be cleaner than on real speech. Routing decisions that pass on clean TTS may fail on the real headset input because the STT transcript is noisier.

**Verdict: QUALIFIED** — the harness is valid for regression testing that a known-good input still routes correctly (catching regressions), but the absolute routing accuracy numbers (e.g., "95% routing accuracy on the battery") are NOT representative of live Valorant session accuracy.

---

### Claim 2 — REFUTED: Kokoro TTS audio fed through faster-whisper is not representative of real speech transcription quality

**Counter-evidence:**

**Whisper hallucination rates on short/non-speech audio are severe:**
- arxiv 2501.11378 (2025) tested 301,317 non-speech audio files: hallucinations appeared **40.3%** of the time.
- At 1-second audio duration: **52.1%** hallucination rate (the single-word callout case — "A", "B", "tree").
- At the 30s segment boundary (Whisper's native decoding length): **62.3%** hallucination rate.
- Silence segments: **~17%** produce hallucinations, with 67.5% being from the top-30 "Bag of Hallucinations" list.
- The Calm-Whisper paper (arxiv 2505.12969, 2025) and Deepgram analysis of Whisper v3 confirm hallucination rates.

**Kokoro TTS is anomalously clean:** Kokoro achieves 3.90% round-trip WER (TTS → Qwen3-ASR → text comparison, Soniqo benchmark 2026) on 30 English conversational sentences. Real Valorant headset speech through faster-whisper large-v3-turbo in real conditions yields 8–12% WER baseline (real-world conditions benchmark from multiple 2025/2026 sources), with additional jargon errors on top.

**The 17% CER figure for Kokoro is misleading in this context:** The benchmark used 30 generic English conversational sentences, not domain-specific jargon. Kokoro relies on espeak-ng for grapheme-to-phoneme conversion, which "occasionally messes up proper nouns or uncommon words" (Kokoro documentation). Game agent names like "Killjoy", "Gekko", "Tejo", "Vyse" are not in espeak-ng's trained dictionary. If Kokoro mispronounces "Gekko" (the agent name), faster-whisper transcribes the mispronounced audio and may produce a garbled result — but this is a Kokoro articulation error, not the STT error a user would experience saying "Gekko" naturally. The errors are wrong in different ways.

**The harness's own workaround reveals the problem:** The harness already knows that Kokoro TTS wake word audio is rejected by the real wake-word detector. This is direct evidence that Kokoro TTS audio is out-of-distribution for at least one acoustic model in the pipeline. The same distribution mismatch plausibly affects faster-whisper STT, VAD behavior, and the EmbeddingGemma sidecar (though to a lesser extent for the text-only sidecar).

**Verdict: REFUTED for absolute accuracy claims. CONFIRMED for regression coverage.** The harness is useful to check "does this text input still route correctly" but the audio-injection route through STT cannot produce reliable absolute numbers for what fraction of live Valorant utterances will route correctly. The STT error modes for clean TTS audio differ from those for real headset speech.

---

### Claim 3 — QUALIFIED: `initial_prompt` biasing helps but has documented failure modes specific to Ultron's vocabulary

**Counter-evidence found:**

**Token limit vs. vocabulary size mismatch:** Valorant has 25+ agents, 7 maps, ~100+ callout terms, site letters, economy terms. A dense `initial_prompt` can fit ~30–40 agent names + site letters within 224 tokens. This is sufficient for agent names but leaves zero budget for callout spatial terms ("heaven", "short", "long", "tree", "link", "catwalk") that are the most commonly misrecognized in live use.

**Attention decay problem:** The arxiv 2410.18363 paper (which B_streaming_stt_biasing.md cites) found: *"the attention mechanism inherently assigns higher weights to tokens at the end of a longer prompt."* This means earlier entries in `_DOMAIN_PROMPT` get less attention weight. A 224-token prompt with agent names listed alphabetically gives lower attention to "Astra", "Breach", "Chamber" (early) vs. "Vyse", "Waylay" (late) — the opposite of what you want given that early agents like "Jett" are most commonly called.

**Size-dependent effectiveness:** Research shows `initial_prompt` improvements are model-size dependent. Whisper-small showed "average WER remained essentially unchanged across prompt conditions, with deltas contained within a few hundredths of a percentage point." Whisper large-v3-turbo should show larger improvements, but the effect has been measured in sports/basketball domain with careful prompt construction, not validated for fast-paced gaming callout speech.

**The live shadow bug makes this moot for now:** B_streaming_stt_biasing.md documents that `WHISPER_INITIAL_PROMPT` env var shadows `_DOMAIN_PROMPT` via Python `or` — domain biasing is OFF when the env var is set. The stream-build history confirms this was the live state during streaming sessions. Until this is fixed on main, all STT biasing claims are moot for live testing.

**17% WER improvement is from basketball, not Valorant:** The cited result (arxiv 2602.18966) is from an NBA basketball commentary domain. Basketball has clean announcer-quality speech, well-known player names that are in standard dictionaries, and a much slower speaking rate than a player saying "Jett A hit 84 coming mid" in one breath during a Valorant match. Transfer to gaming callout speech at speed 1.18× (the harness default) on noisy headset audio is not validated.

**Verdict: QUALIFIED** — initial_prompt is the right direction and should be kept, but the cited 17% WER improvement is not directly applicable to Valorant gaming callout speech on headset audio. The actual improvement on the live path is unknown (and currently zero because the bug is active). The 224-token limit is a hard ceiling that cannot fit the full Valorant vocabulary. For short single-token callouts ("A", "B"), initial_prompt helps but Whisper's fundamental short-utterance pathology (52% hallucination rate at 1s, per arxiv 2501.11378) is the dominant failure, not prompt biasing.

---

### Claim 4 — REFUTED for single-word/short callouts: Whisper is NOT robust for always-on short gaming utterances

**Counter-evidence:**

**Single-word gaming callouts are the worst case for Whisper:**
- Valorant uses many 1–3 word callouts: "A", "B", "mid", "tree", "heaven", "one back", "two here".
- arxiv 2501.11378 measured hallucination rates specifically at 1-second audio: **52.1%**. Short bursts of speech ("A!") after VAD endpoint detection are near-worst-case for Whisper's architecture.
- Whisper was trained on long-form speech (internet audio, audiobooks). Single-phoneme site calls are out-of-distribution at inference even with initial_prompt.
- Whisper-v3 hallucinates **4x more often** than Whisper-v2 on real-world data (Deepgram benchmark: median WER 53.4 for v3 vs. 12.7 for v2). The turbo model is a reduced version of v3.
- For always-on mode (every utterance transcribed), the hallucination rate on non-addressed utterances (teammates talking, Discord chat, background audio) arriving at Whisper is expected to be **~40%** producing spurious transcripts that must then be filtered by the intent gate.

**What this means for always-on intent gate:** The B_eval_methodology.md's IGNORE class relies on the intent gate correctly filtering background speech. But if Whisper hallucination on background noise/non-speech audio produces plausible-looking transcripts ("let's go", "yeah", "okay") — which is exactly what the Bag of Hallucinations shows (common filler phrases are the most frequent hallucination outputs) — then IGNORE classification must handle Whisper hallucinated text that looks exactly like genuine IGNORE_DISCORD examples. The intent gate F1 numbers measured on clean corpus inputs do not include this hallucination pressure.

**Verdict: REFUTED** for single-word and always-on modes. Whisper's short-utterance hallucination rate (52% at 1s) is the dominant failure mode for Valorant site calls and background monitoring, and the harness does not exercise this path (it uses clean Kokoro TTS audio which does not exhibit hallucination patterns).

---

### Claim 5 — QUALIFIED: ClauseCompose numbers do not transfer to noisy Valorant speech

**Counter-evidence:**

**ClauseCompose was tested on clean text, not ASR output:** The CoMIX-Shift benchmark (arxiv 2603.28929) reported 95.7% exact match on unseen intent pairs using the discourse-marker segmenter. This is measured on clean text input, not on STT transcriptions of compound spoken utterances. When STT introduces noise — "Jett aid 84" instead of "Jett hit 84", "Reyna's tree" vs "Reyna's three" — the discourse-marker regex and slot grammar receive corrupted input.

**The "long/noisy pairs" result is actually alarming:** Table in B_compound_commands.md shows ClauseCompose achieves **62.5%** exact match on long/noisy pairs. This is the realistic Valorant compound callout case — longer utterances with noise. The whole-utterance multi-label baseline drops to 18.8%, so ClauseCompose still wins, but 62.5% exact match means over one-third of noisy compound callouts are extracted incorrectly even with the best approach.

**The harness uses clean Kokoro TTS, hiding the noisy-input failure rate:** A battery of compound callouts rendered via Kokoro at 1.18× speed and fed through faster-whisper on clean TTS audio will show higher compound extraction accuracy than the same commands spoken by a real user mid-game with background noise. The "long/noisy" row in the CoMIX-Shift benchmark was constructed by adding noise and longer wrappers to text inputs — real gaming speech noise would be worse.

**MixATIS/MixSNIPS artificial connector bias:** The research documents note that both benchmark datasets are "constructed by concatenating single-intent utterances with connectors" — an artificial structure. Real Valorant compound speech is implicit ("Jett 84 Breach 97", no connector) or uses gaming-specific linking ("Jett 84 and Breach is low health"). The discourse regex must be built specifically for Valorant patterns rather than assuming academic connector patterns will work.

**Verdict: QUALIFIED** — the ClauseCompose approach is the right architecture, but the 95.7% number applies to clean text on academic connectors. For noisy STT output on gaming-style implicit compounds, realistic accuracy is closer to the 62.5% "long/noisy" row, and may be lower for Valorant-specific implicit patterns. The harness will overstate compound extraction accuracy because Kokoro TTS is cleaner than live speech.

---

### Claim 6 — REFUTED: Battery routing accuracy numbers do NOT predict real-world routing correctness

**Synthesizing all above:** The cumulative effect of Claims 1–5 is that the harness provides an optimistic upper bound on routing accuracy, not a production estimate. The concrete gaps:

| Gap | Source | Estimated magnitude |
|---|---|---|
| Clean TTS vs. real headset speech (STT WER) | τ-Voice 2026, Hamming AI | 8–24 percentage points |
| Whisper short-utterance hallucination on non-speech background | arxiv 2501.11378 | 40–52% hallucination rate not exercised by harness |
| Domain prompt shadow bug (biasing OFF in live sessions) | Memory, wip branch | Domain jargon WER unimproved until bug fixed |
| Kokoro TTS agent name mispronunciation vs. real pronunciation | Kokoro docs (espeak-ng) | Unknown, not benchmarked for Valorant vocab |
| Compound extraction on noisy input | ClauseCompose long/noisy | ~62% vs. ~96% on clean text |

A system achieving 95%+ routing accuracy on the battery could realistically achieve 75–85% routing accuracy in live Valorant play, depending on headset quality, background noise, and the proportion of short/ambiguous callouts. **The harness does not provide enough signal to know where in that range the system actually sits.**

**Verdict: REFUTED** for using battery numbers as a proxy for production accuracy. The harness is VALID for:
- Catching regressions (a change that breaks a previously-passing battery case is a real regression)
- Verifying routing architecture correctness on clean inputs
- Stress-testing deterministic snap matchers (which are text-based and immune to STT noise)

---

## Corrected Recommendation for Ultron 1.0

The B-layer recommendation to use the MP3-battery E2E harness is directionally correct but needs critical amendments:

### 1. Rename what the harness measures

The harness measures **text-input routing accuracy** (with a Kokoro TTS → STT wrapper). Call it what it is: a routing regression harness, not an E2E accuracy benchmark. The 95% routing accuracy threshold in the CI gate should be understood as "95% on clean TTS input" not "95% in production."

### 2. Add a text-injection bypass path

The highest-value immediate addition: add a parallel test mode that injects normalized text directly into the post-STT pipeline (bypassing audio entirely). This:
- Removes STT noise as a variable, making routing tests deterministic
- Runs in ~1ms per case (no audio rendering, no STT inference)
- Can be run as a fast CI gate on every PR (not just routing-focused PRs)
- The existing 25k-corpus trace (`trace_corpus_full.py`, tip `4a36d8e`) already does this — **this is the more trustworthy routing accuracy number**

### 3. Add three noise-injection fixtures to the audio harness

To get production-representative E2E numbers, add fixtures that apply:
- **Gaming headset simulation:** apply headset frequency response curve (typically ~100Hz–15kHz bandpass, ~0.5dB ripple) + 2dB room reverb + 15dB SNR background (Valorant game audio at low volume)
- **VoiceMeeter signal chain:** the real Valorant path goes through VoiceMeeter B1 bus (confirmed at −21.14 dB vs. real mic per the audio rootcause doc); STT tests should inject that signal chain
- **Short-utterance silence padding:** for 1–3 word callouts, add explicit test cases with VAD-boundary-exact audio (no leading/trailing silence buffer) to expose the pre-roll/VAD interaction bug

### 4. Add a hallucination pressure test

Add fixtures that deliberately inject background speech (teammate talking, Discord audio) and assert the intent gate routes to IGNORE rather than RELAY_TO_TEAM. These are the false-positive cases that the harness currently cannot test because Kokoro TTS audio does not hallucinate spurious transcripts the way Whisper does on real background speech.

### 5. Fix the domain prompt bug before trusting any STT biasing metrics

The `_DOMAIN_PROMPT` shadow bug (`.env WHISPER_INITIAL_PROMPT` overrides domain biasing via `or`) must land on main before any STT-dependent harness metric is meaningful. All battery runs with the domain prompt absent are measuring degraded STT accuracy. This is already identified on the wip branch.

### 6. Calibrate battery pass rates as relative numbers, not absolutes

Report the battery as a relative metric: "97% routing accuracy at baseline; new change achieves 96% — investigate the 3-case delta." Never report it as "97% production routing accuracy." The production estimate requires the noise-injection fixtures (point 3 above) and ideally a sample of real session logs cross-referenced against the trace.

### 7. Add a real-session spot-check protocol

After each live gaming session, review `logs/usage_trace.jsonl` for the last 30 turns. Manually inspect any turn where `route` is unexpected. Track a simple per-session routing accuracy number on real speech. This is the ground truth the battery cannot provide.

---

## Residual Risks

1. **STT is the opacity layer.** All routing, intent classification, and compound extraction operate on the STT transcript. If faster-whisper produces a wrong transcript (hallucination, jargon mishear, phonetic confusion), downstream logic is correct but the wrong input feeds it. The harness only partially exercises this because Kokoro TTS produces a narrower range of errors than real speech.

2. **espeak-ng pronunciation of new Valorant agents.** Agents added after espeak-ng's training data cutoff (Tejo, Waylay, Vyse added in 2025) may be mispronounced by Kokoro, producing a wrong phoneme sequence that Whisper misrecognizes differently from how it would mishear a real user saying the same name. This creates test cases that fail differently from how they fail in production.

3. **Whisper hallucination in always-on mode is untested.** The battery feeds the pipeline explicit audio clips. In always-on mode, the VAD fires on any audio above threshold, including Whisper hallucination on silence/non-speech between commands. The hallucination pressure on the intent gate is not measured.

4. **The harness `got_trace_row` quiescence heuristic may mask failures.** `run_corpus.py` considers a turn complete when a new trace row appears AND synthesis quiesces for 1.8s. If the pipeline routes to IGNORE (no synthesis) or fails silently, `got_row = False` — these are logged as `??` but may be miscounted in pass-rate calculation.

5. **Compound callout evaluation requires Valorant-specific test pairs.** The CoMIX-Shift "held-out pair" methodology requires excluding specific agent+callout type pairs from training. The current battery mixes all types freely; a held-out compound pair set needs to be constructed explicitly.

6. **No VRAM-pressure simulation.** The harness runs with a controlled VRAM state. In live Valorant play, VRAM may be partially occupied by game assets, Valorant's anti-cheat memory footprint, or OS overhead. STT and LLM inference latency under real VRAM pressure is untested.

---

## Sources

- arxiv 2501.11378 (2025) — Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio: https://arxiv.org/html/2501.11378v1
- arxiv 2505.12969 (2025) — Calm-Whisper: Reducing Whisper Hallucination On Non-Speech: https://arxiv.org/html/2505.12969v1
- τ-Voice Benchmark (2026) — Full-duplex voice agent performance under realistic conditions: https://www.arunbaby.com/speech-tech/0066-tau-voice-benchmark-full-duplex-voice-agents/
- Hamming AI: How to Evaluate Voice Agents (2026): https://hamming.ai/resources/how-to-evaluate-voice-agents-2026
- testdevlab.com: How to Test Audio Quality in AI Voice Agents: https://www.testdevlab.com/blog/how-to-test-ai-voice-agent-audio-quality
- Deepgram: Whisper v3 Results on Real-World Data: https://deepgram.com/learn/whisper-v3-results
- arxiv 2410.18363 (2024) — Contextual Biasing for Domain Vocab Without Fine-Tuning: https://arxiv.org/html/2410.18363v1
- arxiv 2602.18966 (2026) — Whisper Courtside Edition (basketball domain biasing; 17% WER improvement): https://arxiv.org/html/2602.18966
- arxiv 2603.28929 (2026) — ClauseCompose / CoMIX-Shift benchmark: https://arxiv.org/html/2603.28929
- Soniqo Apple Silicon Benchmarks (2026) — Kokoro 3.90% round-trip WER: https://soniqo.audio/benchmarks
- ShiftySpeech arxiv 2502.05674 (2025) — Synthetic speech distribution shifts: https://arxiv.org/pdf/2502.05674
- arxiv 2502.12414 (2025) — Distribution shift and Whisper hallucination mechanism: https://arxiv.org/html/2502.12414v1
- Softcery: Clean audio vs. production gap (STT 2x–66x worse with noise): https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture
- Kokoro TTS documentation (espeak-ng proper noun caveat): https://deepwiki.com/hexgrad/kokoro/4-languages-and-voices
- github.com/ggml-org/whisper.cpp issue #1724 — Hallucination on silence: https://github.com/ggml-org/whisper.cpp/issues/1724
- Codebase: scripts/relay_test/audio_corpus/gen_commands.py (harness audio generation, am_michael at speed 1.18)
- Codebase: scripts/relay_test/audio_corpus/run_corpus.py (harness run loop, quiescence logic)
- Codebase: scripts/relay_test/audio_corpus/inject.py (InjectableCapture implementation)
