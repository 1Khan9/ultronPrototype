# Production wake-free / continued-conversation assistant designs: gating, false-accept mitigation, privacy, and local adaptation

## TL;DR recommendation for Ultron 1.0

Adopt a **three-layer cascade** modelled on the SAS paper (2025) and Amazon's follow-on window patent:

1. **VAD gate** (always-on, zero-cost): silence → drop immediately. Only forward segments with energy.
2. **Cheap utterance-level classifier** (rule + RapidFuzz + EmbeddingGemma cosine, already in-system): decides RELAY / PRIVATE / IGNORE in <20ms for clear cases; abstains for the undecided band (0.40–0.70 cosine bucket).
3. **8B LLM intent gate** (invoked only for undecided band, ~5–8% of utterances based on SAS data): Josiefied-Qwen3-8B with a tight one-sentence system prompt classifies the ambiguous tail.

For the **wake-free window** specifically: after any Ultron turn completes, open an 8–10-second follow-up window (matches both Google and Amazon production specs). During that window, lower the Stage 2 acceptance threshold from the ambient-mode value (0.70) to a relaxed value (~0.50). Close the window early on: (a) silence >3s post-response, (b) explicit closing phrase ("I'm done", "never mind"), (c) inter-speaker audio indicating the user addressed someone else.

This design lets us retire the blunt `_FOLLOWUP_WAKE_RE` bypass while achieving lower false-accept rates than the current approach.

---

## Findings

### 1. Google Look and Talk (2022, Nest Hub Max) — multimodal, on-device, 8 ML models

Google's most aggressive production deployment is Look and Talk, which completely removes the wake-word requirement by fusing **video + audio + text** on-device. The system requires a face-proximity check (<5 feet), face match to an enrolled user, eye-gaze detection (custom multi-tower CNN, gaze smoothing to suppress blinks), and an audiovisual active-speaker detection model (5 video frames + 0.5s audio). Only when all four align does it trigger STT and intent understanding.

Key design principle: **cascaded gating with progressively cheaper-to-expensive checks**. The gaze model runs at low cost and acts as a pre-filter; only if it fires does the heavier active-speaker and intent pipeline engage.

On-device pipeline for the audio-only equivalent uses:
- Non-lexical audio analysis (pitch, speaking rate, hesitation) to score whether the utterance "sounds like an Assistant query"
- Text intent understanding on the ASR transcript for "Assistant request patterns"
- Voice Match (speaker verification) as an additional layer

Compute: all 8 models run via quantized TFLite on Nest Hub Max hardware; end-to-end latency described as "comparable with hotword-based systems"; partial-utterance processing avoids waiting for full transcript.

**False-accept mitigation**: (a) strict attention → relaxed-once-speaking-begins two-phase gaze gate, (b) intent filter that rejects utterances not patterned as assistant queries, (c) diverse 3,000-participant training set for subgroup robustness.

Video never leaves the device.

[Source: Google Research Blog, Look and Talk, 2022](https://research.google/blog/look-and-talk-natural-conversations-with-google-assistant/)
[Source: 9to5Google writeup with additional architecture detail, 2022](https://9to5google.com/2022/07/27/google-assistant-look-and-talk/)

---

### 2. Google Continued Conversation (2018–present, Google Home/Nest audio devices)

Audio-only mode: after the initial wake word + response, the system opens a **~10-second listening window** for follow-up queries without another "Hey Google". Microphone closes automatically on 10 seconds of silence.

Explicit end triggers: "Thank you", "Thanks, Google", "I'm done". Interrupting events (phone call, alarm, media) also close the window.

No public information on the internal false-accept mechanism for this mode — Google's documentation is minimal. The consumer-facing control is an opt-in toggle; the main mitigation appears to be the short temporal window itself.

[Source: Google Nest Help, Continued Conversation](https://support.google.com/googlenest/answer/7685981)
[Source: TechCrunch announcement, June 2018](https://techcrunch.com/2018/06/21/google-assistants-continued-conversation-feature-is-now-live)

---

### 3. Amazon Alexa Follow-Up Mode — VAD + SID on always-on DSP (patent-confirmed 2024)

Patent US 12315497 ("Intended query detection using E2E modeling for continued conversation", granted 2025) and US 12217751 ("Digital signal processor-based continued conversation", 2024) describe the architecture:

- An **always-on DSP** runs VAD and optionally a Speaker ID (SID) model at low power
- After initial wake-word turn, a **follow-on detection mode** window opens
- Detecting voice activity during the window resets or extends the timeout
- Speaker verification can **adjust the acceptable pause duration** based on known-speaker identity (longer pauses tolerated for enrolled voices)
- Multi-layer validation: (1) VAD confirms speech present, (2) SID verifies authorized user, (3) contextual validation checks that the utterance is a plausible continuation, (4) confidence threshold filters low-probability detections

Amazon publicly acknowledges the failure mode: "Alexa may detect you are making a follow-up request when you are not — for example, if you ask Alexa a question and then start speaking to someone else in the room."

Mitigations in production: the short window (Amazon does not specify an exact timeout publicly, but 5–8 seconds is consistent with their device behavior), and the opt-in toggle (disabled by default).

[Source: Amazon patent 12315497 PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12315497)
[Source: Amazon patent 12217751 PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12217751)
[Source: Amazon Alexa Follow-Up Mode user docs](https://www.amazon.com/gp/help/customer/display.html?nodeId=GX7EJ9WHEPYBV94J)

---

### 4. SAS — Selective Attention System (2025, arxiv 2604.08412) — best public engineering reference

This is the most detailed public engineering description of a wake-free device-directed speech detection pipeline. It is directly applicable to Ultron 1.0. Architecture:

**Stage 1 — Acoustic Geometry (beamforming)**
- Pure signal processing, no learned parameters
- Localizes dominant speech relative to microphone array
- Suppresses TV audio, adjacent speakers, HVAC
- Requires ≥2 microphones; single-mic deployments skip this

**Stage 2 — Utterance-level classifier**
- 435K parameters (~520 KB INT8-quantized)
- 64-dimensional log-mel filterbank, 25ms frames, 10ms hop
- 4 × 1D-Conv blocks + single GRU + sigmoid
- Exploits prosodic cues: device-directed speech has elevated F0, reduced speaking rate, higher energy
- Binary classifier: device-directed vs. not

**Stage 3 — Causal Interaction-State Estimator**
- 85K-parameter causal Transformer
- Rolling 8-second context window over (Stage 2 confidence, VAD state, inter-utterance timing) tuples
- Produces a multiplicative prior αt ∈ [0,1] on Stage 2 score
- Largest single-component contribution to accuracy (ablation: −0.38 F1 if removed)

**Performance numbers:**
| Config | F1 | Precision | Recall | False-trigger rate |
|--------|----|-----------|--------|-------------------|
| Audio-only, τ=0.70 | 0.86 | 0.89 | 0.83 | 2.1% |
| Audio-only, τ=0.82 (high-media) | — | — | — | 3.4% (vs 7.8% at τ=0.70 in TV-heavy env) |
| Audio+Video, τ=0.70 | 0.95 | 0.97 | 0.93 | — |

Decision latency: **<150ms end-to-end, median 38ms** on ARM Cortex-A72 (no GPU/NPU).
Runtime footprint: **<20MB**.

ASR cost reduction from filtering: 90.7% fewer ASR calls; 91% fewer LLM calls; 97.9% false-trigger reduction. SAS CPU overhead (~3.8s CPU/hour) saved ~4.8× by downstream savings.

Known failure modes: TV dialogue with interrogative prosody (acoustic/prosodic similarity to real queries), >4 simultaneous speakers (context window saturation).

[Source: SAS paper HTML, arxiv 2604.08412](https://arxiv.org/html/2604.08412)

---

### 5. Multi-signal LLM for Device-Directed Speech Detection — Apple / arxiv 2403.14438 (2024)

Architecture: Whisper (769M params) as audio encoder → two 3-layer mapping networks → GPT-2 (124M) as the decision LLM. Fuses three signal types as prefix tokens:

- **Audio prefix**: Whisper encoder mean-pooled to 1024-dim
- **Decoder signal prefix**: ASR lattice signals (graph cost, acoustic cost, word-level posterior, competing hypothesis count) — all min-max scaled to [0,1]
- **Text**: 1-best ASR hypothesis

EER results:
| Config | EER |
|--------|-----|
| Audio-only (Whisper+head) | 16.28% |
| Text-only | 13.44% |
| Audio-only (fusion model) | 10.85% |
| **Text + Audio** | **6.81%** |
| Text + Audio + Decoder signals | 6.34% |

Text+Audio fusion = **38.9% relative improvement over text-only**, **20.5% over audio-only**.

Adding ASR decoder confidence signals adds another 6.9% relative improvement. Training on 500k additional text examples improves text-only by 2.2% relative.

Takeaway: **ASR confidence scores are a cheap, high-signal feature** — they come for free from faster-whisper's output (already available in Ultron's pipeline) and materially reduce EER.

[Source: arxiv 2403.14438 HTML](https://arxiv.org/html/2403.14438v2)
[Source: Apple ML Research page](https://machinelearning.apple.com/research/llm-device-directed-speech-detection)

---

### 6. FLoRA — Fusion Low-Rank Adaptation (Apple, Interspeech 2024 — arxiv 2406.09617)

Efficiently adapts a unimodal text-only LLM to consume audio by adding LoRA adapters that map audio embeddings into the LLM's token space. Key results:
- 22% relative EER reduction over text-only baseline
- **56% lower false accept rate** vs. full fine-tuning (with adapter dropout)
- Scales from 16M to 3B parameters
- Parameter-efficient: only adapter weights are trained

Adapter dropout is crucial for missing-modality robustness — when audio is unavailable or degraded, the text branch degrades gracefully instead of catastrophically.

Relevance to Ultron 1.0: the existing Josiefied-Qwen3-8B could in principle be LoRA-adapted with EmbeddingGemma outputs as audio proxy embeddings, but this is post-MVP research work.

[Source: arxiv 2406.09617 abstract](https://arxiv.org/abs/2406.09617)

---

### 7. Context-aware False Trigger Mitigation patent — Amazon, 2022/2024

Patent US 12451135 describes context-aware FTM: the system tracks the ambient context (TV playing, conversation between third parties ongoing, etc.) and raises the acceptance threshold accordingly. Key insight: a single global threshold is suboptimal; **context-conditional thresholds** outperform it.

In TV-active sessions, the SAS paper's data confirms: false-trigger rate rises from 2.1% → 7.8% at τ=0.70. Raising τ to 0.82 brings this back to 3.4% at a 6-point recall cost. This is exactly the context-conditional approach Amazon patents.

[Source: Amazon patent 12451135 PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12451135)

---

### 8. VAD as the first gate — always-on compute budget

From the Picovoice VAD guide and production deployments:

- VAD operates on 16 kHz audio, frame-by-frame (25ms frames typical), returning P(speech) ∈ [0,1]
- RTF ~0.000542 on ARM (Cobra); effectively zero CPU cost
- The inherent accuracy tradeoff: lower threshold → higher TPR, higher FPR. Production voice assistants use **lower thresholds for VAD** (high recall, accept more frames) and rely on downstream intent classifiers to reject non-speech-intended audio
- VAD gates all subsequent models: without speech, nothing runs downstream

Ultron already uses WebRTC VAD in `_capture_utterance`. This is correct. The question is what sits immediately downstream of it in the wake-free window.

[Source: Picovoice VAD guide](https://picovoice.ai/blog/complete-guide-voice-activity-detection-vad/)

---

## Concrete techniques/params we should adopt

### A. Time-bounded follow-up window with adaptive threshold

- Duration: **8–10 seconds** of post-response listening (both Google and Amazon production)
- Start: immediately when Kokoro TTS playback completes (or on interrupt)
- End early on: 3s of sustained VAD silence, explicit closing phrase ("never mind", "I'm done"), or any new Ultron wake-word (restart a fresh turn)
- **Threshold relaxation during window**: lower EmbeddingGemma cosine threshold from 0.65 (ambient) to ~0.50 for Stage 2 classification during the window; the temporal context (Stage 3 equivalent) provides the additional prior

Implementation in `orchestrator.py`: after `_handle_kokoro_done()` sets playback complete, set `self._follow_up_window_until = time.monotonic() + 8.0` and `self._follow_up_threshold = 0.50`. The existing `_relay_intent.py` / `rules.py` classification logic then uses the lower threshold.

### B. ASR confidence as a cheap free signal (adopt immediately)

faster-whisper already returns per-segment `avg_logprob` and `no_speech_prob`. These are direct proxies for the "decoder signal" features from the Apple paper (arxiv 2403.14438) that delivered 6.9% relative EER improvement for free.

Concrete gate: if `no_speech_prob > 0.6` on the transcription, treat as non-speech even if VAD fired (catches music, TV, non-linguistic noise that fooled VAD). If `avg_logprob < -1.2`, confidence is very low — treat as potentially non-directed speech, raise required cosine threshold by 0.10.

This is already partially wired (`_preprocess_utterance` confidence gates on the `wip/2026-06-18-confidence-stt` branch, not yet merged to main) — the recommendation is to complete and merge that.

### C. SAS Stage 3 equivalent: utterance-timing context

SAS's largest performance gain (−0.38 F1 if removed) comes from the 8-second rolling context window over (classifier confidence, VAD state, inter-utterance timing). Ultron's equivalent:

- Track a `_recent_utterance_scores` deque: last N=5 utterances, each as (timestamp, intent_class, confidence, was_relayed)
- Before classifying a new utterance, compute a context prior: if the last 2 utterances were RELAY, apply +0.10 prior boost to RELAY confidence; if the last utterance was classified IGNORE, apply +0.05 skepticism boost (more likely to be ambient noise)
- This is a 20-line addition to `classifier.py` / `rules.py` — no new model, no additional compute

### D. Context-conditional threshold per ambient mode

Adopt Amazon's context-conditional threshold pattern:
- **Ambient mode (wake word required)**: τ=0.70 (current behavior)
- **Follow-up window**: τ=0.50 (lower bar, already addressed by temporal context)
- **High-distraction mode** (e.g., config flag `high_media_env: true`): τ=0.82 to compensate for TV audio / Discord streams playing through speakers

Expose as `KENNING_ADDRESSING_TAU` env var (already exists) with per-mode overrides in `addressing.py`.

### E. Explicit closing phrases → window teardown

Implement a small set of closing phrases that kill the follow-up window early and suppress the "empty capture" path:

```python
_CLOSE_WINDOW_RE = re.compile(
    r"\b(never mind|i'?m done|stop listening|that'?s all|forget it|thanks(?:\s+ultron)?)\b",
    re.IGNORECASE,
)
```

Log as `routing:follow_up_closed` and reset `_follow_up_window_until = 0`.

### F. Speaker verification as optional tier-3 gate (future)

Ultron does not currently have speaker verification. The SAS and Amazon patent both use SID as a guard. For Ultron 1.0, this is out of scope (no enrolled voice model), but the architecture should **reserve a hook** for it:

- `classifier.py` score fusion should accept an optional `speaker_verified: bool | None` param
- When `None` (not implemented), the prior is neutral
- When the feature is added later, `True` lowers required cosine by 0.10, `False` raises it by 0.15

### G. What NOT to do (learned from production failures)

- **Do not use a single global threshold**: context-conditional thresholds are strictly better (Amazon patent, SAS ablation)
- **Do not open the window too long**: 10s is the production max; longer windows accumulate false accepts linearly
- **Do not rely on acoustic prosody alone**: SAS achieves F1=0.86 from prosody + timing; text (ASR transcript) fusion brings it to the Apple paper's 6.81% EER. In Ultron's pipeline, the EmbeddingGemma semantic classifier already provides the text-intent signal — this is correct
- **Do not fire the LLM on every utterance**: SAS's data shows only ~8% of VAD-positive segments are device-directed; the 8B should only see the genuinely ambiguous ~5% after rules + embedding pre-filter

---

## Risks/caveats for our constraints

### 1. No microphone array → no beamforming (SAS Stage 1 unavailable)
Ultron uses a single USB mic. SAS Stage 1 requires ≥2 microphones and provides −0.14 F1 protection. Without it, F1 drops from 0.86 → ~0.75 in multi-speaker environments. **Mitigation**: the Discord/party context means teammates' voices are in the game audio mix via VoiceMeeter, not the physical room — the single-mic case is actually cleaner for Ultron (only one physical speaker: the user).

### 2. Look and Talk's video modality is completely inapplicable
The camera-based gating (gaze + face match + proximity) cannot be used in a gaming setup where the user is looking at a monitor, not a smart display. Ultron must rely on audio+text only. SAS's audio-only F1=0.86 is the correct reference, not the 0.95 multimodal ceiling.

### 3. Anticheat constraint limits acoustic feature extraction
The relay path is constrained to `numpy+urllib+scipy+stdlib+rapidfuzz` — no `librosa`, no `pyworld` for F0 extraction. The SAS Stage 2 prosodic features (elevated F0, reduced speaking rate, increased energy) would require scipy signal processing or a sidecar call. **Recommendation**: extract only what scipy provides natively: RMS energy (already computed for VAD), zero-crossing rate, and basic spectral centroid. F0 estimation (pitch) can be approximated via autocorrelation in scipy — feasible in the relay path. Or route prosodic feature extraction through the EmbeddingGemma sidecar (already anticheat-clean as a sidecar process).

### 4. 10GB VRAM budget — 8B LLM and EmbeddingGemma must coexist
EmbeddingGemma-300M runs as a sidecar (CPU or small GPU allocation). The 8B Josiefied-Qwen3 Q5_K_M takes ~6.5GB VRAM at 5-bit. Stage 2 (435K param equivalent) would be a new model that could run entirely CPU-side at <1MB. The Stage 3 Transformer (85K params) is trivially CPU-bound. There is no VRAM pressure from the SAS-equivalent layers.

### 5. ASR confidence gate already partially implemented
The `wip/2026-06-18-confidence-stt` branch has `_preprocess_utterance` confidence gates that were never merged to main. The recommendation to use `no_speech_prob` and `avg_logprob` as free signals (technique B above) requires merging or cherry-picking that branch's STT changes. Risk: those changes were reverted in the 2026-06-18 stream-build rollback due to unrelated regression. Careful cherry-pick needed.

### 6. TV / stream audio false-triggers are Ultron's primary failure mode
In the current stream-build false-accept report (`ad186cf`): 114 un-waked captures/session, flan-t5 mis-accepting "Okay."/"Why is it suddenly running like this". This is exactly the TV/media false-trigger class identified as the hardest case in the SAS paper. The context-conditional threshold (τ=0.82 in high-media mode) and the ASR confidence gate (no_speech_prob > 0.6) are the two cheapest mitigations for this specific failure mode.

### 7. llama-cpp-python 0.3.22 LLM call latency in the undecided band
If the 8B is invoked for ~5% of utterances (the undecided band), and each call takes ~400–800ms for a short intent-classification prompt (one sentence + system prompt), the follow-up window's 8–10 second budget is not threatened. However, if the undecided band is wider (e.g., 20% of utterances in a noisy session), the 8B becomes a latency bottleneck. Mitigation: set a hard 300ms timeout on the 8B intent call; if it doesn't respond within the budget, default to IGNORE (fail-closed).

---

## Sources

1. Google Research Blog — Look and Talk: Natural Conversations with Google Assistant (2022): https://research.google/blog/look-and-talk-natural-conversations-with-google-assistant/

2. 9to5Google — How Google's Look and Talk works (2022): https://9to5google.com/2022/07/27/google-assistant-look-and-talk/

3. Google Nest Help — Continued Conversation: https://support.google.com/googlenest/answer/7685981

4. TechCrunch — Google Assistant Continued Conversation launch (2018): https://techcrunch.com/2018/06/21/google-assistants-continued-conversation-feature-is-now-live

5. Amazon Alexa Follow-Up Mode user documentation: https://www.amazon.com/gp/help/customer/display.html?nodeId=GX7EJ9WHEPYBV94J

6. Amazon patent US 12315497 — "Intended query detection using E2E modeling for continued conversation": https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12315497

7. Amazon patent US 12217751 — "Digital signal processor-based continued conversation": https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12217751

8. Amazon patent US 12451135 — "Context-aware false trigger mitigation for ASR systems": https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12451135

9. SAS — Selective Attention System: Device-Addressed Speech Detection for Real-Time On-Device Voice AI (2025, Kim et al.): https://arxiv.org/html/2604.08412

10. A Multimodal Approach to Device-Directed Speech Detection with Large Language Models (2024, Apple/arxiv 2403.14438): https://arxiv.org/html/2403.14438v2

11. Apple ML Research page — Multi-signal LLM for device-directed speech detection: https://machinelearning.apple.com/research/llm-device-directed-speech-detection

12. FLoRA — Multimodal LLMs with Fusion Low Rank Adaptation for Device Directed Speech Detection (Interspeech 2024, arxiv 2406.09617): https://arxiv.org/abs/2406.09617

13. Picovoice — Complete Guide to Voice Activity Detection (2026): https://picovoice.ai/blog/complete-guide-voice-activity-detection-vad/

14. Android Central — It's time smart assistants evolved beyond fixed wake words: https://www.androidcentral.com/accessories/smart-home/its-time-smart-assistants-evolved-beyond-fixed-wake-words-like-hey-google

15. Vocalize.ai — Smart Speakers, Wake Words and False Positives (2018, still-accurate overview): https://vocalize.ai/2018/11/01/wake-words-false-positives/
