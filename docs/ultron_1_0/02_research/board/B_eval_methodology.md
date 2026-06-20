# Evaluating Voice-Assistant Intent/Routing Systems: Metrics, Corpus Construction, Threshold Calibration, E2E Test Harness, Regression Design, and Per-Stage Trace

## TL;DR Recommendation for Ultron 1.0

Build a **three-layer evaluation stack**:

1. **Labeled discriminator corpus** — 400–600 hand-curated utterances across four classes (`RELAY_TO_TEAM`, `PRIVATE_REPLY`, `IGNORE_DISCORD`, `IGNORE_STREAM`), stratified by ambiguity tier (easy / hard / adversarial), stored as JSONL. Seed with your MP3 battery + synthetic generation from the 8B in thinking mode. Label with 2-pass annotation (rules-first, then human triage for the abstain band).

2. **Threshold calibration protocol** — use a held-out calibration split (15% of corpus), compute Precision-Recall curve per class, pick operating point at max F1 or target-precision (RELAY false-positive is highest-cost). Apply temperature scaling (single scalar τ on logits) or Platt scaling on the EmbeddingGemma sidecar similarity scores. Track ECE and risk-coverage curve. Re-calibrate whenever the router architecture changes.

3. **Deterministic E2E harness** — extend the existing `InjectableCapture` / MP3 battery pattern: pre-render all test utterances to WAV via Kokoro or Piper, inject via a mock `sounddevice` callback fixture, capture the full routing decision + trace fields, assert class + snap + latency against a frozen golden JSONL. Gate on `pytest -m routing` in CI; block merge if routing accuracy drops below 95% or any RELAY false-positive appears in the "obvious non-relay" tier.

Per-stage trace: emit one JSONL line per pipeline stage using a shared `turn_id`; minimum fields: `turn_id`, `stage`, `t_ms` (elapsed since wake), `decision` / `label`, `confidence`, `latency_ms`.

---

## Findings

### 1. Intent Classification Metrics: What Is Standard in 2024–2026

The NLU field has converged on a small set of primary metrics for intent routing tasks ([Voiceflow Pathways, 2024](https://www.voiceflow.com/pathways/benchmarking-hybrid-llm-classification-systems); [IntentDetection LLM Age 2024](https://arxiv.org/html/2410.01627)):

- **Macro-F1** (harmonic mean of per-class precision and recall, averaged unweighted) — preferred over accuracy when class sizes are imbalanced, which they will be in Ultron (RELAY likely dominates during a Valorant session).
- **Weighted-F1** — used when class support matters; reported alongside Macro-F1 in multi-party datasets ([MIntRec2.0, MPGT, arxiv 2507.22289](https://arxiv.org/html/2507.22289v1)).
- **OOS Recall / F1-OOS** — critical for the IGNORE classes; Ultron's system must not relay Discord chatter. The multi-party paper (2025) reports 45% F1-OOS for a hard corpus (30-class in-scope + 38% OOS ratio), versus 91.7% in-scope accuracy — revealing the inherent tension.
- **AUPRC** (area under the precision-recall curve, [EMNLP 2024 OOS fine-tuning](https://arxiv.org/abs/2410.13649v1)) — preferred over AUROC for OOS detection with imbalanced test sets. The paper reports 1–4% AUPRC improvement from their reconstruction-loss regularization.
- **Risk-Coverage curve** ([TACL Abstention Survey](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566/Know-Your-Limits-A-Survey-of-Abstention-in-Large)) — plots abstention rate vs. error rate among accepted predictions. For Ultron's 8B undecided-band routing, this curve determines the threshold that sends utterances to the expensive LLM path vs. the cheap rules path.
- **ECE (Expected Calibration Error)** ([metrics-reloaded, DKFZ](https://metrics-reloaded.dkfz.de/metric-library/expected_calibration_error)) — measures whether confidence scores are numerically meaningful as probabilities. ECE < 0.05 is considered well-calibrated in production intent systems.

**Ultron-specific metric priority order:**
1. RELAY Precision (false positives relay team chatter from Discord/stream = worst failure mode)
2. RELAY Recall (false negatives = missed relays = lost utility)
3. IGNORE F1-OOS (IGNORE classes are Ultron's "abstain" behavior)
4. Macro-F1 overall
5. ECE of the sidecar similarity score (verifies calibration validity)

#### Hybrid LLM + NLU Classifier Benchmark Numbers

The Voiceflow Pathways benchmark (2024) tested a two-stage retrieval-augmented classifier (encoder retrieves top-10 candidate intents → LLM picks from them). Key results:
- Recall@10 from the encoder exceeded **95%** on standard benchmarks (CLINC150, Banking77, HWU64)
- Production dataset with 32 intents: encoder recall dropped to **93%** — a warning that internal corpora with compound or ambiguous intent labels behave worse than benchmarks
- Full-LLM baseline (Haiku) false-none rate: **27%** on HWU64 — catastrophic for Ultron if applied naively to relay routing
- Hybrid approach false-none rate: **< 3%**
- Token savings: **4.78x** on the production dataset, **15.62x** on HWU64 vs. full-LLM prompting

This directly motivates the Ultron 1.0 design: rules + EmbeddingGemma handle the easy band, 8B LLM handles only the undecided band.

#### LLM vs. Fine-Tuned Models (real-world data)

The "Intent Detection in the Age of LLMs" paper (EMNLP 2024 Industry, [arxiv 2410.01627](https://arxiv.org/html/2410.01627)) evaluated on real deployed task-oriented dialogue systems (not toy benchmarks):
- Claude v3 Haiku: **0.736 F1** across datasets
- SetFit + Negative Augmentation: **0.658 F1**, but **56x faster** (0.030ms vs. 2.345ms latency)
- Hybrid (embedding retrieval + LLM): within **~2% of LLM accuracy** at **~50% less latency**

Key insight: "label design matters" — broader label scope degrades OOS detection significantly. For Ultron, keeping the routing label space small (4 classes) is a conscious design choice that will improve OOS detection versus systems with dozens of intents.

---

### 2. Labeled Discriminator Corpus Construction

#### Methodology

The pipeline for building intent corpora from sparse data, per multiple 2024 sources:

**Step 1 — Seed collection.** Three sources:
- Existing MP3 battery (already ~950+ utterances, transcribed) — mine these for relay-positive examples
- Live session logs (`logs/kenning.log`, `logs/usage_trace.jsonl`) — mine for naturally occurring non-relay examples (Discord chatter, stream comments, teammate speech that fired wake word accidentally)
- Synthetic generation — prompt the 8B in thinking mode to generate 50 utterances per class given a few exemplars; keep only those the rules layer disagrees on (contention zone)

**Step 2 — Cluster and label.** Standard intent discovery pipeline per the MDPI 2024 paper ([Improving Intent Classification Using Unlabeled Data](https://www.mdpi.com/2227-7390/11/3/769)):
1. Embed all utterances (EmbeddingGemma sidecar already present)
2. Cluster (k-means or HDBSCAN, k = 4 for 4 classes)
3. Hand-label cluster centroids + outliers
4. Re-classify stragglers

**Step 3 — Stratify by ambiguity.** Three tiers:
- **Easy** (rules give high-confidence answer, >0.85): ~50% of corpus
- **Hard** (rules are ambiguous, confidence 0.40–0.85): ~35%
- **Adversarial** (intentionally designed edge cases: "tell the stream what happened" = PRIVATE, not RELAY; "let Discord know I'm back" = IGNORE): ~15%

Adversarial examples are the most valuable for threshold calibration — they define where the decision boundary must be.

**Step 4 — Inter-annotator agreement.** Even for a solo project, run two labeling passes with a gap of several days. Disagreements between your own passes define the "genuinely ambiguous" tier — these are the inputs that must go to the 8B LLM path, not be decided by rules.

**Step 5 — Frozen golden split.** 70% train/development, 15% calibration, 15% frozen test (never seen during any tuning). The frozen test set is the regression gate.

#### Class Definitions for Ultron 1.0

Precise class scope matters enormously for OOS detection accuracy ([Intent Detection LLM Age 2024](https://arxiv.org/html/2410.01627)). Proposed definitions:

| Class | Trigger | Example utterances | Notes |
|---|---|---|---|
| `RELAY_TO_TEAM` | Spoken to Ultron, content is tactical/social, should go to Valorant team voice | "Tell my team they're rotating B", "Jett hit 84", "Let them know we're going to A" | Always starts with or implies Ultron as relay agent |
| `PRIVATE_REPLY` | Spoken to Ultron, answer is for the user only (info request, config, meta) | "What's the score?", "Ultron stop", "Switch to GPU", "Show me the stop button" | No team relay; Ultron responds directly to user |
| `IGNORE_DISCORD` | Speech picked up from Discord/party members, not directed at Ultron | "Yeah I'll be on in a sec", "okay sure", "I'm landing Bind" | Background speech from teammates or Discord calls |
| `IGNORE_STREAM` | Speech picked up from stream output, TV, or other media | "...subscribe to the channel...", "our next ad break" | Sources without tactical intent |

Note: `IGNORE_DISCORD` and `IGNORE_STREAM` may be merged into `IGNORE` for the first corpus version if labeled examples are insufficient to distinguish them acoustically/textually.

---

### 3. Threshold Calibration

#### Temperature Scaling (Recommended for Sidecar Scores)

Temperature scaling ([arxiv 2604.07172, 2025](https://arxiv.org/html/2604.07172v1)) is the most practical post-hoc calibration method: a single scalar τ divides logits before softmax.

```
p_calibrated = softmax(logits / τ)
```

τ > 1 smooths (softens) overconfident outputs; τ < 1 sharpens underconfident ones. Optimized on calibration set by minimizing NLL. For EmbeddingGemma cosine similarity scores (already in [0,1]), treat them as pre-sigmoid logits: fit a Platt sigmoid `σ(w * sim + b)` with (w, b) on the calibration set.

**DETER framework result** ([EMNLP 2024](https://arxiv.org/html/2405.19967v2)): threshold T = 0.7 on softmax output, calibrated on validation set **without any OOS training examples**, achieved:
- CLINC-150 (25% OOS ratio): 92.19% in-scope F1, 98.42% OOS F1
- Banking77 (25% OOS): 87.45% in-scope F1, 97.86% OOS F1

DETER uses only 1.5M trainable parameters (vs. 125M in comparable baselines) — lightweight enough to run alongside llama.cpp in 10GB.

#### Abstention / Risk-Coverage Curve

For Ultron's undecided band, the operating threshold controls the **risk-coverage tradeoff** ([TACL survey](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566/Know-Your-Limits-A-Survey-of-Abstention-in-Large)):
- **Coverage** = fraction of utterances decided by the cheap path (rules/embedder)
- **Risk** = error rate on accepted predictions

Target: drive the cheap path to handle 80–85% of utterances (coverage ≥ 0.80) while keeping risk < 5% on the easy tier. Tune thresholds separately per class: the cost of a RELAY false-positive (team hears Discord chatter) vastly exceeds a RELAY false-negative (relay missed).

#### Calibration Protocol for Ultron

1. Run the calibration split (15%, ~75–90 utterances) through the full pipeline
2. Collect raw scores: RapidFuzz match confidence, EmbeddingGemma cosine similarity, 8B softmax probability
3. Fit Platt sigmoid per score type on calibration labels
4. Sweep the resulting calibrated thresholds; plot Precision-Recall per class
5. For RELAY: pick threshold that achieves **Precision ≥ 0.97** (tight), allow Recall to float
6. For IGNORE: pick threshold that achieves **Recall ≥ 0.90** (catch background chatter)
7. Report final ECE on calibration set; flag if ECE > 0.06
8. Lock thresholds into a config file versioned alongside the corpus

**Key warning from research**: "State-of-the-art models don't always outperform older models and performance is heavily dataset-dependent" ([Voiceflow 2024](https://www.voiceflow.com/pathways/benchmarking-hybrid-llm-classification-systems)). Re-calibrate any time: the 8B model changes, the EmbeddingGemma sidecar is updated, or the intent label space changes.

---

### 4. Deterministic MIC-Input Simulation for E2E Tests

#### Existing Asset: InjectableCapture

The codebase already contains `InjectableCapture` — a drop-in mic stream that accepts pre-loaded audio chunks. This is the correct injection point. The pattern is consistent with the industry approach:

From the Piper TTS testing blog ([binaryrepublik.com, 2025](https://blog.binaryrepublik.com/2025/07/test-your-ai-voice-assistant-with.html)): render test text to WAV, inject WAV frames via a stream, assert three outcomes: transcript, routing decision, executed action.

```python
# Conceptual pytest fixture pattern for Ultron
@pytest.fixture
def injectable_mic(tmp_path):
    """Drop InjectableCapture into the capture layer; push WAV frames."""
    cap = InjectableCapture()
    yield cap
    cap.close()

def test_relay_routing(injectable_mic, wav_factory):
    wav = wav_factory("Tell my team they're rotating B")   # Kokoro/Piper TTS
    injectable_mic.push_audio(wav)
    result = run_turn_pipeline(injectable_mic)
    assert result.routing_class == "RELAY_TO_TEAM"
    assert result.latency_ms < 2000
```

**Determinism requirement**: use Kokoro or Piper (local, no API) to render utterances. Fix the TTS voice model version and random seed so WAV outputs are byte-identical across CI runs. Store pre-rendered WAVs in `tests/fixtures/audio/` and git-LFS them (or derive from text at test time with a locked seed).

#### WAV Injection in sounddevice Callback Pattern

For deeper pipeline coverage (including VAD, wake word, STT), inject at the `sounddevice.InputStream` callback level:

```python
# Mock sounddevice stream that replays a WAV queue
class FakeStream:
    def __init__(self, callback, wav_queue):
        self._callback = callback
        self._wav_queue = wav_queue
    
    def start(self):
        for chunk in self._wav_queue:
            self._callback(chunk, len(chunk), {}, None)
```

Patch `sounddevice.InputStream` with `FakeStream` in test scope. This exercises the real VAD, real STT, and real routing — all from deterministic audio. The LiveKit testing guide ([hamming.ai, 2026](https://hamming.ai/resources/testing-livekit-voice-agents-complete-guide)) confirms this is the recommended pattern: "text-only pytest helpers for logic validation, though text tests miss WebRTC timing, jitter, and turn-taking behavior."

#### Silence / Noise Injection

Include silence frames (zero-padded WAV) and background noise (pink noise at -30dBFS) as fixtures. These test the VAD threshold, the capture-stall watchdog, and the wake-word false-positive rate. The existing silence detection tests in the codebase (`tests/test_silence_detection.py` pattern) already model this.

---

### 5. Regression Harness Design

#### Golden Dataset + Frozen Test Table Pattern

The codebase already uses this pattern (186-case frozen table, `tests/data/voice_lines_golden_digest.json`). Extend it to routing:

**File**: `tests/data/routing_golden.jsonl`

Each line:
```json
{
  "id": "R-001",
  "tier": "easy",
  "utterance_text": "Tell my team they're rotating B",
  "audio_fixture": "tests/fixtures/audio/relay_rotating_b.wav",
  "expected_class": "RELAY_TO_TEAM",
  "expected_snap": null,
  "expected_relay_text_contains": "rotating B",
  "notes": "explicit relay lead + tactical content"
}
```

**Size recommendation** ([testquality.com 2026](https://testquality.com/llm-regression-testing-pipeline/)): 100–300 cases for initial corpus; start at 150 covering all 4 classes + adversarial edge cases. Scale to 400–600 as live session logs surface new failure modes.

#### Blocking Criteria

From the regression testing literature ([testquality.com](https://testquality.com/llm-regression-testing-pipeline/); internal precedent from the codebase's `assert_firewall_enforces` pattern):

| Failure condition | Action |
|---|---|
| RELAY Precision < 0.97 on frozen test | Block merge |
| Any RELAY false-positive in "easy" tier | Block merge |
| RELAY Recall < 0.85 | Warning, manual review |
| IGNORE Recall < 0.90 | Block merge |
| Macro-F1 < 0.88 | Block merge |
| Any previously-passing test now fails | Block merge (regression) |
| E2E latency p95 > 3000ms on relay path | Warning |

Run the full routing suite (`pytest -m routing`) on every PR that touches: `relay_speech.py`, `orchestrator.py`, `_relay_intent.py`, `_common_words.py`, `addressing.py`, or any normalizer file.

#### Dynamic Maintenance

Per production practice ([testquality.com 2026](https://testquality.com/llm-regression-testing-pipeline/)): quarterly rotation of live session examples into the corpus. After each major stream or gaming session, review `logs/usage_trace.jsonl` for mis-routed utterances; add confirmed failure cases to the golden corpus within 24 hours (while context is fresh).

#### Precedent in This Codebase

The existing behavioral-diff regression pattern (per the 25k-corpus audit, tip `4a36d8e`) runs 24,996-input diffs against an oracle. For routing, a lighter version suffices: 150–600 inputs is enough if the easy tier is truly easy (deterministic rule coverage) and the adversarial tier is truly adversarial (exercises the 8B LLM path).

---

### 6. Per-Stage Trace Design

Based on the dograh.com voice observability article ([2024](https://blog.dograh.com/why-observability-matters-in-building-voice-agents-traces-evals-guide/)) and AgentTrace framework ([arxiv 2602.10133](https://arxiv.org/html/2602.10133)), plus the existing `logs/usage_trace.jsonl` format in the codebase.

#### Correlation Strategy

Every pipeline invocation gets a `turn_id` (UUID4 or monotonic counter) generated at wake-word detection. All log lines for that turn share this ID. This enables post-hoc joining of: wake event → STT → normalizer → intent gate → routing decision → relay render → TTS → PTT playback.

The codebase already writes `logs/kenning.log` with turn-flow entries. Extend to structured JSONL alongside the existing log.

#### Per-Stage Schema

**File**: `logs/usage_trace.jsonl` (already exists; extend field set)

Each line is one stage event:

```json
{
  "turn_id": "a3f2c1d0",
  "stage": "wake_detect",
  "t_ms": 0,
  "wake_score": 0.91,
  "pre_roll_ms": 50,
  "latency_ms": 12
}

{
  "turn_id": "a3f2c1d0",
  "stage": "stt",
  "t_ms": 45,
  "raw_transcript": "tell my team they're rotating b",
  "stt_confidence": 0.88,
  "stt_model": "parakeet-ctc-0.6b",
  "latency_ms": 310
}

{
  "turn_id": "a3f2c1d0",
  "stage": "normalize",
  "t_ms": 355,
  "normalized": "tell my team they're rotating B",
  "normalizer_edits": ["site_letter_upper"],
  "latency_ms": 2
}

{
  "turn_id": "a3f2c1d0",
  "stage": "intent_gate",
  "t_ms": 357,
  "addressing_score": 0.95,
  "addressing_decision": "addressed",
  "intent_path": "rules",
  "intent_class": "RELAY_TO_TEAM",
  "intent_confidence": 0.99,
  "latency_ms": 8
}

{
  "turn_id": "a3f2c1d0",
  "stage": "router",
  "t_ms": 365,
  "routing_decision": "relay",
  "snap_matched": null,
  "template_id": "relay_tactical_v2",
  "latency_ms": 1
}

{
  "turn_id": "a3f2c1d0",
  "stage": "llm",
  "t_ms": 366,
  "model": "josiefied-qwen3-8b-q5_k_m",
  "prompt_tokens": 312,
  "thinking_tokens": 87,
  "completion_tokens": 24,
  "output_text": "They're rotating B.",
  "latency_ms": 890
}

{
  "turn_id": "a3f2c1d0",
  "stage": "flavor_tail",
  "t_ms": 1256,
  "tail_enabled": true,
  "tail_text": "I see the shift.",
  "tail_agent": "Jett",
  "tail_situation": "rotation",
  "latency_ms": 3
}

{
  "turn_id": "a3f2c1d0",
  "stage": "tts",
  "t_ms": 1259,
  "tts_model": "kokoro",
  "audio_duration_ms": 1840,
  "latency_ms": 320
}

{
  "turn_id": "a3f2c1d0",
  "stage": "ptt",
  "t_ms": 1579,
  "ptt_enabled": true,
  "key_held_ms": 1900,
  "latency_ms": 20
}
```

#### Cascading Failure Detection

The dograh.com observability article specifically highlights the "invisible cascade" failure: packet loss → ASR degrades → misrouting → wrong output. The trace schema above exposes each link: if `stt_confidence` drops below 0.70 and `intent_class` is `RELAY_TO_TEAM`, that's a suspicious cascade worth flagging.

Add a `cascade_risk` flag computed at the `intent_gate` stage:
```json
"cascade_risk": "stt_low_confidence"  // or null
```

#### What NOT to Log (Anticheat Constraint)

Per BINDING RULES: no desktop stack imports in the relay path. The trace logger must use only `json` + `pathlib` + `time` from stdlib. Do not import psutil, win32api, or any monitoring library into the voice path. Write to JSONL via a background thread with a queue to avoid blocking the audio path.

#### Minimum Viable Trace for First Iteration

If implementing full schema is too much overhead initially, the minimum per-turn record is:

```json
{
  "turn_id": "a3f2c1d0",
  "ts_iso": "2026-06-20T03:14:15.926Z",
  "raw": "tell my team they're rotating b",
  "normalized": "tell my team they're rotating B",
  "intent_class": "RELAY_TO_TEAM",
  "intent_path": "rules",
  "routing": "relay",
  "relay_text": "They're rotating B.",
  "total_latency_ms": 1599,
  "stt_confidence": 0.88,
  "addressing_score": 0.95
}
```

This minimum set enables all post-hoc analysis: routing errors, latency regressions, confidence distribution shifts.

---

### 7. Multi-Party / Addressee Attribution

The multi-party conversation literature ([arxiv 2507.22289, 2025](https://arxiv.org/html/2507.22289v1)) addresses Ultron's exact problem: a mic capturing both user speech and teammates/Discord. Key techniques:

- **Uncertainty-based routing**: BERT (or EmbeddingGemma) computes σ (std dev of softmax); high-σ utterances route to LLM. For Ultron: utterances where the rules/embedder abstain route to the 8B.
- **σ thresholds from the paper**: 0.10 on MIntRec2.0, 0.12 on MPGT. These are post-softmax; recalibrate for EmbeddingGemma cosine similarity scores (different range).
- **Label space reduction**: P=0.85 cumulative-probability cutoff reduced label space ~80% with >90% hit rate. For Ultron (4 classes), this is trivially satisfied — always send all 4 to the LLM when it's consulted.
- **Result**: hybrid approach achieved **44% latency reduction** vs. LLM-only while maintaining competitive accuracy.

For Ultron's IGNORE classes specifically: the addressee/wake-word detection layer (already implemented via `addressing.py`, `zero_shot.py`, `rules.py`) IS the first discriminator. Utterances that score low on addressee confidence AND don't match the relay pattern are IGNORE. The routing corpus should include wake-word misfires (the "told you so" category: wake fired but utterance is background chatter) as adversarial IGNORE examples.

---

### 8. Out-of-Scope Detection Patterns for Ultron

OOS in Ultron 1.0 context = utterances that should be IGNORED but arrive in the pipeline because the wake word fired or PTT was pressed by mistake.

**DETER approach** ([EMNLP 2024](https://arxiv.org/html/2405.19967v2)):
- Threshold T = 0.7 on softmax output, calibrated on validation set, **no OOS training examples needed**
- Uses synthetic OOS: convex combinations of in-scope embeddings from different classes
- CLINC-150 OOS F1: 98.42% at 25% OOS ratio — very strong

**Applying to Ultron**: the relay/addressing confidence scores already provide a natural OOS signal. When both `relay_match_confidence` < 0.45 AND `addressing_score` < 0.50, the utterance is likely IGNORE. Calibrate T on the 15% calibration split using the DETER threshold-sweep approach.

**Class Name Guided approach** (EMNLP 2024 Findings): encode the class names themselves as prototypes, compute cosine similarity to the utterance embedding, threshold on minimum similarity. For Ultron: embed the strings "relay to team", "private reply to me", "ignore Discord chatter", "ignore stream audio" — these become natural language prototypes that generalize well to novel phrasings.

---

## Concrete Techniques / Params We Should Adopt

| Technique | Source | Concrete param | Ultron applicability |
|---|---|---|---|
| Macro-F1 + OOS Recall as primary metrics | Multiple 2024 sources | — | Primary eval metrics for routing corpus |
| AUPRC for OOS class evaluation | [EMNLP 2024, arxiv 2410.13649](https://arxiv.org/abs/2410.13649v1) | — | Track AUPRC for IGNORE classes specifically |
| Temperature scaling (Platt sigmoid) on sidecar cosine scores | [arxiv 2604.07172](https://arxiv.org/html/2604.07172v1) | Single scalar τ, fit on 15% cal split | Calibrate EmbeddingGemma similarity → probability |
| Confidence threshold T = 0.7 as OOS reject threshold (start point) | [DETER, arxiv 2405.19967](https://arxiv.org/html/2405.19967v2) | T ∈ [0, 1]; sweep on cal split | Apply to intent_confidence field; tune up/down |
| Uncertainty routing: σ of softmax | [Multi-party NLU, arxiv 2507.22289](https://arxiv.org/html/2507.22289v1) | σ thresholds 0.10–0.12 | Route to 8B when EmbeddingGemma σ > threshold |
| Label space reduction (P=0.85 cumulative) | [Multi-party NLU](https://arxiv.org/html/2507.22289v1) | P = 0.85 | Not needed for 4-class, but useful if classes expand |
| Golden corpus: 150–300 cases, 70/15/15 split | [testquality.com](https://testquality.com/llm-regression-testing-pipeline/) | 150 initial, 400–600 mature | `tests/data/routing_golden.jsonl` |
| Golden corpus 2-pass annotation with adversarial tier | Domain-standard | 15% adversarial | Hard examples that must reach the 8B path |
| WAV injection via mock InputStream callback | [binaryrepublik.com](https://blog.binaryrepublik.com/2025/07/test-your-ai-voice-assistant-with.html) | 3200-byte chunk streaming | Extend InjectableCapture; pre-render WAVs with Kokoro |
| Freeze test WAVs as fixtures in git-LFS | Production standard | — | `tests/fixtures/audio/` |
| CI blocking at 95% routing accuracy | [testquality.com](https://testquality.com/llm-regression-testing-pipeline/) | 95% threshold | `pytest -m routing`, block merge on regression |
| Per-turn JSONL trace with `turn_id` correlation | [dograh.com observability](https://blog.dograh.com/why-observability-matters-in-building-voice-agents-traces-evals-guide/) | Fields: turn_id, stage, t_ms, decision, confidence, latency_ms | Extend `logs/usage_trace.jsonl` |
| AgentTrace dual-path: JSONL + OpenTelemetry | [arxiv 2602.10133](https://arxiv.org/html/2602.10133) | JSONL for offline, OTel for live | JSONL only (OTel not needed for single-node local system) |
| Cascade risk flag in trace | [dograh.com](https://blog.dograh.com/why-observability-matters-in-building-voice-agents-traces-evals-guide/) | `cascade_risk` field | Set when stt_confidence < 0.70 and routed as relay |
| Rotate live session failures into corpus quarterly | [testquality.com](https://testquality.com/llm-regression-testing-pipeline/) | Monthly preferred; quarterly minimum | Mine `usage_trace.jsonl` after each stream |
| Class name embedding prototypes for OOS | EMNLP 2024 Findings | Cosine sim to class name strings | Bootstrap OOS detection without OOS training data |
| Synthetic OOS via convex embedding combinations | [DETER](https://arxiv.org/html/2405.19967v2) | h_oos = θ × h_β + (1-θ) × h_α | Generate pseudo-OOS for calibration without real data |

---

## Risks / Caveats for Our Constraints

### 1. Class Imbalance in Practice
During a live Valorant session, RELAY utterances may be 60–70% of all addressed utterances. This will distort Macro-F1 toward RELAY unless the corpus is deliberately balanced. Counter: stratify the corpus to have at least 30% IGNORE examples; use weighted sampling in calibration.

### 2. OOS Ratio Sensitivity
DETER's 98% OOS-F1 was at 25% OOS ratio. At 50%+ OOS (typical for Ultron: many false-wake events), performance degrades. Measure OOS-F1 at multiple OOS ratios (25%, 50%, 75%) on the frozen test set.

### 3. EmbeddingGemma Sidecar Calibration Mismatch
EmbeddingGemma produces cosine similarity scores, not softmax probabilities. The DETER T=0.7 threshold applies to softmax outputs — direct transplant is incorrect. Must apply Platt scaling to convert cosine similarity to calibrated probability before applying any threshold. Validate with ECE on the calibration split.

### 4. STT Variability in E2E Tests
Faster-whisper transcription is not deterministic across runs (temperature, beam search). For E2E routing tests, bypass STT by injecting normalized text directly into the post-STT pipeline stage, OR fix random seed + disable beam search variation. WAV injection only helps if STT is also deterministic or mocked.

### 5. anticheat Constraint on Trace Logger
The trace JSONL writer must not import anything beyond `json`, `pathlib`, `threading`, `queue`, `time`. No psutil, no OpenTelemetry export, no network calls. Write to local JSONL only. This is less observable in production but is the only safe option given the gaming anticheat environment.

### 6. 4-Class Design Stability
If the label space later expands (e.g., adding `RELAY_TO_GAME` for keybind triggers), re-calibration is mandatory. The "label design matters" finding from the EMNLP 2024 paper applies: broader scope = worse OOS detection. Keep the class space small and stable before scaling.

### 7. Hybrid LLM Path Latency Budget
The multi-party study reports 44% latency reduction by routing only uncertain examples to LLM. For Ultron, the 8B LLM is in-process (llama-cpp-python 0.3.22); a full inference pass is 600–1200ms on GPU. Budget this into the threshold design: if the undecided band is 20% of utterances and each costs 900ms, average latency impact is 180ms — acceptable. If the band is 50%, average impact is 450ms — unacceptable. Target: keep undecided band < 20% by investing in the rules/embedder layer.

### 8. WAV Fixture Storage
Pre-rendered WAVs at 16kHz mono (Kokoro output format) are ~160KB per second. 150 test utterances averaging 3 seconds = ~72MB. Use git-LFS or generate at test time with a fixed TTS seed; document which is used.

### 9. Golden Corpus Staleness
Per testquality.com: gold sets must be maintained; stale baselines become disconnected from production. Set a calendar reminder to review the corpus after every 3 major stream sessions or whenever the routing architecture changes.

---

## Sources

- [Voiceflow Pathways — Benchmarking Hybrid LLM Classification Systems (2024)](https://www.voiceflow.com/pathways/benchmarking-hybrid-llm-classification-systems)
- [Intent Detection in the Age of LLMs — EMNLP 2024 Industry Track, arxiv 2410.01627](https://arxiv.org/html/2410.01627)
- [Intent Recognition and OOS Detection in Multi-Party Conversations — arxiv 2507.22289 (2025)](https://arxiv.org/html/2507.22289v1)
- [Improved Out-of-Scope Intent Classification with Dual Encoding and Threshold-based Re-Classification (DETER) — arxiv 2405.19967 (2024)](https://arxiv.org/html/2405.19967v2)
- [Fine-tuning Sentence Transformers for Intent Classification and OOS Detection — EMNLP 2025, arxiv 2410.13649](https://arxiv.org/abs/2410.13649v1)
- [Temperature Scaling Improves Semantic Uncertainty Quantification — arxiv 2604.07172 (2025)](https://arxiv.org/html/2604.07172v1)
- [Know Your Limits: A Survey of Abstention in Large Language Models — TACL 2024](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00754/131566/Know-Your-Limits-A-Survey-of-Abstention-in-Large)
- [AgentTrace: A Structured Logging Framework for Agent System Observability — arxiv 2602.10133 (2025)](https://arxiv.org/html/2602.10133)
- [Voice Agent Observability: Traces + Evals Guide — dograh.com (2024)](https://blog.dograh.com/why-observability-matters-in-building-voice-agents-traces-evals-guide/)
- [Voice Observability: The Missing Discipline in Conversational AI — Hamming AI Blog](https://hamming.ai/blog/voice-agent-observability-voice-observability)
- [Testing LiveKit Voice Agents: Unit, Scenario, Load & Production Guide (2026) — Hamming AI](https://hamming.ai/resources/testing-livekit-voice-agents-complete-guide)
- [Test Your AI Voice Assistant with Realistic TTS Using Piper — binaryrepublik.com (2025)](https://blog.binaryrepublik.com/2025/07/test-your-ai-voice-assistant-with.html)
- [LLM Regression Testing Pipeline — testquality.com (2026)](https://testquality.com/llm-regression-testing-pipeline/)
- [Improving Intent Classification Using Unlabeled Data from Large Corpora — MDPI Mathematics 2023](https://www.mdpi.com/2227-7390/11/3/769)
- [Expected Calibration Error (ECE) — metrics-reloaded DKFZ](https://metrics-reloaded.dkfz.de/metric-library/expected_calibration_error)
- [Calibration in Deep Learning: A Survey of the State-of-the-Art — arxiv 2308.01222 (2023)](https://arxiv.org/pdf/2308.01222)
- [A Multimodal Approach to Device-Directed Speech Detection with LLMs — arxiv 2403.14438 (2024)](https://arxiv.org/pdf/2403.14438)
- [SELMA: A Speech-Enabled Language Model for Virtual Assistant Interactions — arxiv 2501.19377 (2025)](https://arxiv.org/pdf/2501.19377)
- [How to Evaluate Voice Assistant Pipelines From End to End — TELUS Digital](https://www.telusdigital.com/insights/data-and-ai/article/how-to-evaluate-voice-assistant-pipelines)
- [Observability in LLM Workflows: Metrics, Traces & Logs — TrueFoundry](https://www.truefoundry.com/blog/observability-in-llm-workflows)
