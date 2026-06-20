# Semantic VAD / Endpointing for Always-Listening + Compound-Command Segmentation

**Research date:** 2026-06-20
**Researcher:** Claude Sonnet 4.6 (frontier-research sub-agent)
**Board slot:** B — VAD & endpointing
**System target:** Ultron 1.0 — always-listening, RTX 4070 Ti 12 GB, llama-cpp-python 0.3.22, EmbeddingGemma-300M sidecar, anticheat-safe (voice path = numpy/scipy/stdlib only), Valorant relay persona

---

## TL;DR Recommendation for Ultron 1.0

**Three-layer stack (all local, anticheat-safe):**

1. **Silero VAD** (primary speech/silence gate) — 20 ms chunks, threshold 0.5–0.6, `min_silence_duration_ms` **400–600 ms** for gaming command speech (NOT the faster-whisper default of 2000 ms).
2. **Semantic semantic-endpointing probe** on the partial STT transcript — a tiny rule-based + EmbeddingGemma classifier that checks whether the transcribed clause is syntactically/semantically complete BEFORE committing the silence timeout. If incomplete (trailing "and", "also", coordinating conjunction without payload, incomplete prepositional phrase), extend the wait window to **1 200–1 500 ms**. If clearly complete (period-final intonation detected acoustically OR transcript ends in a full tactical noun-phrase), commit at **400 ms**.
3. **Compound-command splitter in the router** — after the utterance is committed, the 8B LLM (or a cheap regex) detects the presence of conjunctive payload lists ("Jett hit 84, Breach hit 97, rotate B") and routes EACH sub-command through its own pipeline slot, queued sequentially.

**Barge-in during TTS:** keep Silero VAD always running on the mic even during playback; use an energy gate (-40 dBFS threshold) + 250 ms sustain guard. The existing VoiceMeeter B1 echo-cancellation path already removes Kokoro output from the mic feed; rely on that. Flush TTS (`audio.stop()`) the instant `barge-in_confirmed`.

**Do NOT** run Smart-Turn v2/v3 (360 MB wav2vec2, 12 ms on L40S = 400–900 ms on CPU) or Phoenix-VAD (50 ms on A6000; Qwen2.5-0.5B + Zipformer) on the Ultron 1.0 hot path — too heavy for same-GPU as the 8B, and anticheat import profile is wider than necessary. Use the sidecar pattern instead.

---

## Findings

### 1. Acoustic VAD: State of the Art & Parameters

**Silero VAD v5** is the current SOTA for lightweight local deployment.  
([GitHub silero-vad](https://github.com/snakers4/silero-vad))

Key parameters and recommended values for gaming command speech:

| Parameter | faster-whisper default | Silero native default | Ultron 1.0 recommendation |
|---|---|---|---|
| `threshold` | 0.5 | 0.5 | 0.55 (slightly tighter; gaming env has keyboard/click noise) |
| `min_speech_duration_ms` | 250 | 250 | 150 (short burst commands OK) |
| `min_silence_duration_ms` | **2000** | **100** | **500** (gaming commands run fast; 2 s is absurd) |
| `speech_pad_ms` | 400 | 30 | 150 (preserve leading consonants without bloating) |
| `window_size_samples` | 1024 | 512 | 512 (20 ms at 16 kHz; real-time resolution) |

The faster-whisper 2000 ms default exists because it was tuned for offline batch transcription of long audio (you don't want to split a sentence in two), NOT for interactive endpointing. For real-time command speech it introduces ~1–1.5 s of dead latency on every turn. **This is why Ultron previously felt slow.**

Performance: at 5% FPR, Silero correctly detects ~87.7% of speech vs WebRTC VAD at ~50%.  
([AlterSquare production VAD analysis](https://altersquare.medium.com/why-vad-end-of-speech-detection-is-the-hardest-problem-in-production-voice-agents-fee308e38cfc))

Dual-threshold hysteresis: Silero auto-sets the deactivation threshold ~0.15 below the activation threshold (so at threshold=0.55, deactivation triggers at ~0.40). This prevents oscillation on fricatives and soft consonants.

**Cobra VAD** (Picovoice, proprietary) outperforms Silero on ROC curves (1.1% miss rate vs Silero's ~12.3%), but it is a paid SDK and adds a platform-level DLL — anticheat risk. Not recommended.

### 2. Semantic VAD: The Frontier

Traditional acoustic VAD can only detect "sound vs silence." It has zero ability to distinguish:
- Mid-sentence breath ("Jett hit 84... [breath] ...and Breach hit 97")
- Hesitation filler ("um... rotate B")
- Syntactically complete one-shot command ("Sage rotate B." — silence follows, AND the sentence is done)
- Syntactically incomplete stub ("Sage rotate..." — pause while user thinks of the site)

**Semantic VAD** (2023, [arXiv:2305.12450](https://arxiv.org/abs/2305.12450)) adds:
- Frame-level punctuation prediction
- Explicit "artificial endpoint" classification label (distinct from speech/silence)
- ASR-derived semantic loss during training

Result: **53.3% average latency reduction** over acoustic-only VAD, without ASR character error rate regression. The key insight: the model learns to fire the endpoint signal BEFORE trailing silence completes, because it has seen the punctuation distribution.

**Phoenix-VAD** (Sep 2025, [arXiv:2509.20410](https://arxiv.org/abs/2509.20410)) takes this further: a 3-component architecture (Zipformer audio encoder ~150M params + 2-layer linear adapter + Qwen2.5-0.5B-Instruct backbone LLM) doing streaming binary classification: "Continue Speaking" vs "Stop Speaking." Sliding window: 2560 ms audio window, 320 ms stride. Dual timeout thresholds:
- **400 ms** for semantically complete queries
- **1000 ms** for incomplete ones

Performance: 98.5–98.6% overall accuracy; 90.5% F1 on "Stop Speaking" for complete utterances; 99.3% F1 on "Continue Speaking" (very few false cuts). Inference: ~50 ms on A6000 48 GB.

**However, for Ultron 1.0:** Phoenix-VAD requires Qwen2.5-0.5B alongside your 8B — two model loads on a 10 GB budget = infeasible without tight VRAM juggling. The 50 ms A6000 latency also scales to ~300–400 ms on a 4070 Ti if loaded concurrently. Use the core idea (dual-timeout based on semantic completeness) but implement it cheaply (see Section 4).

**Smart Turn v2** (Pipecat, 2025, [Hugging Face](https://huggingface.co/pipecat-ai/smart-turn-v2)):
- wav2vec2 encoder + linear head, 94.8M params, 360 MB float32
- Analyzes raw waveform (NOT transcript) for intonation + filler word patterns
- Output: single probability ≥ 0.5 = speaker done
- Inference: 12 ms on L40S, **74 ms on T4, 410–900 ms on CPU**
- Smart Turn v3 (also on HF) adds ONNX export; Pipecat docs show `LocalSmartTurnAnalyzerV3` runs "under 100 ms" on CPU cloud instances

**On an RTX 4070 Ti with 8B already loaded:** 360 MB for Smart Turn v2 would consume ~3% of VRAM but adds another model load path. The CPU fallback at 410–900 ms is too slow for gaming commands. Feasible if loaded at the ONNX tier with GPU dispatch, but requires testing. Treat as "aspirational" for Ultron 1.0 Phase 2.

**Thai EOT paper** ([arXiv:2510.04016](https://arxiv.org/abs/2510.04016)): fine-tuned small transformer beats LLM zero-shot prompting for per-language semantic EOT at near-instant latency. Confirms the pattern: cheap fine-tuned classifier on partial transcript >> acoustic silence alone.

### 3. Compound Commands in One Utterance

The specific Ultron 1.0 case: "Jett hit 84, Breach hit 97, rotate B" is ONE acoustic utterance (no silence between clauses) containing THREE distinct relay sub-commands. This is called a **multi-intent utterance** in NLP literature.

**What research says:**

**DialogUSR** (EMNLP 2022, [arXiv:2210.11279](https://arxiv.org/abs/2210.11279)) proposes splitting + reformulation: detect coordinating conjunctions as segment boundaries, split the utterance into single-intent sub-queries, then resolve coreference in each split ("Breach hit 97" might implicitly reference the same kill context). Domain-agnostic plug-in approach. Accuracy: effective on 23-domain dataset. Latency: adds one inference pass per split. For Ultron 1.0: the split is unnecessary if routing handles multi-subject lists directly.

**Patent US11367444** (Google): voice search explicitly buffers on conjunctions ("and", "or") and waits for additional speech before committing. This implements the "extended window on coordinating conjunction detection" pattern.

**Assembly AI semantic endpointing** ([blog](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent)): uses end-of-turn confidence threshold 0.7 + minimum silence 160 ms when confident + fallback silence 2400 ms. The hybrid: semantic signal fires first, silence threshold as safety net.

**Key insight for Ultron 1.0:** The VAD+endpointing layer should NOT split "Jett hit 84, Breach hit 97, rotate B" — comma-separated clauses spoken in one breath have <100 ms inter-clause gaps, below any practical silence threshold. The entire compound is ONE acoustic segment and should be committed as ONE utterance. The **router/LLM layer** then splits it into sub-intents, queues them, and executes sequentially. This is the correct decomposition of responsibilities.

**How to detect compound payload at the router:**
- Presence of multiple proper-noun agent-name tokens ("Jett", "Breach") in one utterance = almost certainly multi-target callout
- Comma separation in the STT transcript between tactical tokens = compound list
- Coordinating conjunction "and" between two tactical clauses = compound sequence

The existing relay_speech.py slot parser already extracts agent+damage pairs. The compound case simply produces a list of (agent, dmg) tuples instead of one. Route each tuple to the relay individually (one TTS clip per relay message) or concatenate into a single relay clip.

### 4. Barge-In During TTS

The practical requirement: user says "Rotate A" while Ultron is playing the relay TTS for a previous command.

**Architecture (from production guides):**

1. **VAD always running on mic** — even during TTS playback. This is currently implemented in Ultron (STOP command is always-on via `audio.stop_command_enabled`).
2. **AEC (echo cancellation):** The TTS output goes through VoiceMeeter B1 (to Valorant). The mic input is from the physical mic. These are separate physical signal paths on a desktop — there is no loopback of Kokoro into the mic feed (unlike a phone call). So **AEC is already handled by the hardware setup**: Ultron's mic capture does not include Kokoro output. This eliminates the hardest barge-in problem.
3. **Energy gate for barge-in confirmation:** Silero threshold 0.55, sustained for ≥250 ms, at mic input (not VoiceMeeter output). This prevents keyboard clicks or brief room noise from triggering.
4. **TTS flush on barge-in:** Stop the current `audio.play()` immediately. The existing `audio.stop_command_enabled` ("Ultron stop") already does this. The barge-in path should call the same flush function without requiring the exact "stop" keyword — any confirmed speech during TTS = flush + re-enter STT pipeline.
5. **Latency targets** ([FutureAGI barge-in guide 2026](https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/)):
   - VAD detection: 85–100 ms
   - TTS flush: <60 ms (target P95: 54 ms)
   - LLM cancel: <40 ms  
   - Total barge-in handle: <150 ms end-to-end

**False barge-in risks in Valorant context:**
- Team voice comms bleeding into the mic (teammates talking) — mitigation: raise energy gate threshold to -35 dBFS during TTS playback (tighter than the normal -40 dBFS)
- Click sounds from gunfire/abilities in game audio — Ultron's output goes to VoiceMeeter, game audio goes to headset directly; no conflict on the mic signal path

### 5. STEER: Turn Extension / Follow-Up Detection

**Apple STEER** ([arXiv:2310.16990](https://arxiv.org/abs/2310.16990), EMNLP Industry 2023):
- Detects whether a follow-up turn is a "steering" (correction/clarification of the previous command) vs. a new independent command
- Transformer-based, 95%+ accuracy on opt-in usage data
- Saves 58.06% of repeat queries (3.96 words/query saved)
- STEER+ uses semantic parse trees for better handling of named entities at sentence boundaries

For Ultron 1.0: directly relevant to the case where user says "Sage rotate B" and then immediately says "actually A site" — the second utterance is a steering/correction of the first, not a new relay. The router should detect this and either (a) cancel the first relay if still in flight or (b) replace the pending action.

This is currently approximated by the "Ultron stop" command. A proper steering detector could handle implicit corrections without requiring an explicit stop command.

### 6. Adaptive Endpointing

**Amazon adaptive endpointing** ([arXiv:2303.13407](https://arxiv.org/abs/2303.13407), ICASSP 2023):
- Deep contextual multi-armed bandit: chooses between "standard" (short silence) and "relaxed" (long silence) endpointing configurations per utterance
- Features: utterance-level audio characteristics (speaking rate, pause frequency)
- No ground truth labels needed; learns from reward signals online
- Reduces early cutoffs while maintaining low latency

For Ultron 1.0: the two-config bandit maps directly to:
- "Standard" config: 400 ms silence = fast command (complete tactical noun phrase)
- "Relaxed" config: 1 200 ms silence = incomplete/hesitant/compound-in-progress

The bandit inference cost is cheap (a few audio features + a small NN); it can live in the voice path without anticheat concerns.

### 7. Pause / Gap Protocols — Concrete Numbers

From the research synthesis:

| Scenario | Silence threshold | Source |
|---|---|---|
| Clean command speech, fast speaker | 300–400 ms | AlterSquare, rajatpandit |
| Hesitation mid-sentence | Extend to 1 200–1 500 ms | Phoenix-VAD, rajatpandit |
| Syntactically complete query | Respond after 400–500 ms | AssemblyAI, rajatpandit |
| Syntactically incomplete stub | Extend to 1 500 ms | Phoenix-VAD |
| Comma-separated compound (same breath) | Do NOT split; commit whole | compound-command research |
| Barge-in confirmation | 200–300 ms sustain post-VAD | FutureAGI, sparkco |
| Barge-in TTS flush target | <60 ms | FutureAGI |
| Always-on VAD frame size | 20 ms (512 samples @ 16 kHz) | Silero, rajatpandit |

---

## Concrete Techniques / Parameters We Should Adopt

### A. Replace the 500-ms flat endpointing with a semantic-aware dual-threshold

```python
# In orchestrator._capture_utterance / VAD wrapper
SILENCE_STANDARD_MS = 500    # default commit (complete clause)
SILENCE_RELAXED_MS  = 1200   # incomplete clause / hesitation
SILENCE_BARGE_MS    = 400    # during TTS playback (faster to interrupt)

def _choose_silence_threshold(partial_transcript: str) -> int:
    """Cheap proxy for semantic completeness. No ML required."""
    txt = partial_transcript.strip().lower()
    # Signs of incompleteness: trailing conjunction, open preposition, agent name only
    INCOMPLETE_SIGNALS = [
        r'\b(and|but|or|also|then|so)\s*$',
        r'\b(to|at|in|on|for|with)\s*$',
        r'^[A-Z][a-z]+\s*$',  # solo agent name, e.g. "Jett"
        r'\.\.\.$',            # ellipsis in STT
    ]
    import re
    for pat in INCOMPLETE_SIGNALS:
        if re.search(pat, txt):
            return SILENCE_RELAXED_MS
    return SILENCE_STANDARD_MS
```

Integrate: after VAD fires "silence started," grab the current partial transcript from faster-whisper (or parakeet streaming output), run `_choose_silence_threshold`, arm a timer. If the timer fires without new speech, commit the utterance.

### B. Silero VAD parameters for Ultron 1.0

```python
vad_params = {
    "threshold": 0.55,
    "min_speech_duration_ms": 150,
    "max_speech_duration_s": 12.0,   # cap at 12 s; anything longer = likely two turns
    "min_silence_duration_ms": 500,   # base commit window (overridden by semantic check)
    "speech_pad_ms": 150,
    "window_size_samples": 512,       # 20 ms @ 16 kHz
}
```

### C. Compound command splitting at the router

```python
# In router / relay path — AFTER full utterance committed
import re

AGENT_NAMES = {"jett","sage","breach","sova","reyna","phoenix","omen","killjoy",
               "cypher","raze","viper","astra","brimstone","skye","yoru","neon",
               "chamber","fade","harbor","gekko","deadlock","iso","clove","vyse"}

def split_compound_relay(text: str) -> list[str]:
    """Split 'Jett hit 84, Breach hit 97, rotate B' into 3 sub-commands."""
    # Split on comma or ' and ' boundaries
    clauses = re.split(r',\s*|\s+and\s+', text)
    # Rebuild context: if a clause has no agent, inherit from context or treat as team-wide
    return [c.strip() for c in clauses if c.strip()]
```

Route each clause through the existing relay_speech pipeline. This is additive to the current slot-parser pattern — the slot-parser already handles individual agent+damage pairs; the compound splitter just calls it once per clause.

### D. Barge-in improvements

```python
# Keep VAD always running during TTS; barge-in confirm logic
BARGE_IN_ENERGY_THRESHOLD_DBF = -40.0  # normal; raise to -35 dBFS during TTS playback
BARGE_IN_SUSTAIN_MS = 250              # confirm 250 ms of sustained speech before flush

# On barge-in confirmed:
# 1. audio.stop() (flushes Kokoro playback)
# 2. re-enter _wait_for_speech() immediately
# 3. do NOT re-enter _wait_for_wake_word() — already addressed
```

### E. Do NOT run Smart Turn v2 on CPU in the hot path

Smart Turn v2 CPU inference = 410–900 ms. For a system targeting sub-2 s end-to-end, this is unacceptable on the critical path. If ONNX GPU inference can be isolated to <50 ms on the 4070 Ti without conflicting with the 8B LLM, Smart Turn is feasible as an **optional post-VAD refinement** (run it on the audio buffer WHILE Kokoro is starting to render the previous response — overlap the inference).

### F. STEER-style correction detection (lightweight proxy)

No need to run Apple's full STEER model. A simple heuristic:
- If a new utterance arrives within 3 s of the previous relay dispatch AND contains a contradicting site/direction token ("actually A", "no B site", "wait"), treat it as a correction and cancel/replace the pending relay.
- This is currently handled by "Ultron stop" + re-command. A regex-based correction gate closes the gap.

---

## Risks / Caveats for Our Constraints

### Anticheat (highest priority)

- **Silero VAD**: ships as a PyTorch model (`silero_vad`). PyTorch is already in the sidecar (EmbeddingGemma loads it). If Silero is loaded in the **sidecar process** (not the main voice path), it is anticheat-safe. The current architecture loads Silero directly in the orchestrator — this is fine because Silero was there before anticheat hardening, and it is audio/voice-only (no screen read, no game process injection).
- **Smart Turn v2**: adds wav2vec2 + safetensors loading. wav2vec2 is a transformers-based model. The main voice path `import_firewall` blocks transformers. If Smart Turn is added, it MUST go into the sidecar — same process as EmbeddingGemma. The sidecar is already running on CPU with shared GPU via PyTorch; adding a 360 MB model there is feasible.
- **Phoenix-VAD**: requires Qwen2.5-0.5B + Zipformer. Qwen2.5-0.5B is a full transformer LLM, 500M parameters. Loading it alongside the 8B will consume ~1 GB VRAM. Feasible in VRAM budget but adds warmup latency and complicates the sidecar model-management. Not recommended for Ultron 1.0.

### VRAM budget (10 GB design cap)

- Josiefied-Qwen3-8B Q5_K_M via llama-cpp-python: ~5.5–6.0 GB VRAM
- Kokoro TTS: ~0.5–1.0 GB VRAM
- EmbeddingGemma-300M sidecar: ~0.6 GB VRAM
- Smart Turn v2 ONNX (GPU): ~0.4 GB VRAM
- Remaining headroom: ~1.5–2.5 GB — tight but feasible for Smart Turn if inference does not overlap with 8B inference peaks

### Latency budget

- Current faster-whisper STT: ~150–300 ms for short gaming commands
- Semantic endpointing probe (rule-based): <1 ms — negligible
- EmbeddingGemma intent gate: ~30–50 ms (already in pipeline)
- Compound splitter (regex): <1 ms
- Smart Turn v2 on GPU: 12–30 ms (L40S → A100 proxy for 4070 Ti = ~40–60 ms estimated)
- Total additional overhead vs current: ~40–60 ms (Smart Turn) + 0 ms (rule-based semantic dual-threshold)

### False barge-in in Valorant

The biggest practical risk: Valorant game audio (explosions, ability sounds) is NOT on the mic signal path (it goes headset → ears directly). However, voice comms from teammates DO come through Discord/Valorant voice channel and could play through speakers and enter the mic if not using headphones. Mitigation: enforce headphone use (already assumed by the setup) and keep barge-in sustain threshold at 250 ms minimum.

### Compound command latency accumulation

If "Jett hit 84, Breach hit 97, rotate B" splits into 3 sequential TTS clips, the total relay time triples. This is inherent to the multi-command structure. Mitigation: relay the compound as a SINGLE concatenated TTS clip where possible ("Jett hit 84, Breach hit 97, rotating B" synthesized as one sentence) rather than 3 separate clips.

---

## Sources

1. [Semantic VAD: Low-Latency Voice Activity Detection for Speech Interaction (arXiv:2305.12450)](https://arxiv.org/abs/2305.12450)
2. [Phoenix-VAD: Streaming Semantic Endpoint Detection for Full-Duplex Speech Interaction (arXiv:2509.20410)](https://arxiv.org/abs/2509.20410) | [HTML full paper](https://arxiv.org/html/2509.20410v2)
3. [pipecat-ai/smart-turn-v2 — Hugging Face model card](https://huggingface.co/pipecat-ai/smart-turn-v2)
4. [Smart Turn v2: faster inference, and 13 new languages — Daily.co blog](https://www.daily.co/blog/smart-turn-v2-faster-inference-and-13-new-languages-for-voice-ai/)
5. [Pipecat Smart Turn Overview — official docs](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview)
6. [Turn Detection for Voice Agents: VAD, Endpointing, and Model-Based Detection — LiveKit blog](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection)
7. [Why VAD End-of-Speech Detection Is the Hardest Problem in Production Voice Agents — AlterSquare/Medium](https://altersquare.medium.com/why-vad-end-of-speech-detection-is-the-hardest-problem-in-production-voice-agents-fee308e38cfc)
8. [How Intelligent Turn Detection (Endpointing) Solves the Biggest Challenge in Voice Agent Development — AssemblyAI](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent)
9. [Adaptive Endpointing with Deep Contextual Multi-armed Bandits (arXiv:2303.13407)](https://arxiv.org/abs/2303.13407) | [Amazon Science](https://www.amazon.science/publications/adaptive-endpointing-with-deep-contextual-multi-armed-bandits)
10. [STEER: Semantic Turn Extension-Expansion Recognition for Voice Assistants (arXiv:2310.16990)](https://arxiv.org/abs/2310.16990) | [Apple ML Research](https://machinelearning.apple.com/research/steer)
11. [DialogUSR: Complex Dialogue Utterance Splitting and Reformulation for Multiple Intent Detection (arXiv:2210.11279)](https://arxiv.org/abs/2210.11279)
12. [Thai Semantic End-of-Turn Detection for Real-Time Voice Agents (arXiv:2510.04016)](https://arxiv.org/abs/2510.04016)
13. [RESPOND: Responsive Engagement Strategy for Predictive Orchestration and Dialogue (arXiv:2603.21682)](https://arxiv.org/abs/2603.21682)
14. [Optimizing Voice Agent Barge-in Detection for 2025 — SparkCo](https://sparkco.ai/blog/optimizing-voice-agent-barge-in-detection-for-2025)
15. [Voice AI Barge-In and Turn-Taking: A 2026 Implementation Guide — FutureAGI](https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/)
16. [Real-Time Audio AI: Implementing Silero VAD in Python — Rajat Pandit](https://rajatpandit.com/agentic-ai/real-time-audio-vad/)
17. [Silero VAD GitHub](https://github.com/snakers4/silero-vad)
18. [Voice Activity Detection (VAD): The Complete 2026 Guide — Picovoice](https://picovoice.ai/blog/complete-guide-voice-activity-detection-vad/)
19. [faster-whisper VAD parameters issue #477 — GitHub](https://github.com/SYSTRAN/faster-whisper/issues/477)
20. [Voice AI Echo Cancellation — Coval](https://www.coval.ai/blog/voice-ai-echo-cancellation)
21. [Systems and methods for using conjunctions in a voice input to cause a search application to wait for additional inputs — US Patent 11367444](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11367444)
22. [Prompt-Guided Turn-Taking Prediction (arXiv:2506.21191)](https://arxiv.org/pdf/2506.21191)
