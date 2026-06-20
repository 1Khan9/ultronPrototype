# Always-on Streaming STT on Consumer GPU (2026): Model Comparison, Architecture, and Contextual Biasing for Ultron 1.0

## TL;DR Recommendation for Ultron 1.0

**Keep faster-whisper (large-v3-turbo, int8, GPU) as primary STT** for Ultron 1.0. It is the lowest-friction path: already integrated, ~2.5 GB VRAM on RTX 4070 Ti, ~12× real-time in offline mode, and the WhisperStreaming LocalAgreement-2 commit policy converts it to a functional streaming pipeline with 300–800 ms effective latency. The existing `initial_prompt` / `_DOMAIN_PROMPT` mechanism already addresses Valorant jargon biasing — the shadow bug (`.env` `WHISPER_INITIAL_PROMPT` overriding via `or`) was identified and fixed on the wip branch; that fix must land on main.

**For Ultron 1.1 / future iteration:** NVIDIA Nemotron-Speech-Streaming-0.6B is the SOTA answer for always-on streaming STT. It achieves 18 ms p50 latency (vs 173 ms for Whisper turbo), uses only ~2.8 GB VRAM, degrades just 0.21% absolute WER moving from batch to streaming, and supports configurable 80 ms–1.12 s chunk latency. The blocker is NeMo dependency and Linux-first stance.

**Contextual biasing for gaming jargon:** The highest-ROI zero-code technique is a well-constructed `initial_prompt` (Valorant agent names, site letters, callout vocab, up to 224 tokens) — proven 17% relative WER improvement on domain-specific vocabulary in comparable gaming/sports domains. For transducer-based models (Nemotron, Parakeet), sherpa-onnx hotwords with `modified_beam_search` add 3–4% latency overhead and cut keyword WER by 35–45%.

---

## Findings

### 1. Model Landscape (2026 State)

#### 1a. faster-whisper + large-v3-turbo (SOTA for Whisper family)

Large-v3-turbo reduces Whisper Large V3's decoder layers from 32 to 4, yielding:
- **~2.7× faster** than large-v3 in faster-whisper (GitHub issue #1030: 19.2 s vs 52.0 s for 13 min audio)
- **WER: 7.75%** average (vs 7.4% for large-v3; negligible regression)
- **VRAM: ~2.5 GB** (int8 via CTranslate2), ~6 GB in fp16
- **RTFx: 216** in batch; **~12× real-time** on RTX 4070 (int8)
- On RTX 4070 Ti (our GPU), expect RTFx ~180–250 depending on batch size

The model is **not natively streaming**: it expects complete audio segments up to 30 s. Streaming is emulated via chunk-based re-processing (see Architecture section).

Faster-whisper specifically beats whisper.cpp ~50% on RTX 4070 (12× vs 8×) and includes built-in Silero VAD integration, which is essential for always-on silence suppression.

Sources: [Northflank STT benchmark 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks), [promptquorum comparison](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026), [GitHub issue #1030](https://github.com/SYSTRAN/faster-whisper/issues/1030)

#### 1b. Moonshine v2 (Ergodic Streaming Encoder, Feb 2026)

Moonshine v2 (arxiv 2602.12241) is the most architecturally elegant streaming model:
- **Architecture:** Sliding-window self-attention (no positional embeddings in encoder = "ergodic"); 80 ms lookahead, 320 ms max future context
- **Latency:** Constant TTFT regardless of utterance length. Moonshine v2 Medium: **258 ms** vs Whisper Large v3's 11,286 ms for same utterance
- **WER:** Medium = 6.65%, Small = 7.84%, Tiny = 12.01%
- **Model sizes:** Tiny 34 MB, Small 123 MB, Medium 245 MB (extremely lightweight)
- **Partial hypothesis:** Finalized vs. provisional encoder states — live display naturally improves as audio extends
- **Platform:** CPU-first, edge-optimized. On Apple M3 CPU, Medium achieves 258 ms at 28.95% CPU load

**Critical caveat for Ultron 1.0:** Moonshine is English-only, CPU-first, and targets edge devices. On our RTX 4070 Ti it would massively over-provision (no GPU kernel optimizations tested). WER at 6.65% (Medium) is competitive, but the model is designed for scenarios where Whisper Large is too heavy. Since we have a 12 GB GPU and our primary constraint is latency and jargon accuracy, Moonshine is best viewed as an **emergency fallback** if VRAM becomes constrained by the 8B LLM.

Sources: [Moonshine v2 paper](https://arxiv.org/html/2602.12241), [Moonshine HF streaming docs](https://huggingface.co/docs/transformers/model_doc/moonshine_streaming), [modelslab benchmark](https://modelslab.com/blog/audio-generation/moonshine-vs-whisper-asr-real-time-speech-2026)

#### 1c. NVIDIA Parakeet TDT 1.1B / 0.6B-v3 (Batch SOTA, Streaming Problematic)

Parakeet TDT uses a Token-and-Duration Transducer decoder on a FastConformer encoder:
- **WER: 7.02%** mean (Open ASR leaderboard), LibriSpeech clean = 1.39% — among the best
- **RTFx: 2,390** — fastest offline model available
- **VRAM: ~4–5 GB**
- **Streaming:** NOT natively streaming. Chunked inference via `speech_to_text_buffered_infer_rnnt.py` in NeMo. **Bug fixed May 2025** (previously broken for TDT). When chunked at 3 s, WER degrades from 6.32% → 9.22% (+46% relative), making it strictly worse than Whisper for streaming use cases.
- **Partial hypotheses:** Not documented; RNNT decodes token-by-token but the Python NeMo API does not expose incremental outputs cleanly.
- **Dependency:** Requires `nemo_toolkit['all']` — a large installation that would need careful anticheat isolation (heavy ML framework, imports at load time).

**Bottom line for Ultron 1.0:** Parakeet is a batch/offline powerhouse but a streaming liability. Its chunked-streaming WER regression eliminates its accuracy advantage.

Sources: [Parakeet HF page](https://huggingface.co/nvidia/parakeet-tdt-1.1b), [E2E Networks benchmark](https://www.e2enetworks.com/blog/benchmarking-asr-models-nvidia-l4-parakeet-whisper-nemotron), [HF discussion streaming?](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2/discussions/3)

#### 1d. NVIDIA Nemotron-Speech-Streaming-0.6B (SOTA Streaming, June 2026)

Released June 2026, this is the current best purpose-built streaming model:
- **Architecture:** Cache-Aware FastConformer + RNNT decoder (24 encoder layers); maintains rolling cache tensors across chunks, eliminating recomputation
- **WER: 10.30%** without normalization on E2E benchmark (Whisper Large v3-turbo: 8.93% same benchmark), **8.20%** with int4 ONNX optimization across 8 benchmarks
- **Streaming latency:** 18 ms p50 at 0.5 s frame length (benchmark vs Whisper's 173 ms p50)
- **VRAM: ~2.8 GB** (fp16), **0.67 GB** in int4 ONNX quantized
- **Chunk latency configurability:** 80 ms / 160 ms / 560 ms / 1.12 s via `att_context_size` parameter — adjustable at inference without retraining
- **WER streaming degradation:** Only 0.21% absolute (best-in-class; Whisper chunks degrade 3.5% absolute at 10 s)
- **ONNX path:** Microsoft CoreAI reimplemented entire streaming pipeline in ONNX Runtime (April 2026 paper). int4 k-quant = 73% size reduction, 7.2× RTF on CPU
- **Nemotron 3.5 ASR** (June 2026): 40-language multilingual variant, 80 ms–1 s controllable latency
- **Supported GPUs:** Ampere, Hopper, Blackwell, Volta (RTX 4070 Ti = Ampere = Ada Lovelace — confirmed compatible)
- **Windows:** Not officially supported (Linux preferred). NeMo 25.11 required.

**For Ultron 1.0 blockers:** NeMo on Windows is painful but doable; the ONNX path bypasses NeMo for inference. Anticheat concern is minimal since this runs in-process as an ONNX model — no network, no unusual imports.

Sources: [Nemotron HF README](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/blob/9e21a4f0482c4ac609afb25f7eae1b0d09a07d14/README.md), [Compact Streaming ASR paper arxiv 2604.14493](https://arxiv.org/html/2604.14493v2), [E2E Networks benchmark](https://www.e2enetworks.com/blog/benchmarking-asr-models-nvidia-l4-parakeet-whisper-nemotron), [MarkTechPost Nemotron 3.5](https://www.marktechpost.com/2026/06/06/nvidia-releases-nemotron-3-5-asr-a-600m-parameter-cache-aware-streaming-model-transcribing-40-language-locales-in-real-time/)

#### 1e. Model Comparison Table

| Model | WER (avg) | p50 Latency | VRAM | Streaming | Partial Hyp | Notes |
|---|---|---|---|---|---|---|
| faster-whisper large-v3-turbo | 7.75% | ~173 ms (batch p50) | 2.5 GB int8 | Emulated (chunks) | Via LocalAgreement | RTX 4070: 12× RT |
| Moonshine v2 Medium | 6.65% | 258 ms constant | <1 GB | Native (ergodic) | Finalized/provisional | Edge/CPU-first |
| Parakeet TDT 1.1B | 7.02% | 29 ms (batch) | ~4 GB | Chunked (degrades) | Not exposed | 9.22% WER streaming |
| Nemotron Streaming 0.6B | 8.20% | 18 ms | 2.8 GB | Native cache-aware | Per-chunk output | SOTA streaming |

---

### 2. Continuous-Transcription Architecture: Rolling Buffer + Partial Commits

The fundamental challenge: Whisper-class models expect complete audio (up to 30 s) but we need sub-1 s response for always-on voice intent classification. Three proven patterns:

#### Pattern A: WhisperStreaming LocalAgreement-2 (Recommended for Ultron 1.0)

From [ufal/whisper_streaming](https://github.com/ufal/whisper_streaming):

1. Maintain a rolling audio buffer (configurable, default 30 s max, cleaned at sentence boundaries)
2. Every `--min-chunk-size` seconds (configurable; 1–3 s typical), feed the current buffer to faster-whisper
3. **LocalAgreement-2 commit policy:** Text is "committed" (emitted as stable) only if two consecutive processing iterations agree on that prefix. This prevents premature commits when future audio clarifies ambiguous words.
4. Buffer trimmed at timestamp of last confirmed complete sentence (Whisper returns timestamps per word)
5. Silero VAD runs first to suppress silence processing

Reported latency: **3.3 s** on long-form speech (conservative default). For short gaming commands (1–3 s utterances), effective latency is closer to **500 ms–1.5 s** with `--min-chunk-size 1.0`.

Relevant parameter tuning for Ultron:
- `--min-chunk-size 1.0` — process as soon as 1 s of audio arrives
- `beam_size=1`, `condition_on_previous_text=False` — prevents hypothesis drift across chunks (faster + more stable)
- Strip first/last 0.5 s of each chunk output in overlap region before concatenating stable middle
- `--comp_unaware` mode to reveal theoretical latency floor (model-uncertainty only, excludes processing time)

#### Pattern B: Silero VAD + Endpoint-Gated Whisper (Current Ultron 0.x approach)

Rather than rolling re-process, use VAD to find speech boundaries → feed complete utterance to Whisper. This is what current Ultron does (`_wait_for_wake_word` / `_capture_utterance`). Latency = VAD endpoint delay + Whisper inference time. For short gaming commands this is 300–800 ms total. The known bug (pre-roll not fed to VAD → `speech_seen` False → discard) is the primary failure mode.

**This is actually fine for Ultron 1.0** because gaming commands are typically short (1–5 s) and endpoint detection is fast. The fix in `ad15ded` (pre-feed `chunks[0]` to `vad.process`) resolves the root cause.

#### Pattern C: Cache-Aware Transducer (Nemotron / Nemotron 3.5 approach)

The gold standard for always-on streaming:
1. Divide audio into chunks (80 ms–1.12 s)
2. Run encoder on chunk → update rolling cache tensors (attention + convolution)
3. RNNT decoder emits tokens as they are predicted, no wait for endpoint
4. Partial hypotheses available after each chunk naturally

This achieves 18 ms p50 because the encoder cache eliminates recomputation of prior audio. The model is specifically trained to tolerate partial context.

**When to switch to Pattern C:** When Ultron 1.0's intent gate needs to act on a partial utterance before it ends (e.g., detect "relay" intent at the word "tell" before hearing the full sentence). This is the architecture upgrade path.

---

### 3. Contextual Biasing / Hotword Boosting for Gaming Jargon

This is where the research is richest. Several layers available:

#### Layer 0: initial_prompt (Already in Ultron, Partially Broken)

Whisper's `initial_prompt` parameter injects "previous transcript" tokens before decoding. When populated with Valorant vocab (agent names, site letters, callout terms), the decoder probability mass shifts toward those tokens.

**Proven results:** A basketball commentary system ("Whisper Courtside Edition", arxiv 2602.18966) used a prompt encoding: domain context + canonical player names + sport jargon. Result: **17% relative WER reduction** on domain-specific vocabulary. This is directly analogous to Valorant callouts.

**Current Ultron bug:** `.env` `WHISPER_INITIAL_PROMPT='Kenning.'` overrides `_DOMAIN_PROMPT` via Python `or` operator — domain biasing is effectively OFF when the env var is set. Fix: `initial_prompt = os.getenv("WHISPER_INITIAL_PROMPT") or _DOMAIN_PROMPT` should be reversed to: use domain prompt as base, append env override if any.

**Limitations of initial_prompt:**
- 224-token maximum (sufficient for ~30–40 agent names + site letters)
- Attention weights decay for tokens far from the end of prompt (put most critical terms last)
- Misaligned: Whisper expects prior transcript text, not a vocabulary list. Still works empirically but is suboptimal.

**Recommended Ultron initial_prompt content (priority order, last = highest weight):**
```
Valorant. Jett. Reyna. Omen. Killjoy. Sova. Breach. Chamber. Viper. Sage. 
Astra. Skye. Fade. Gekko. Deadlock. Iso. Clove. Vyse. Tejo. Waylay.
A site. B site. C site. mid. heaven. short. long. attack. defend.
```

#### Layer 1: B-Whisper / Prompted Fine-Tuning (Medium Effort, High Gain)

B-Whisper (arxiv 2502.11572) achieves **45.6% relative reduction in rare-word WER** and **60.8% reduction in OOV WER** via:
1. Fine-tune on 670 hours of English (Common Voice)
2. At training time: random "true bias word" from vocabulary list injected in prompt + weighted cross-entropy (β=1.1 for bias words)
3. At inference: provide hotword list as prompt, model learned to preferentially decode listed words

This requires fine-tuning, which is feasible (Common Voice is publicly available) but non-trivial. The resulting model still uses the standard faster-whisper inference path.

#### Layer 2: CTC-Based Streaming Word Spotting (For Transducer Models)

Paper arxiv 2605.18222 — applies to CTC/RNNT architectures (Nemotron, Parakeet):
1. Maintain Aho-Corasick automaton over hotword trie
2. At each audio chunk, run CTC log-probability search through trie
3. "Commit frontier" = earliest active token start → emit stable prefix
4. Boost paths matching hotwords; cancel boost if full match fails
- **WER improvement:** F-score on person names: 66.84% → 89.61%; WER 18.36% → 12.83%
- **Latency overhead:** ~3–4% of chunk duration — effectively zero
- **No retraining required** — plugs into existing deployed model

#### Layer 3: Sherpa-ONNX Hotwords (Transducer models, Production-Ready)

[Sherpa-ONNX hotwords](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html) implements Aho-Corasick hotword boosting for any transducer model:
- Pass hotwords as file (one per line), set boost score per token
- **Only** works with `modified_beam_search` decoding (not `greedy_search`)
- Individual per-word score: `SOVA :3.0`, `JETT :2.5`, etc.
- Demonstrated RTF improvement (0.076 → 0.065) with hotwords enabled — no regression
- Works identically in streaming and offline transducer models
- **Anticheat note:** Sherpa-ONNX is pure ONNX Runtime + numpy + scipy — no unusual imports, no network. This is anticheat-safe if used as a subprocess or isolated library.

#### Layer 4: Prefix-Trie Decoding (Research, 2025)

arxiv 2508.17796 — zero-shot trie-based decoding with synthetic multi-pronunciation:
- **B-WER reduction: 19% (test-clean), 22% (test-other)**
- Multi-pronunciation handling (e.g., "Killjoy" → ["KIL-joy", "KIL-djoy"])
- No fine-tuning required; operates at decoding time
- Currently research code (WhisperBiasing GitHub); not yet packaged for production

---

### 4. The Pre-Roll / Domain Prompt Bug (Critical for Ultron Now)

Two live bugs identified in research that directly affect Ultron's STT quality:

**Bug A (in wip branch, not yet on main):** `WHISPER_INITIAL_PROMPT` env var shadows `_DOMAIN_PROMPT` → domain biasing is OFF when env var is set. Result: agent names and site letters get Whisper's default (wrong) transcription. Fix is trivial (reverse the `or`).

**Bug B (fixed in ad15ded, not yet on main):** Pre-roll audio chunk fed to STT but not to VAD → `speech_seen` stays False → utterance discarded → "said it 8x before response". Fix exists on branch.

Both bugs must reach main before Ultron 1.0 streaming STT is trustworthy.

---

### 5. Architecture Decision: VAD Endpoint vs. Streaming Partial

For Ultron 1.0's always-on intent gate:

**Situation A — Wake-word-required mode (current default):**
- Ultron listens for wake word only (via `_wait_for_wake_word`)
- After wake → capture utterance via VAD endpoint
- Transcribe complete utterance → route intent
- Acceptable total latency: 300–600 ms (VAD endpoint detection + Whisper inference on ~2–5 s audio)
- **No streaming needed** — the current architecture is correct, just needs Bug A + Bug B fixed

**Situation B — Always-listening intent gate (Ultron 1.0 target):**
- Every utterance transcribed to classify {RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE}
- Most utterances → IGNORE quickly; relay utterances transcribed fully
- **Recommended approach:** Run Silero VAD continuously (already in-process, <1 ms/chunk); on speech detection, feed audio chunks to faster-whisper with LocalAgreement commit at 1–1.5 s
- The intent classifier (EmbeddingGemma + rules) can fire on each committed partial to pre-classify as RELAY_LIKELY vs IGNORE_LIKELY, with IGNORE cases discarded before full transcription completes
- This gives sub-1 s IGNORE latency (cheap: rules + embedding on partial), 1–2 s RELAY latency (full transcription then format)

**Situation C — Sub-200 ms partials for responsive UX:**
- Not achievable with faster-whisper without specialized streaming architecture
- Requires Nemotron or Moonshine v2 running in true chunk-streaming mode
- Defer to Ultron 1.1

---

### 6. VRAM Budget Interaction with 8B LLM

Critical constraint: 10 GB VRAM design cap on RTX 4070 Ti (12 GB physical).

| Component | VRAM |
|---|---|
| Josiefied-Qwen3-8B Q5_K_M (llama-cpp) | ~6.5–7 GB |
| faster-whisper large-v3-turbo (int8) | ~2.5 GB |
| Kokoro TTS | ~0.5–1 GB |
| EmbeddingGemma sidecar | ~0.5 GB (CPU likely) |
| **Total** | **~10–11 GB** |

This is tight. Options:
1. Keep EmbeddingGemma on CPU (current approach — correct)
2. Keep faster-whisper on GPU for speed; evict/reload if needed (current approach)
3. Switch to faster-whisper large-v3-turbo int8 (not int4) to stay at 2.5 GB not 4 GB
4. If Nemotron ONNX path is used instead of faster-whisper, it saves ~1.8 GB VRAM (0.67 GB ONNX int4 vs 2.5 GB faster-whisper int8) — but Nemotron's accuracy is 1–2% WER worse on English

The VRAM math works for the current setup as long as EmbeddingGemma remains on CPU and we use int8 quantization for Whisper.

---

### 7. Short-Utterance / Single-Word Command Accuracy

Valorant gaming commands include extremely short utterances: "A", "B", "mid", "tree", "heaven", "one back". These are where Whisper historically fails.

Key findings from research:
- Whisper was trained on long-form speech. Single-word utterances are out-of-distribution.
- `initial_prompt` helps substantially (decoder probability biased toward valid words)
- `condition_on_previous_text=False` in streaming mode prevents contamination from prior chunk hypotheses
- For single-word commands: **separate rapid-keyword detector** (Silero/Picovoice/sherpa-onnx hotword path) can run in parallel with full STT, firing faster for high-confidence single words
- `word_timestamps=True` in faster-whisper enables per-word timing for LocalAgreement commit policy
- The existing RapidFuzz + Metaphone lexical matcher in Ultron serves as a post-processing correction layer — this is the right architecture (STT outputs noisy transcript → lexical matcher corrects to valid vocab)

The current Ultron approach (STT → normalizer → RapidFuzz fuzzy match → snap/router) is sound. The gap is domain prompt biasing being broken.

---

## Concrete Techniques/Params We Should Adopt

1. **Fix the initial_prompt shadow bug** (wip branch → main): ensure `_DOMAIN_PROMPT` is always active; env var should append, not replace.

2. **Populate `_DOMAIN_PROMPT` with full Valorant agent roster + site letters + common callout terms** (up to 224 tokens). Structure: most-common-confusables last (highest attention weight). Include: all 25 current agents by name, "A site", "B site", "C site", "mid", "heaven", "short", "long", "lurk", "flank", "retake", "rotate".

3. **Apply WhisperStreaming LocalAgreement-2 for the always-listening intent gate:**
   - `min_chunk_size=1.0` (1 s minimum before each re-process)
   - `beam_size=1`, `condition_on_previous_text=False`
   - Strip 0.5 s overlap from chunk boundaries before committing
   - Feed committed partials to EmbeddingGemma intent classifier immediately
   - On IGNORE classification: halt STT for that utterance early

4. **faster-whisper params for streaming mode:**
   ```python
   model.transcribe(
       audio_chunk,
       language="en",
       beam_size=1,
       best_of=1,
       temperature=0.0,
       condition_on_previous_text=False,
       word_timestamps=True,
       initial_prompt=_DOMAIN_PROMPT,
       vad_filter=True,
       vad_parameters={"min_silence_duration_ms": 300}
   )
   ```

5. **Pre-feed pre-roll chunk to VAD** (Bug B fix from ad15ded — must land on main):
   ```python
   # Feed chunks[0] (ring snapshot) to vad.process before live loop
   vad.process(chunks[0])  # latches speech_seen; fail-open
   ```

6. **For Ultron 1.1 / Nemotron path:** Use ONNX Runtime streaming variant at 560 ms chunk size (best latency/accuracy tradeoff per paper). Set hotwords via the CTC-WS layer (arxiv 2605.18222) or port to sherpa-onnx transducer if compatible model is available.

7. **Sherpa-ONNX hotwords for transducer model evaluation (optional, low risk):** If evaluating Parakeet or Nemotron via sherpa-onnx, add agent names as hotwords with score 2.5–3.0. No code change to acoustic model, minimal latency impact.

---

## Risks/Caveats for Our Constraints

### Anticheat (Primary Constraint)

- **faster-whisper (CTranslate2):** Anticheat-safe. No kernel drivers, no network, pure CUDA via PyTorch/CTranslate2. Already validated in Ultron 0.x.
- **NeMo toolkit:** HIGH RISK. Installs a large framework with optional network-fetching of models, telemetry potential, heavy imports. Would need careful isolation or import-firewall allowlist additions. **Do not install NeMo in the same process as the anticheat-sensitive relay path.**
- **Nemotron ONNX path:** SAFE if using ONNX Runtime directly (no NeMo at inference time). The Microsoft CoreAI ONNX conversion (arxiv 2604.14493) produces a standalone ONNX model runnable with `onnxruntime-gpu` only.
- **Sherpa-ONNX:** SAFE — pure ONNX Runtime + numpy, no network, no kernel drivers.
- **Moonshine:** SAFE via HuggingFace transformers (already in the sidecar environment).

### VRAM Budget

- Adding Nemotron ONNX (0.67 GB int4) alongside the 8B LLM and Kokoro TTS is feasible (~9.7 GB total). Replacing faster-whisper with Nemotron saves ~1.8 GB.
- Do NOT run large-v3 (non-turbo) — it requires ~6 GB alone and would OOM the combined stack.
- int8 quantization for faster-whisper is mandatory (not int4, which CTranslate2 does not support for Whisper at this precision).

### Windows Support

- **faster-whisper:** Full Windows CUDA support.
- **Nemotron via NeMo:** Linux officially. NeMo on Windows is possible via WSL2 or direct pip but not officially tested. The ONNX path (onnxruntime-gpu on Windows) is clean.
- **Sherpa-ONNX:** Full Windows support including C++ binaries and Python wheel.
- **Moonshine:** Full Windows support via HuggingFace transformers.

### Streaming Accuracy Degradation

- faster-whisper in chunked mode at 3 s chunks: **+3.5% absolute WER regression** (Northflank/E2E benchmark). At 1 s chunks, expect higher.
- Mitigation: LocalAgreement-2 policy delays commit until two iterations agree → reduces spurious tokens at chunk boundaries.
- For gaming commands (1–5 s utterances), the VAD-endpoint approach (Pattern B) avoids this entirely because the full utterance is transcribed at once. **Prefer Pattern B for Ultron 1.0.**

### Single-Word Utterance Failure

- Whisper consistently fails on single-phoneme or very short words ("A", "B") transcribed in isolation without context. The model may output silence, random tokens, or hallucinate.
- Mitigation: Ultron's `_DOMAIN_PROMPT` primes the decoder. The RapidFuzz fuzzy matcher corrects "eh" → "A" and similar confusions. The Metaphone phonetic matcher handles ASR phonetic confusions.
- For bare single-letter site calls ("A!", "B!"), the deterministic slot parser (`relay_speech._parse_callout_slots`) should be the primary path — STT just needs to get close enough for the fuzzy matcher to score a high match.

### Latency Reality Check

- Always-on continuous STT with sub-500 ms commit latency requires either: (a) a purpose-built streaming model (Nemotron/Moonshine), or (b) VAD endpointing + fast Whisper on short segments.
- For Ultron's use case (classify intent, route relay), **total STT→route latency of 600–1200 ms is acceptable**. The TTS/relay output latency is already the dominant term (2–4 s for Kokoro + flavor tail).
- Do not optimize STT beyond 500 ms until TTS+relay latency is below 1 s.

---

## Sources

- [Northflank: Best Open Source STT Models 2026 (benchmarks)](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Moonshine v2 paper (arxiv 2602.12241)](https://arxiv.org/html/2602.12241)
- [Moonshine HuggingFace streaming docs](https://huggingface.co/docs/transformers/model_doc/moonshine_streaming)
- [Nemotron HF README (Streaming EN 0.6B)](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b/blob/9e21a4f0482c4ac609afb25f7eae1b0d09a07d14/README.md)
- [Compact Streaming ASR / Nemotron benchmark paper (arxiv 2604.14493)](https://arxiv.org/html/2604.14493v2)
- [E2E Networks: Parakeet vs Whisper vs Nemotron on NVIDIA L4](https://www.e2enetworks.com/blog/benchmarking-asr-models-nvidia-l4-parakeet-whisper-nemotron)
- [MarkTechPost: Nemotron 3.5 ASR June 2026](https://www.marktechpost.com/2026/06/06/nvidia-releases-nemotron-3-5-asr-a-600m-parameter-cache-aware-streaming-model-transcribing-40-language-locales-in-real-time/)
- [Parakeet TDT 1.1B HuggingFace](https://huggingface.co/nvidia/parakeet-tdt-1.1b)
- [Parakeet TDT streaming discussion (HF)](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2/discussions/3)
- [WhisperStreaming (ufal/whisper_streaming GitHub)](https://github.com/ufal/whisper_streaming)
- [faster-whisper turbo benchmark (GitHub issue #1030)](https://github.com/SYSTRAN/faster-whisper/issues/1030)
- [faster-whisper vs whisper.cpp comparison 2026](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026)
- [B-Whisper: Rare-word recognition improvement (arxiv 2502.11572)](https://arxiv.org/html/2502.11572v1)
- [Contextual Biasing for Streaming ASR via CTC Word Spotting (arxiv 2605.18222)](https://arxiv.org/abs/2605.18222)
- [Sherpa-ONNX hotwords documentation](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)
- [Whisper Courtside Edition — basketball domain biasing (arxiv 2602.18966)](https://arxiv.org/html/2602.18966)
- [Zero-shot trie-based contextual biasing (arxiv 2508.17796)](https://arxiv.org/pdf/2508.17796)
- [WhisperPipe streaming architecture (arxiv 2604.25611)](https://arxiv.org/pdf/2604.25611)
- [Contextual Biasing domain vocab without fine-tuning (arxiv 2410.18363)](https://arxiv.org/abs/2410.18363)
- [Improving endpoint detection streaming ASR conversational speech (arxiv 2505.17070)](https://arxiv.org/pdf/2505.17070)
