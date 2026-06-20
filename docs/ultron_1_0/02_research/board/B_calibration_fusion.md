# Confidence Calibration + Cost-Asymmetric Thresholding for Ultron 1.0's 3-Way Intent Gate

**Research board: B — Calibration & Fusion**
**Date: 2026-06-20 | Model: Claude Sonnet 4.6**

---

## TL;DR Recommendation for Ultron 1.0

**Use Platt scaling (2-parameter logistic fit on a held-out log set) as the post-hoc calibrator for every signal, then fuse all signals in log-odds space using a logistic meta-learner trained on labeled logs. Pick a cost-asymmetric threshold τ* computed from the cost ratio of false-relay vs. missed-relay, not from ROC Youden-J. Bootstrap the fusion weights from rule + embedding signals only (80–200 labeled examples suffices for Platt with 2 params); add the LLM first-token P(YES) column later when the LLM is in-loop.**

The 3-way gate is: `RELAY_TO_TEAM` | `PRIVATE_REPLY` | `IGNORE`. In practice the system already collapses this into binary cascades: an addressing gate decides ADDRESSED vs. NOT_ADDRESSED, and a relay-intent gate decides RELAY vs. CONVERSATIONAL. Both should be independently calibrated and independently thresholded, then composed — not collapsed into a single 3-way softmax. Composite labels from a 3-way logistic can hurt calibration on severely imbalanced classes (IGNORE is ~60%+ of live utterances).

**Concrete τ* formula for relay gate:**
```
τ* = C_FP / (C_FP + C_FN)
```
where `C_FP` = cost of a false relay (broadcasts garbage to teammates; annoying, trust-destroying; call it 3) and `C_FN` = cost of a missed relay (user has to re-say; minor; call it 1). This yields τ* = 0.75. Compare to the existing `threshold = 0.06` cosine-margin gate, which is a raw distance with no probabilistic meaning; calibrated Platt output should operate at τ ≈ 0.70–0.80.

---

## Findings

### 1. Why Calibration Matters in This System

The existing `RelayIntentGate.decide()` uses `(pos_sim - neg_sim) >= 0.06` — a cosine margin over exemplar clouds, not a probability. The `AddressingClassifier` fuses rule confidence (explicit values like 0.8, 0.95) with Flan-T5-small's P(YES) (a first-token logit softmax), taking `max(zs_conf, rule_hit.confidence)` when they agree. **These scores are on incompatible scales and are not calibrated probabilities.** A 0.8 from a regex rule and a 0.8 from Flan-T5 do not represent the same probability of being correct. Combining them with `max()` is ad hoc; a log-odds combiner with learned weights would be strictly principled.

Calibration research (NAACL 2024 survey on LLM confidence; arxiv 2410.10414 on guard model calibration) consistently finds that:
- Raw classifier outputs (including LLM first-token logits) are **overconfident** in RLHF-tuned models and **underconfident** in smaller classifiers.
- Flan-T5-small (used as zero-shot gate here) is a fine-tuned encoder with no RLHF but has well-documented output miscalibration on OOD text (gaming domain ≠ NLI training distribution).
- The ECE (Expected Calibration Error) for uncalibrated small models on OOD text is typically 15–30%.

### 2. Calibration Method Hierarchy: Which to Use

Three post-hoc methods dominate the literature:

#### Temperature Scaling (1 parameter)
- Divides logits by scalar T > 0 before softmax. Best for **decoder LLMs** where you extract first-token logit. T > 1 softens overconfident outputs; T < 1 sharpens underconfident ones.
- Fit T on a validation set by minimizing NLL (single-param optimization, fast).
- 2024 result (arxiv:2409.19817, Adaptive Temperature Scaling): ATS achieves 10–50% ECE reduction over vanilla temperature scaling on RLHF models by predicting per-token T from hidden features. Not needed for a single-class gate, but the vanilla single-T approach is the right choice for the Qwen 8B first-token P(YES|NO) extraction.
- **Verdict: use for LLM first-token logit only.**

#### Platt Scaling (2 parameters: A, B)
- Fits `p = σ(A·s + B)` on held-out labeled data via MLE (logistic regression with 1 feature = the raw score).
- Sklearn: `CalibratedClassifierCV(model, method='sigmoid', cv='prefit')` on a validation split.
- **Optimal for small calibration sets** (80–300 examples): 2 parameters, low variance.
- Li & Sur (arxiv:2502.15131, 2025): Platt scaling is provably Bregman-optimal (minimum divergence to true label distribution) under Gaussian-like feature distributions with large enough holdout. Converges at n_ho ≈ 2,000; at n_ho = 100 it's noisier but still better than uncalibrated.
- **Verdict: use for EmbeddingGemma cosine scores and rule confidence values. This is the primary calibration tool for the intent gate during the bootstrapping phase (< 500 logs).**

#### Isotonic Regression (non-parametric)
- Learns a piecewise monotone mapping. No shape assumption.
- Outperforms Platt on ECE/Brier with statistical significance when calibration set > 1,000 examples (KDNuggets calibration survey, 2024; sklearn docs).
- **Overfits below ~500 examples** — strictly worse than Platt in small-data regime.
- **Verdict: deferred. Revisit when > 1,000 labeled turns exist in the observation log.**

### 3. Expected Calibration Error (ECE) — Measurement in Our Context

ECE bins predictions by confidence, measures |mean_confidence - empirical_accuracy| per bin, averages. Standard library: sklearn's `calibration_error` or `calibration_curve`.

**Key caveats for Ultron 1.0:**
- **Class imbalance invalidates standard ECE.** If IGNORE is 60% of utterances, per-class-weighted ECE (`CECE` or `wsECE`) is needed. The majority-class will dominate bin-level accuracy, making RELAY look well-calibrated even when it's not. Compute ECE separately per class.
- **Small observation counts inflate ECE variance.** With < 200 labeled examples, use Brier score (strictly proper scoring rule, no binning) instead of ECE for calibration quality.
- **Reliability diagrams** (calibration curve plots) are the right visual diagnostic. Plot for each decision class separately.

### 4. Optimal Threshold — Cost-Asymmetric Formula

The key insight from the calibration + threshold literature (Journal of Operations Management 2026; arxiv:2409.19751, 2024 9,000-experiment study):

> **Decision Threshold Calibration (post-training threshold shift) was the best intervention in 40% of datasets and all three methods (SMOTE, class weights, threshold shift) beat the default 0.5 baseline by statistically significant margins. Threshold calibration won on 10 of 15 models tested.**

The Bayes-optimal threshold for calibrated posteriors is:

```
τ* = C_FP / (C_FP + C_FN)
```

This is derived from the minimum expected cost decision rule:
```
decide RELAY if P(relay|x) > τ*
```
where `τ*` is set so that the marginal misclassification costs are equal at the boundary.

**For our relay gate:**
- `C_FP` = cost of relaying non-relay speech (false alarm). Quantify: ruins immersion, confuses teammates, trust in Ultron degrades. Subjective: **3 units**.
- `C_FN` = cost of missing a relay (user re-says it with "tell my team"). Mild inconvenience: **1 unit**.
- `τ* = 3 / (3 + 1) = 0.75`.

**For the addressing gate (ADDRESSED vs. NOT_ADDRESSED):**
- `C_FP` = responding to stray speech (false accept). During gaming this is annoying, may broadcast noise. **2 units**.
- `C_FN` = not responding when addressed (false reject). User has to say "Ultron" again. **1 unit**.
- `τ* = 2 / (2 + 1) = 0.67`.

When operating under severe class imbalance, thresholds near the minority class's base rate outperform 0.5. RELAY is ~10–15% of live utterances; the optimal threshold naturally migrates toward 0.75–0.85 region under asymmetric cost + imbalance.

**Note on Youden-J / ROC-optimal threshold:** Youden-J maximizes `TPR - FPR` (F1-balanced), which is appropriate for balanced costs. When costs are asymmetric — our case — it's **wrong**: it underweights the 3x FP penalty. Always use cost-ratio threshold for this application. Literature confirms this (Valeman 2024 Medium article on ROC threshold pitfalls).

### 5. Log-Odds Fusion: Combining Heterogeneous Signals

The right way to combine rules + embeddings + LLM into a single calibrated gate is **logistic regression in log-odds space** (LLR fusion). This has strong theoretical grounding in speaker verification (NIST SRE), detection theory, and NLP classification:

**Mathematical basis:**
Each signal `s_i` (after per-signal Platt calibration) is a calibrated probability `p_i`. Convert to log-odds:
```
λ_i = log(p_i / (1 - p_i))  # log-odds = logit(p_i)
```

The fusion logistic regression models:
```
logit(P(RELAY | s_1, ..., s_k)) = w_0 + w_1·λ_1 + w_2·λ_2 + ... + w_k·λ_k
```

This is exactly `LogisticRegression` with features = `[logit(p_1), ..., logit(p_k)]` and target = binary relay label. The learned weights `w_i` encode each signal's reliability on Ultron's specific utterance distribution.

**Key properties:**
- When signals are independent conditionally on the label (or nearly so), log-odds fusion is the exact Bayes-optimal combiner (product of likelihood ratios in log space = sum of log-LRs).
- Rules and embedding similarity are not independent, but the logistic regressor learns to weight correlated signals appropriately via the shared intercept.
- The bias term `w_0` absorbs the class prior adjustment, so you don't need to re-weight for imbalance separately.
- A logistic regressor trained on 100–300 examples with k=3–5 features has extremely low variance (< k+1 = 6 effective parameters). L2 regularization (`C=1.0` or weaker) handles near-collinear signals.

**What the existing system does vs. what it should do:**

Current: `confidence = max(zs_conf, rule_hit.confidence)` — takes the higher value, discards the weaker signal. This is strictly suboptimal when the two signals carry orthogonal information (and they do: rules catch lexical patterns, embeddings catch semantic meaning, LLM catches context-sensitivity).

Target: `logit(P) = w_0 + w_rule·logit(rule_conf) + w_emb·logit(emb_score) + w_llm·logit(llm_p_yes)`, then `P = sigmoid(logit(P))` and threshold at τ*.

**Fallback for missing signals:** If a signal is unavailable (sidecar down, LLM not yet in-loop), set its log-odds contribution to 0 (equivalent to p=0.5, "no information"). This is the correct Bayesian fallback and preserves the other signals' contributions.

### 6. Severe Class Imbalance: IGNORE is the Majority

In the always-listening mode, the empirical class distribution is approximately:
- IGNORE (ambient, other-directed): ~60–70%
- PRIVATE_REPLY (addressed to Ultron): ~20–30%
- RELAY_TO_TEAM: ~5–15%

The SAS paper (arxiv:2604.08412, 2026) studying device-directed speech detection found similar imbalance (~8% device-directed, 58% person-directed, 34% silent) and recommends:
1. **Do not use SMOTE for calibration** (it worsens Brier score and probability calibration while boosting raw F1).
2. **Threshold calibration beats resampling** — directly adjust τ rather than resampling training data, as it preserves calibration quality.
3. **Fail-closed design**: below τ, abstain/IGNORE rather than routing to a default. This prevents expensive downstream LLM invocation on false triggers.
4. **Curriculum learning** (simple cases first) for training the fusion weights when using active learning to label logs.

The 9,000-experiment study (arxiv:2409.19751) confirms: threshold calibration achieved best F1 on 40% of imbalanced datasets; SMOTE won 30%, but at the expense of miscalibrated probabilities.

### 7. EER (Equal Error Rate) and Operating Point Selection

EER is the threshold where FAR = FRR (false accept rate = false reject rate). In our binary relay/no-relay gate:
- False Accept Rate (FAR): P(RELAY predicted | true = NOT_RELAY)
- False Reject Rate (FRR): P(NOT_RELAY predicted | true = RELAY)

EER is a single-number performance metric, not an operating threshold for production. It's useful for comparing gate architectures (lower EER = better gate), but the production threshold should be the cost-asymmetric τ* above, not the EER point.

The SAS paper evaluated at τ=0.70 (balanced, F1=0.86) and τ=0.82 (high-noise environment). This matches the cost-asymmetric derivation: C_FP/C_FN ≈ 3 → τ=0.75, with live-tuning from 0.70–0.82 based on environment.

**Recommendation:** Measure EER over the observation log every N sessions to track gate quality drift. Production threshold stays at τ* = 0.75 unless costs change.

### 8. LLM First-Token Probability Extraction (Qwen 8B via llama-cpp-python)

In Ultron 1.0, the 8B LLM (Josiefied-Qwen3-8B) is in-process via llama-cpp-python 0.3.22. To extract first-token probability for intent classification:

```python
# llama-cpp-python 0.3.x: use logit_bias + logprobs to get P(YES)/P(NO)
# Request completion with max_tokens=1, logprobs=True
result = llm.create_completion(
    prompt=prompt,
    max_tokens=1,
    logprobs=True,
    temperature=1.0  # raw logits, calibrate post-hoc
)
# Extract top-token logprobs
top_logprobs = result['choices'][0]['logprobs']['top_logprobs'][0]
p_yes = softmax_over(['Yes', 'No', ' Yes', ' No'], top_logprobs)
```

Then apply **temperature scaling** (a single learned T, fit on labeled logs):
```python
p_yes_cal = sigmoid(logit(p_yes) / T)  # T > 1 dampens overconfidence
```

**Cost:** ~50–150 ms additional latency per gate call. Reserve for the undecided band only (rule score and embedding score both in [0.4, 0.6] logit range).

### 9. Minimal Bootstrap Recipe (< 300 Labeled Examples)

The active Ultron session logs `logs/kenning.log` and (if enabled) `logs/usage_trace.jsonl`. Label 200–300 rows with `{relay, private_reply, ignore}`. This is sufficient to:

1. **Fit per-signal Platt calibrators:**
   - Rule confidence → `CalibratedClassifierCV(method='sigmoid', cv='prefit')` on the rule confidence scalar.
   - Embedding margin (pos_sim - neg_sim) → same.
   - LLM P(YES) → temperature scaling (grid search T ∈ [0.5, 3.0]).

2. **Fit the log-odds fusion logistic regressor:**
   ```python
   from sklearn.linear_model import LogisticRegression
   import numpy as np

   # X: (N, k) matrix of logit-transformed calibrated probabilities
   # y: binary relay label
   X = np.column_stack([logit(rule_cal), logit(emb_cal), logit(llm_cal)])
   clf = LogisticRegression(C=1.0, class_weight={0: 1.0, 1: 3.0}, max_iter=1000)
   # class_weight encodes cost: relay class weighted by C_FP=3
   clf.fit(X, y)
   ```
   Note: set `class_weight` during fusion LR training to encode cost asymmetry *in addition to* using τ*. This is doubly protective — `class_weight` shifts the decision boundary during training, `τ*` shifts it at inference.

3. **Evaluate on hold-out with Brier score** (not ECE, too noisy at < 300 samples):
   ```python
   from sklearn.metrics import brier_score_loss
   brier = brier_score_loss(y_test, p_relay_test)
   ```

4. **Store the fitted calibrators + weights** as a small JSON/pickle artifact (< 1 KB for Platt params + LR coefficients). Load at orchestrator boot alongside the sidecar.

### 10. Online Update: Growing the Calibrators with Labeled Logs

The observation log (`kenning.observations` / `usage_trace.jsonl`) accumulates per-turn evidence including `decision`, `confidence`, and `source`. A nightly or end-of-session refit job:
1. Load all logged turns, deduplicate by utterance hash.
2. Label those with high-confidence single-source verdicts as auto-labeled (`rule_conf > 0.95` → conservative auto-label; everything else needs human review or LLM-relabeling).
3. Refit Platt calibrators + fusion LR on the full labeled set.
4. When labeled set > 1,000: switch EmbeddingGemma from Platt to isotonic regression.
5. Monitor EER session-over-session; flag if it rises > 2% (possible distribution shift from new game patch).

This is effectively **online logistic regression with periodic batch refit** — low engineering cost, principled, and directly applicable to the streaming + few-labels constraint.

---

## Concrete Techniques / Params We Should Adopt

| What | Technique | Params | When |
|------|-----------|--------|------|
| Rule confidence calibration | Platt scaling | `method='sigmoid', cv='prefit'` | Boot, fit on 100+ labeled logs |
| Embedding margin calibration | Platt scaling | Same | Same |
| LLM P(YES) calibration | Temperature scaling | Grid T ∈ [0.5, 3.0], fit NLL | When LLM is in-loop for gate |
| Signal fusion | Log-odds logistic regression | `C=1.0, class_weight={0:1, 1:3}` | With calibrated inputs |
| Production threshold | Cost-asymmetric τ* | τ=0.75 (relay gate), τ=0.67 (addr. gate) | Replace raw margin thresholds |
| Calibration metric | Per-class Brier score | (use sklearn) | Track per session |
| Visual diagnostic | Reliability diagram | `calibration_curve` from sklearn | After each refit |
| Isotonic upgrade | Isotonic regression | `method='isotonic'` | When > 1,000 labeled |
| Environment-tuned threshold | Live τ sweep | τ ∈ [0.65, 0.85] if EER rises | High-noise environment |
| Fail-closed behavior | Below τ → IGNORE | (already in orchestrator) | Keep as-is |

**Threshold formula for deployment (relay gate):**
```
τ* = C_FP / (C_FP + C_FN)  →  default 0.75 for C_FP=3, C_FN=1
```

**Fusion forward pass (Python pseudocode):**
```python
def gate_relay(utterance: str) -> tuple[bool, float]:
    # Layer 1: rules
    rule_p = rule_platt.predict_proba([[rule_score(utterance)]])[0, 1]

    # Layer 2: EmbeddingGemma margin
    margin = embedding_margin(utterance)           # pos_sim - neg_sim
    emb_p = emb_platt.predict_proba([[margin]])[0, 1]

    # Layer 3: LLM first-token (only in undecided band)
    logit_rule = logit(rule_p)
    logit_emb  = logit(emb_p)
    if abs(logit_rule) < 3 and abs(logit_emb) < 3:  # undecided
        llm_raw_p = qwen_first_token_p_yes(utterance)
        llm_p = sigmoid(logit(llm_raw_p) / T_llm)    # temperature-scaled
        logit_llm = logit(llm_p)
    else:
        logit_llm = 0.0  # no LLM, contribute nothing

    X = [[logit_rule, logit_emb, logit_llm]]
    p_relay = fusion_lr.predict_proba(X)[0, 1]
    return p_relay >= TAU_RELAY, p_relay
```

**The `|logit| < 3` band check** means the LLM is consulted only when calibrated P is in [0.047, 0.953]. For clear-cut rule hits (regex → conf 0.95 → logit ≈ 2.9) or strong embedding signals (margin 0.4+ → calibrated P > 0.95), the LLM is not invoked.

---

## Risks / Caveats for Our Constraints

### Anticheat Safety
- All calibration artifacts (Platt `A, B` params; fusion LR weights; temperature T) are numpy scalars or small arrays. No ML heavy import needed in the relay/addressing path: numpy + scipy (already allowed) suffice for `sigmoid`, `logit`, and dot product. This is **safe to deploy in the relay path**.
- The LLM invocation for the undecided band adds latency. Per existing anticheat constraints, the 8B LLM is in-process (llama-cpp-python, not an external API), so no network calls are introduced.
- EmbeddingGemma sidecar is already anticheat-safe (urllib-only communication from main process).

### Small Calibration Set Risk
- Platt scaling at n=50 is noisy. Below 80 examples per signal, the A and B parameters have high standard error. **Minimum recommended: 100 labeled examples per gate (relay gate separately from addressing gate).** At < 80, use fixed τ from cost-ratio formula and uncalibrated rule/embedding scores with the existing thresholds; do not apply a Platt fit.
- Isotonic regression must not be used until > 500 labeled examples per class (RELAY and NOT_RELAY), per literature consensus.

### Distribution Shift (Game Patches / Meta)
- Valorant meta changes (new agents, new maps, new callout vocabulary) shift the utterance distribution. The embedding exemplar clouds may drift. **Re-label and refit calibrators after each major patch.** EER monitoring (session-level) is the early-warning signal.

### 3-Way vs. Binary Decomposition
- Fitting a single 3-way softmax logistic regressor (RELAY / PRIVATE / IGNORE) requires balanced representation of all three classes in the training set. Since RELAY is rare (5–15%), a 200-sample calibration set may contain only 10–30 relay examples — too few for 3-way reliable calibration. **Binary cascade is safer at small data scales.**
- Decompose into: (1) addressing gate (ADDRESSED vs. NOT) → (2) relay intent gate (RELAY vs. PRIVATE). Each gate calibrated and thresholded independently.

### LLM Logit Extraction in llama-cpp-python 0.3.22
- The `logprobs=True` API is available in llama-cpp-python >= 0.2.x but behavior differs by backend (Metal vs. CUDA vs. CPU). On RTX 4070 Ti (CUDA), extraction of top-k logprobs is supported. **Test that `result['choices'][0]['logprobs']` is non-null before deploying the LLM gate column.**
- Qwen3 with thinking enabled (`/think` token) produces thinking tokens before the answer. For first-token extraction of YES/NO, the prompt must constrain the answer format or extract from the LAST token before `</think>` — not the first. Use `thinking=False` mode (or explicit prompt instruction to answer YES/NO immediately) for the gate path.

### Calibration Collapse (GPT/LLM Artifact)
- The Nyckel calibration study found that GPT self-assessed confidence can "collapse" — become uniformly uninformative — when underlying model accuracy shows no confidence correlation for a particular class. If Qwen 8B's P(YES|intent) shows no correlation with actual precision on the relay class, temperature scaling cannot fix it. **Monitor P(YES) vs. actual relay accuracy on labeled logs; if AUC < 0.55, drop the LLM column from the fusion and rely on rules + embeddings.**

### Platt Scaling Assumes Sigmoid-Shaped Distortion
- If the raw rule confidence or embedding margin has a non-sigmoid calibration distortion (multi-modal distribution), Platt scaling will not correct it. Check with reliability diagrams first. If the calibration curve has a kink or S-shape reversal, isotonic regression is needed — but requires > 500 samples.

---

## Sources

1. **NAACL 2024 Survey on LLM Confidence Estimation and Calibration**
   https://aclanthology.org/2024.naacl-long.366.pdf

2. **Adaptive Temperature Scaling (ATS) for LLM Calibration** (arxiv:2409.19817, 2024)
   https://arxiv.org/abs/2409.19817

3. **Optimal and Provable Calibration: Angular Calibration and Platt Scaling** (Li & Sur 2025)
   https://arxiv.org/html/2502.15131v4

4. **Balancing the Scales: Tackling Class Imbalance in Binary Classification** (9,000 experiments, 2024)
   https://arxiv.org/html/2409.19751v1

5. **Calibrating LLM-based Guard Models for Reliable Content Moderation** (ICLR 2025)
   https://arxiv.org/abs/2410.10414

6. **Streaming Intended Query Detection using E2E Modeling for Continued Conversation** (2022, EER + DET curve methodology for voice intent)
   https://arxiv.org/pdf/2208.13322

7. **Sequential Device-Addressed Routing (SAS) — 3-class intent detection for voice assistants** (2026)
   https://arxiv.org/html/2604.08412

8. **Classifier Calibration and the End of ROC-Based Threshold Selection** (Valeman 2024)
   https://valeman.medium.com/classifier-calibration-and-the-end-of-roc-based-threshold-selection-d8e52086cb12

9. **A Gentle Introduction to Threshold-Moving for Imbalanced Classification** (MachineLearningMastery)
   https://machinelearningmastery.com/threshold-moving-for-imbalanced-classification/

10. **How and When to Use a Calibrated Classification Model with scikit-learn** (MachineLearningMastery)
    https://machinelearningmastery.com/calibrated-classification-model-in-scikit-learn/

11. **Decision Threshold Setting in Binary Classification: A Behavioral Lens** (Journal of Operations Management, 2026)
    https://onlinelibrary.wiley.com/doi/full/10.1002/joom.70040

12. **A Deep Dive into Calibration of Language Models: Platt Scaling, Isotonic Regression, Temperature Scaling** (KDNuggets)
    https://www.kdnuggets.com/a-deep-dive-into-calibration-of-language-models-platt-scaling-isotonic-regression-temperature-scaling

13. **Calibrating GPT Classifications** (Nyckel blog, 2024)
    https://www.nyckel.com/blog/calibrating-gpt-classifications/

14. **Layer-Aware Embedding Fusion for LLMs in Text Classifications** (2025)
    https://arxiv.org/html/2504.05764v1

15. **Decision Threshold Optimization in Binary Classification: Business-Aligned Strategies** (Medium 2024)
    https://medium.com/@mielmt17/decision-threshold-optimization-in-binary-classification-business-aligned-strategies-836b8929aab2

16. **On Calibration of LLM-Based Guard Models** (ICLR 2025)
    https://arxiv.org/abs/2410.10414

17. **Logistic Regression Makes Small LLMs Strong Classifiers** (2024)
    https://arxiv.org/pdf/2408.03414

18. **Classifier Calibration with Platt's Scaling and Isotonic Regression** (FastML)
    https://fastml.com/classifier-calibration-with-platts-scaling-and-isotonic-regression/

19. **Sampling Control for Imbalanced Calibration in Semi-Supervised Learning** (2025)
    https://arxiv.org/html/2511.18773
