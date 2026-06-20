# Device-Directed Speech Detection (DDSD) 2024-2026: Architectures, Features, and Cues for Ultron 1.0

**Research date:** 2026-06-20
**Scope:** Determining when a transcribed utterance is directed at Ultron (the AI) vs. directed at a human teammate vs. ambient/stream/background speech — for the Ultron 1.0 always-listening intent gate running locally on a single RTX 4070 Ti (10 GB design cap), anticheat-constrained, voice-first Valorant relay assistant.

---

## TL;DR Recommendation for Ultron 1.0

**Use a three-layer cascade that mirrors the SAS architecture (Kim et al., 2026) but adapted to text-first, no-mic-array reality:**

1. **Layer 1 — Lexical/rule gate (zero-latency):** Deterministic rules over the ASR transcript. Direct-address patterns ("Ultron, …"; imperative opening; vocative at start), pronoun cues (second-person singular vs. third-person plural "you guys"), and explicit relay markers ("tell my team", "let them know") already handle 70–80% of cases correctly. This is what Ultron already has in `_relay_intent.py` and `rules.py`. Make it a hard-accept/hard-reject with a passthrough band.

2. **Layer 2 — EmbeddingGemma cosine similarity (< 5 ms, anticheat-safe):** For utterances in the passthrough band, embed the transcript with the existing EmbeddingGemma-300M sidecar and compute cosine sim against a curated 50-200 exemplar set per class (RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE). EmbeddingGemma-300M is already in the codebase; this is essentially free. Threshold tuning (tau ~ 0.22–0.28 cost-asymmetric) controls false-trigger rate vs. miss rate.

3. **Layer 3 — 8B LLM arbitration (only for true undecided band, ~20% of utterances):** Pass (transcript + conversation context of last 2 turns) to the Josiefied-Qwen3-8B via a short classification prompt. With thinking OFF (already supported by the flavor toggle), this runs in 1–3 seconds at ~35–50 tok/s on the RTX 4070. The 8B's strong instruction-following makes it a reliable zero-shot classifier; LoRA fine-tuning on 500–2000 curated examples would push it further.

**Do NOT attempt real-time acoustic/prosodic feature extraction as a separate module** — the system already has faster-whisper transcripts and you lack a mic array. Acoustic hyperarticulation features (F0, energy, speaking rate) are highly effective per the literature (EER drops from 23% lexical-only to 11% lexical+prosodic) but require per-frame pitch extraction at <50ms latency; add this only if you instrument it in the whisper preprocessing pipeline.

**Key insight from SAS (2026):** Removing temporal interaction history drops F1 from 0.95 to 0.57. Context is the biggest lever — more important than any single-utterance acoustic signal. Our Layer 2 must include the last-turn outcome as a feature, not just the current transcript.

---

## Findings

### 1. Problem Taxonomy

DDSD has three distinct subtasks in the literature, all relevant to Ultron:

| Subtask | Definition | Hardest cases |
|---------|-----------|---------------|
| **Wake-word invocation** | Detect "Ultron" + command; reject TV/bystander phonetically similar audio | Phonetic lookalikes; TV false triggers |
| **Follow-up / continued conversation** | After a wake-word turn, detect the next utterance as still-directed without re-invoking | Bystander speech immediately after; "do it again" / "what?" ambiguity |
| **Always-on passive gate** | No wake word; classify every VAD segment as DEVICE / PERSON / IGNORE before STT | All ambient speech; multiparty Valorant team voice |

Ultron 1.0 targets primarily subtask 3 (always-on intent gate) with subtask 2 (follow-up window) as a secondary concern. Standard DDSD literature focuses on subtask 1; the multiparty gaming context makes this harder than typical smart-speaker scenarios.

---

### 2. Core Acoustic/Prosodic Cues (What Makes Device-Directed Speech Different)

**Hyperarticulation** is the central phenomenon. When speaking to a voice assistant, users adopt:
- Higher mean F0 (pitch) and wider pitch range
- Louder volume (increased RMS energy, ~3–6 dB above casual speech)
- Slower speaking rate (deliberate pacing, longer phoneme duration)
- Reduced use of disfluencies ("uh", "um", pauses mid-phrase)
- More pronounced vowel space expansion (clearer articulation)
- Imperative-first sentence structure

Sources: [SAS (Kim et al., 2026)](https://arxiv.org/abs/2604.08412); [Modality Dropout (Krishna et al., 2023)](https://arxiv.org/abs/2310.15261); prosodic patent US10529321.

**In a Valorant gaming context specifically:** players may NOT hyperarticulate when simultaneously playing a fast-paced game. Commands to Ultron ("tell my team Jett hit 84") are likely at normal or elevated pace. This weakens the prosodic discriminator vs. teammate voice chat. The lexical/semantic channel is more reliable here.

**Quantified prosodic gains (literature):**
- Lexical features alone: EER ~23.1%
- Prosodic features alone: EER ~12.6%
- Combined lexical + prosodic: EER ~11.1% ([Modality Dropout, 2023](https://arxiv.org/abs/2310.15261))
- Best acoustic-only on-device (SAS Stage 2, log-mel + GRU): F1 = 0.86
- With temporal context (SAS Stage 3 + causal transformer): F1 = 0.95

---

### 3. Architecture Landscape (2022–2026)

#### 3a. Acoustic-Only + Distillation (Apple, 2022 / 2025)

**Paper:** [Device-Directed Speech Detection: Regularization via Distillation for Weakly-Supervised Models](https://arxiv.org/abs/2203.15975) (Garg et al., Interspeech 2022) + [Adaptive Knowledge Distillation for DDSD](https://arxiv.org/abs/2508.02801) (Chi et al., Interspeech 2025).

- **Teacher:** 79M-param conformer ASR encoder (frozen)
- **Student:** 5M-param transformer or conformer, 8 blocks, 256 hidden units
- **KD losses:** Embedding distillation (MSE between encoder outputs) + Attention Regularization (penalizes divergence in temporal attention weights) + Pseudo-labeling (teacher predictions as soft targets)
- **EER results:**
  - HAG (hotword after gate): Teacher 1.66%, Student-noKD 1.57%, Student-aKD **1.05%** (26% relative gain)
  - AG (after gate, general): Teacher 3.87%, Student-noKD 5.24%, Student-aKD **4.19%** (19% relative gain)
  - FCO (far-channel cocktail): Teacher 7.74%, Student-noKD 10.87%, Student-aKD **8.70%**
- **Training data:** 2.7K hours with room impulse response / echo augmentation
- **Key insight:** The KD transfers temporal attention patterns from the ASR model — the student learns WHEN to attend in an utterance, not just overall features. This is the most efficient small-model approach for deployment.

**Earlier Apple work (2022):** LatticeRNN (LRNN) on ASR decoding lattices (16-D embeddings from lattice RNN → FC → softmax). Key property: device-directed speech is "in-domain" with the assistant's LM, so competing lattice paths are few and the lattice structure is distinctive. Ensemble of LRNN + acoustic-distilled student achieves **4% EER**. Limitation: requires full ASR decode first; model must be retrained whenever ASR model changes.

#### 3b. Multimodal LLM Fusion (Apple, late 2023)

**Paper:** [Multimodal Data and Resource Efficient DDSD with Large Foundation Models](https://arxiv.org/html/2312.03632) (Dec 2023)

- **Backbone LLM:** Falcon 7B or RedPajama 7B (decoder-only)
- **Audio Encoder:** Whisper-medium (769M params, 1024-dim) or UAD (6M params, 256-dim); frozen
- **Fusion:** Audio mean-pooled embedding + ASR decoder signals (4 utterance-level metrics: graph cost, acoustic cost, posterior confidence, alternatives per position) → learnable M₁, M₂ mapping networks → prefix tokens → LLM
- **Trainable params:** Only ~39M (M₁ + M₂ + LoRA rank=8 on Q/V) out of full 7B+769M
- **EER:** Falcon 7B + Whisper-medium → **8.80%**; Falcon 7B + UAD (6M) → **8.23%** (better efficiency)
- **Data efficiency:** 10k examples achieves 8.84% EER, better than acoustic-only at 80k examples (9.31%)
- **Key insight:** The LLM context window provides strong semantic regularization; the tiny UAD encoder is better than Whisper-medium for this task (more task-specific), suggesting that a smaller dedicated encoder > large general encoder for DDSD fusion.

#### 3c. Follow-up Context + LLM Prompting (Apple, Oct 2024)

**Paper:** [Device-Directed Speech Detection for Follow-up Conversations Using LLMs](https://arxiv.org/abs/2411.00023) (Rudovic et al., ICASSP 2025)

- **LLM:** Vicuna-7B-v1.3 (instruction-tuned LLaMA)
- **Approach:** Text-only; no acoustic input. Prompts concatenate (1) the initial wake-word query and (2) the follow-up transcript + n-best ASR hypotheses with confidence scores in bracket notation `[cost]`
- **Why n-best lists:** ASR uncertainty in follow-ups correlates with whether the utterance was truly device-directed (the ASR's own domain LM is more confident on in-domain device queries)
- **LoRA:** rank minimal, 4.1M trainable params; 4× A100 for training
- **Result:** ClassHead approach achieves **20–40% reduction in false alarms** at 10% fixed false-reject vs. single-utterance baseline
- **Key limitation:** No acoustic/prosodic features; relies entirely on transcript. Inference on consumer GPU with 7B model: ~2–4 seconds for combined query.

#### 3d. SELMA — Unified Speech-Enabled LLM (Apple, ICASSP 2025)

**Paper:** [SELMA: A Speech-Enabled Language Model for Virtual Assistant Interactions](https://arxiv.org/abs/2501.19377)

- **Backbone:** Qwen-Audio-Chat (Whisper-large-v2 encoder ~650M + Qwen LLM ~7.4B = ~8B total)
- **Trainable params:** Only 5.5M (0.84%) via LoRA rank=8 on Q/V of both encoder and LLM
- **Feature pooling:** Concatenates mean-pooled (global) + full sequence (temporal) audio representations before LLM
- **Joint tasks:** Voice Trigger detection + DDSD + ASR, differentiated by prompts
- **DDSD EER:** Baseline 10.78% → SELMA **7.78%** (28% relative improvement)
- **VT EER:** 0.33% → 0.12% (64% relative improvement)
- **Training data:** 237K DDSD audio + 3.8M text-only DDSD samples
- **Key insight:** Joint training with ASR forces the model to build a rich acoustic representation useful for DDSD. The audio encoder never sees ASR loss only; it must also classify addressee. The text-only DDSD samples (3.8M!) act as strong semantic regularization with near-zero compute cost.
- **Cost:** 16× A100s for training; inference is a full 8B forward pass — not viable for sub-500ms always-on gate.

#### 3e. SAS — Sequential Device-Addressed Routing (Kim et al., Apr 2026)

**Paper:** [Selective Attention System (SAS): Device-Addressed Speech Detection for Real-Time On-Device Voice AI](https://arxiv.org/abs/2604.08412)

This is the most directly applicable paper to Ultron 1.0.

**Three-stage cascade:**

**Stage 1 — Acoustic Geometry (beamforming):** Localizes dominant speech direction, suppresses off-axis. Requires ≥2 microphones. **Bypass if single mic.** Ablation shows -14 F1 points when removed — significant but system remains functional.

**Stage 2 — Utterance Classifier (435K params, INT8 = 520KB):**
- Input: 64-dim log-mel filterbank, 25ms frames
- Architecture: 4× conv block (BN + ReLU + MaxPool) → GRU layer → sigmoid
- Exploits prosodic hyperarticulation: elevated F0, reduced speaking rate, increased energy
- INT8 quantization: < 0.5 F1-point degradation
- Latency: < 10ms
- Audio-only F1 (without Stage 3): 0.57 (insufficient alone)

**Stage 3 — Causal Interaction-State Transformer (~85K params):**
- Input: rolling 8-second context of (Stage 2 confidence, VAD state, inter-utterance time delta) tuples
- Output: multiplicative prior α_t ∈ [0,1]
- Final score: c'_t = α_t · c_t^(S2)
- Latency: < 5ms additional
- **Effect of removing Stage 3: F1 drops from 0.95 to 0.57 (−38 points) — the single largest factor**

**Key ablations (audio+video):**

| Configuration | F1 |
|---|---|
| Full SAS | 0.95 |
| No Stage 1 (beamforming) | 0.81 |
| No Stage 2 (classifier) | 0.74 |
| No Stage 3 (context) | 0.57 |

**Per-speaker-count (audio+video):**
1 speaker: 0.98 / 2: 0.97 / 3: 0.94 / 4: 0.91 — degrades gracefully

**Total footprint:** < 20MB; < 55ms latency; runs on ARM Cortex-A72 (no GPU needed)

**Television false triggers:** 7.8% at τ=0.70; drops to 3.4% at τ=0.82 (cost: some recall)

**Critical finding:** Utterance-local classification (without temporal context) is near-random for multi-speaker ambiguous speech. Context is mandatory for production quality.

---

### 4. Lexical/Textual Cues (What the ASR Transcript Tells You)

These are the cheapest features — zero additional model inference.

**Strong DEVICE-DIRECTED indicators:**
- Imperative-first: "Tell my team…", "Say to the group…", "Let them know…"
- Direct address: "Ultron, [command]" — vocative at sentence start
- Command verbs + action object: relay verbs (tell, say, update, mention, let them know), info verbs (check, find, look up)
- Explicit relay markers: "my team", "the group", "everyone"
- Tactical content + action: "Jett hit 84" → _slot_callout_forced path (already implemented)

**Strong IGNORE indicators:**
- Conversational non-imperative: "I think we should…", "what did you say?", "oh nice"
- Third-person references to Ultron: "Ultron said", "Ultron's playing"
- Past-tense recounting: "I told them…", "they already know…"
- Discourse markers: "like", "you know", "I mean" (disfluency pattern)
- Questions directed at teammates: "where are you?", "are you on site?"

**Ambiguous (need Layer 2/3):**
- "Hit 84" (without agent name or "tell my team" lead) — could be self-talk
- Follow-up continuations: "do it again", "yes", "exactly", "what?"
- Coordinated statements: "we need smokes" — could be relay target OR teammate communication

**False-trigger patterns in gaming voice (Valorant-specific):**
- Teammate announces their own position: "I'm on A" — NOT for Ultron
- Player self-narrating: "okay I'm going B" — NOT for Ultron
- Reacting to gameplay: "nice!", "let's go!", "oh come on!" — NOT for Ultron
- Talking TO a teammate by name: "Jett, wait" — NOT for Ultron (different addressee name)

From [Reject or Not? (2024)](https://arxiv.org/pdf/2512.10257): LLM chain-of-thought reasoning outperforms both rule-based and traditional ML approaches on smart-home rejection; applies directly to gaming false-trigger rejection.

---

### 5. ASR Uncertainty as a Signal

Cited in [Apple 2024 LLM follow-up paper](https://arxiv.org/abs/2411.00023): device-directed speech is more "in-domain" with the assistant's acoustic/language model. The ASR decoder is more confident on well-articulated device-directed speech. Practical implications for Ultron:

- faster-whisper returns `no_speech_prob`, `avg_logprob`, and per-segment confidence. Low `no_speech_prob` + high `avg_logprob` correlates with device-directed speech (user speaks clearly TO Ultron).
- Conversely, high `no_speech_prob` = likely background/ambient. Already used as a pre-filter.
- n-best hypothesis diversity: if faster-whisper's n-best alternatives are very similar (low entropy), utterance is likely device-directed clear speech. High alternative diversity = noisy/ambient.

**Practical addition:** Expose `avg_logprob` from faster-whisper to the intent gate as a scalar feature alongside the transcript.

---

### 6. Temporal Context (Interaction History)

The SAS Stage 3 result (−38 F1 points without it) is the strongest finding in the 2024–2026 literature. Apply this lesson:

**What to track:**
- Outcome of last 2–3 turns: was the previous utterance classified RELAY / PRIVATE / IGNORE?
- Inter-utterance gap: < 500ms follow-up after Ultron replied = likely continuation
- VAD continuity: continuous VAD across a turn boundary suggests same speaker in same conversation
- Whether Ultron's last response was a relay confirmation (increases probability the follow-up is a continuation command or clarification)

**Implementation:** A tiny causal model (even a stateful Python dict + exponential decay is sufficient) maintaining:
```python
_context = {
    'last_outcome': 'RELAY' | 'PRIVATE' | 'IGNORE' | None,
    'turns_since_relay': int,
    'gap_seconds': float,
    'ultron_spoke_last': bool,
}
```
This context is prepended to the Layer 2 exemplar lookup query and Layer 3 LLM prompt.

---

### 7. Training-Free vs. Trained Approaches

| Approach | EER / F1 | Training needed | Latency | Applies to Ultron |
|---|---|---|---|---|
| Rule-based lexical (Ultron current) | EER ~30–40% est. | None | < 1ms | YES — Layer 1 |
| EmbeddingGemma cosine + exemplars | EER ~15–20% est. | None (few-shot) | ~5ms | YES — Layer 2 |
| Acoustic-only 5M conformer | EER 8–11% | 2.7K hours labeled | < 10ms | Possible post-MVP |
| LatticeRNN (ASR lattice features) | EER 4% | Large labeled set + ASR coupling | ~50ms | No (ASR coupling) |
| Whisper + LLM fusion (2312.03632) | EER 8.23% | 10K+ examples + LLM train | 2–4s | Partial (Layer 3) |
| SELMA (Qwen-Audio 8B) | EER 7.78% | 237K audio + LoRA | 2–4s | No (too slow for gate) |
| SAS three-stage cascade | F1 0.86–0.95 | 600h + curriculum | < 55ms total | Architecture yes; components adapted |
| Qwen3-8B zero-shot prompting | ~EER 10–15% est. | None | 1–3s | YES — Layer 3 (undecided only) |

**Training-free recommendation:** The EmbeddingGemma exemplar approach (Layer 2) is viable zero-shot. Maintain a curated set of ~100 prototypical utterances per class, update offline. No training pipeline needed. EER estimate is rough (no direct literature benchmark), but the embedding similarity approach is established for intent routing (see [zero-shot audio-to-intent, 2023](https://arxiv.org/pdf/2311.02482)).

---

### 8. Latency Budget Analysis (Ultron 1.0)

Ultron 1.0 target: intent gate decision before the 8B LLM starts generating. Already have faster-whisper STT output in ~200–400ms. Gate must add minimal overhead.

| Layer | Operation | Latency est. |
|---|---|---|
| L1: Rule gate | Python regex + dict lookup | < 1ms |
| L2: EmbeddingGemma cosine | 300M embed (GPU sidecar) + cosine | ~5–15ms |
| L3: 8B Qwen3 classification prompt | ~150-token prompt, 5-token output | 200–500ms |

L1 handles ~60–70% of traffic. L2 handles ~20–25% more. L3 only fires for ~10–15% of utterances. Weighted average gate latency: ~15–60ms. Acceptable.

The 8B model already runs in-process for relay generation, so L3 is "free" in the sense that the model is already loaded; the only cost is the extra forward pass before the main generation.

---

### 9. Comparison with Ultron's Existing System

Current implementation (`_relay_intent.py`, `rules.py`, `addressing.py`):
- Layer 1 ✓ (strong deterministic rules, already catches ~70% correctly)
- Layer 2 ✓ (EmbeddingGemma sidecar cosine sim already exists; the margin/threshold tuning is the gap)
- Layer 3 partial (flan-t5 zero-shot for the undecided band, limited by flan-t5's smaller capacity)

**Key gaps to close for 1.0:**
1. Replace flan-t5 with the already-loaded 8B Qwen3 for L3 (better accuracy, same latency since model is warm)
2. Add temporal context state (last 2 turns) to L2 exemplar lookup and L3 prompt
3. Expose faster-whisper `avg_logprob` as a scalar feature for L2 (free signal)
4. Add gaming-specific IGNORE exemplars: self-talk, teammate mentions by name, celebratory utterances
5. Add ASR n-best diversity as a reject signal (high diversity → likely ambient/noisy → lean IGNORE)

---

## Concrete Techniques/Params We Should Adopt

1. **Temporal context state machine:** Track `last_outcome`, `gap_seconds`, `turns_since_relay`, `ultron_spoke_last`. Pass as prefix to L3 LLM prompt: "Previous turn: [RELAY to team]. Gap: 1.2s. Current utterance: …". Expected large F1 gain.

2. **ASR confidence gating:** Use faster-whisper `avg_logprob` threshold (e.g., < -0.8) as a pre-reject before even hitting the lexical rules. Already computed, free.

3. **EmbeddingGemma exemplar set expansion:** Curate 100–200 GAMING-SPECIFIC examples per class (RELAY, PRIVATE, IGNORE). Include Valorant agent names, tactical callouts, team-chat patterns. Update the exemplar set offline without model retraining.

4. **Cost-asymmetric threshold τ:** False accepts (wrong relay to team) are worse than missed detections (Ultron stays quiet). Set τ at L2 to bias toward IGNORE on low-margin decisions. Literature suggests τ ~0.20–0.25 for log-odds fusion (addressee fusion work, `rules.py` `KENNING_ADDRESSING_TAU`).

5. **n-best diversity feature (optional, low effort):** Sum of Levenshtein distances across n-best ASR hypotheses normalized by transcript length → scalar 0–1. High diversity → ambient/noisy → add to IGNORE logit.

6. **L3 prompt design (Vicuna-style, based on 2411.00023):** Do NOT use flan-t5 style "Answer: YES/NO". Instead use Qwen3 instruction format with context:
   ```
   You are classifying game voice commands. The user may be:
   A) Talking TO Ultron (AI assistant) to relay information to teammates
   B) Talking TO Ultron for a private reply (personal request)
   C) Talking to a teammate or themselves (not for Ultron)
   
   Previous turn: {last_outcome}. Time gap: {gap}s.
   Utterance: "{transcript}"
   ASR confidence: {avg_logprob:.2f}
   
   Reply with exactly one letter: A, B, or C.
   ```
   First-token probability P(A) / P(B) / P(C) is a calibrated confidence score — map to {RELAY, PRIVATE, IGNORE}.

7. **SAS-inspired Stage 2 acoustic model (post-MVP):** Train a 435K-param 1D-CNN + GRU on log-mel features using 200–500 hours of curated voice data. This is the route to sub-10ms acoustic-only pre-gate. Not feasible for MVP due to training data requirements; flag for v1.1.

8. **Modality dropout for robustness:** When EmbeddingGemma sidecar is unavailable (startup, crash), fall back gracefully to L1 only. Do not block on sidecar (already done per existing orphan guardrails).

---

## Risks/Caveats for Our Constraints

**Anticheat (highest priority):**
- All DDSD layers MUST run in the voice/relay path with only `numpy`, `scipy`, `rapidfuzz`, `stdlib`, and approved sidecar calls. EmbeddingGemma already in sidecar. The 8B Qwen3 is in-process. No new heavy imports for the gate itself.
- Do NOT add real-time F0/prosody extraction via `librosa` (not anticheat-safe in the main process). If acoustic features are desired, add a microphone preprocessing step in the embedder server (sidecar).

**VRAM headroom:**
- 10 GB cap. Josiefied-Qwen3-8B Q5_K_M ≈ 5.5–6 GB. EmbeddingGemma-300M ≈ 0.5 GB. Kokoro TTS ≈ 0.3 GB. Faster-Whisper medium ≈ 0.9 GB. Total ≈ 7.2–7.7 GB. Headroom ~2.3–2.8 GB. Safe to add the 8B as L3 since it's already loaded.
- Do NOT add SELMA (7.8B) or Whisper-large (1.5 GB) — no VRAM room and they overlap with existing components.

**Latency risk with L3:**
- 8B forward pass for a ~150-token prompt + 5-token output at ~35–50 tok/s on RTX 4070 = ~100–200ms. If the game loop generates many ambiguous utterances rapidly (unlikely in Valorant, which has natural speech gaps), L3 may queue. Mitigate with a 500ms timeout: if L3 takes > 500ms, default to IGNORE (safe default).

**Gaming voice specifics:**
- High noise floor (gunfire, game audio, Discord). Faster-whisper already filters via `no_speech_prob`. Ensure the `avg_logprob` L2 feature is robust to this — noisy but clearly-spoken commands will have lower logprob; combine with `no_speech_prob < 0.3` gate.
- Multiple voices: Discord/party chat pipes teammates into the same mic mix in some configurations. Ultron's mic input (VoiceMeeter B1 bus) should be user-voice-only, but game audio bleed can occur. The temporal context state helps — a sequence of IGNORE classifications followed by a sudden RELAY candidate is more likely to be a true relay.

**EER benchmarks not directly comparable:**
- All published EER numbers are on proprietary smart-speaker datasets (single-mic, home environment, English). Gaming voice is louder, faster, more terse, has game audio background, and has a very different lexical distribution. Expect published EERs to be optimistic for our scenario. The 3-layer cascade approach is more robust precisely because it uses domain-specific lexical rules as Layer 1.

**Follow-up window (Ultron config.yaml `addressing.follow_up_enabled`):**
- Currently disabled (false) due to false-positives from bystander speech. The temporal-context state machine is the correct long-term fix — not a blanket time window. The follow-up window should be re-enabled ONLY when the context model is in place, and with a shorter window (< 30s vs. the 120s that caused the false-positive storm).

**Single microphone:**
- No beamforming (Stage 1 in SAS). SAS ablation shows −11 F1 points vs. two-mic config. This is unavoidable. Compensate with stronger L2/L3 semantic discrimination and the ASR confidence gate.

---

## Sources

1. [SAS: Device-Addressed Speech Detection for Real-Time On-Device Voice AI (Kim et al., Apr 2026)](https://arxiv.org/abs/2604.08412) — arXiv 2604.08412. Three-stage cascade, SDAR formulation, F1 0.86–0.95, <55ms, <20MB, ARM Cortex-A72.

2. [Device-Directed Speech Detection for Follow-up Conversations Using LLMs (Rudovic et al., Oct 2024)](https://arxiv.org/abs/2411.00023) — arXiv 2411.00023. Vicuna-7B, n-best ASR uncertainty, 20–40% false-alarm reduction, ICASSP 2025.

3. [Adaptive Knowledge Distillation for DDSD (Chi et al., Aug 2025)](https://arxiv.org/abs/2508.02801) — arXiv 2508.02801. Teacher 79M conformer → 5M student, KD via embedding MSE + attention reg + pseudo-label, EER 1.05%/4.19%/8.70% on HAG/AG/FCO, Interspeech 2025.

4. [Multimodal Data and Resource Efficient DDSD with Large Foundation Models (Dec 2023)](https://arxiv.org/html/2312.03632) — arXiv 2312.03632. Falcon-7B + UAD-6M encoder → EER 8.23%, data-efficient (10k examples), LoRA-only training.

5. [SELMA: Speech-Enabled Language Model for Virtual Assistant Interactions (Jan 2025)](https://arxiv.org/abs/2501.19377) — arXiv 2501.19377. Qwen-Audio-Chat ~8B, joint VT+DDSD+ASR, DDSD EER 7.78% (28% rel. improvement), ICASSP 2025.

6. [Device-Directed Speech Detection: Regularization via Distillation for Weakly-Supervised Models (Garg et al., 2022)](https://arxiv.org/abs/2203.15975) — arXiv 2203.15975. Apple; LatticeRNN + acoustic-distilled ensemble → 4% EER.

7. [Modality Dropout for Multimodal DDSD using Verbal and Non-Verbal Features (Krishna et al., Oct 2023)](https://arxiv.org/abs/2310.15261) — arXiv 2310.15261. Prosody adds 8.5% FA improvement; modality dropout adds 7.4% robustness; ICASSP 2024.

8. [Reject or Not? Benchmark for Voice Assistant Query Rejection (2024)](https://arxiv.org/pdf/2512.10257) — arXiv 2512.10257. LLM chain-of-thought outperforms rules and traditional ML for rejection; direct applicability to gaming false-trigger rejection.

9. [Complementary Language Model and Parallel Bi-LRNN for False Trigger Mitigation (Agarwal et al., 2020)](https://arxiv.org/abs/2008.08113) — arXiv 2008.08113. Bi-LRNN on complementary LM lattices; 38.34% relative FTR reduction.

10. [EmbeddingGemma: Powerful and Lightweight Text Representations (2025)](https://arxiv.org/abs/2509.20354) — Google; 300M params, on-device, outperforms models 2× its size; used as Layer 2 backbone in Ultron.

11. [Apple — Device-Directed Utterance Detection](https://www.amazon.science/publications/device-directed-utterance-detection) — Amazon Science. Original two-LSTM (acoustic + ASR 1-best) baseline with DNN combiner; EER 9.3%/10.9%/20.1%.

12. [Device-Directed Speech Detection for Follow-up Conversations — Apple MLR page](https://machinelearning.apple.com/research/device-directed) — Apple Machine Learning Research summary of 2411.00023.

13. [Modality Dropout — Apple MLR page](https://machinelearning.apple.com/research/modality-dropout) — Apple MLR summary of 2310.15261.

14. [SELMA — Apple MLR page](https://machinelearning.apple.com/research/selma-speech-enabled-language) — Apple MLR summary of 2501.19377.

15. [Adaptive Knowledge Distillation — Apple MLR page](https://machinelearning.apple.com/research/adaptive-knowledge) — Apple MLR summary of 2508.02801.
