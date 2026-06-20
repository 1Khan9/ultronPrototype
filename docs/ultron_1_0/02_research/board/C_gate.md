# C_gate: Adversarial verdict — always-listening intent gate (rules + EmbeddingGemma + 8B LLM)

**Adversarial agent:** claude-sonnet-4-6 | **Date:** 2026-06-20
**Cluster:** Gate design (B_ddsd_architectures, B_llm_intent_classifier, B_calibration_fusion, B_wakefree_production)
**Adversarial goal:** Refute or qualify whether a cheap rules + EmbeddingGemma-300M cosine gate (with 8B LLM in the undecided band only) can hit an acceptable false-accept rate on continuous ambient / Discord / stream speech, given 114 false-positives per session were observed before.

---

## Claims examined

The Layer-B docs collectively assert:

1. A three-layer cascade (rules → EmbeddingGemma cosine → 8B LLM for ~5–10% undecided band) can achieve acceptable false-accept rate in the always-listening gaming context.
2. Temporal context is the single biggest lever for accuracy (SAS −38 F1 points without it).
3. The 8B LLM (Qwen3-8B via llama-cpp-python 0.3.22) with GBNF-constrained output and `/no_think` will deliver 40–60 ms single-token classification in the undecided band.
4. EmbeddingGemma-300M cosine similarity with a tuned threshold handles the middle layer reliably.
5. The SAS architecture (F1 = 0.86–0.95) is the correct reference frame for feasibility.
6. Cost-asymmetric Platt-scaled threshold τ* ≈ 0.75 gives the right operating point.
7. ASR confidence (`avg_logprob`, `no_speech_prob`) is a free high-value pre-reject signal.

---

## Verdict per claim

### Claim 1 — Three-layer cascade can achieve acceptable false-accept rate

**Verdict: QUALIFIED (not refuted, but the 114 FA/session baseline reveals the gap is much larger than the Layer-B docs suggest)**

**Evidence:**

The 114 false-accepts per session observed in Ultron's live deployment (memory: `ad186cf`) arose specifically because `addressing.follow_up_enabled: true` opened a 120-second post-turn window where *any* VAD-positive segment was escalated to flan-T5-small, which accepted "Okay." and "Why is it suddenly running like this." This is not a failure of the Layer-B design — it is a demonstration of what happens when the temporal gating (window duration, threshold) is misconfigured. The Layer-B design's 8–10 second window with τ ≈ 0.70–0.82 is strictly tighter.

However, three genuine structural problems remain unaddressed by the Layer-B docs:

**Problem A — No characterisation of false-accept rate in multiparty gaming voice specifically.** The SAS paper tests on office/living-room ambient environments, 1–4 speakers. Valorant has a qualitatively different false-trigger distribution: multiple teammates narrating in first person ("I'm going B", "I'm planting"), high-frequency tactical callouts structurally similar to relay commands, and Discord/party voice piped through the game audio mix. None of the Layer-B references benchmark in this domain. The SAS 2.1% false-trigger rate at τ=0.70 is from proprietary smart-speaker data, not validated on gaming voice.

**Problem B — The lexical rules are the gate's strongest component, but they are also the one most likely to fail on gaming-specific disfluent commands.** "Hit 84" without an agent name or relay marker is not caught by Layer 1 rules. If EmbeddingGemma's exemplar set is not curated for gaming, the cosine similarity will over-generalise on short tactical strings because the semantic distance between "hit 84" (directed at Ultron for relay) and "nice hit, 84 damage" (team voice chat) may be very small.

**Problem C — The real false-accept driver in the Valorant context is teammate speech via VoiceMeeter.** If Discord party audio or in-game voice chat bleeds into the user's mic bus (VoiceMeeter B1 → Ultron mic path), then Ultron receives teammate speech as if the user spoke it. The Layer-B docs acknowledge this risk only briefly ("teammate announces position") and propose no specific mitigation beyond more IGNORE exemplars. The 114 FA/session data point is consistent with teammate speech, not just self-talk.

**Source:** Memory (`ad186cf`); SAS paper limitations section (internal evaluation, not gaming-domain validated); B_wakefree_production §Risk 6.

---

### Claim 2 — Temporal context is the single biggest accuracy lever (SAS −38 F1 points)

**Verdict: CONFIRMED, but the SAS result is from a different architecture class and the gain is not directly transferable**

The SAS Stage 3 ablation result (F1 drops from 0.95 → 0.57 without temporal context in audio+video mode) is real and is the paper's own reported number. The principle generalises: classifying utterances without history of the interaction is close to chance in multiparty environments.

**Qualification:** The SAS Stage 3 is an 85K-parameter causal transformer operating on rolling (confidence, VAD state, timing) tuples over 8 seconds at <5ms. The Layer-B docs propose a Python dict with exponential decay as the Ultron equivalent. This is not equivalent. The causal transformer learns non-linear interaction patterns over turn sequences; a rule-based Python dict cannot. The dict approach will capture obvious cases (last 2 turns were RELAY → boost RELAY prior) but will fail on adversarial sequences (teammate chatted right after an Ultron relay → dict boosts RELAY, but next utterance is teammate speech).

**For Ultron 1.0:** The dict approach is better than nothing and is the right MVP. But the Layer-B claim that adding temporal context "dramatically raises F1" rests on a 85K-param trained model, not a hand-coded dict. Expect more modest gains from the dict alone.

**Source:** SAS arxiv 2604.08412 ablation table (confirmed via WebFetch); B_ddsd_architectures §6.

---

### Claim 3 — 8B LLM with GBNF + `/no_think` delivers 40–60 ms single-token classification

**Verdict: REFUTED for thinking-mode suppression; QUALIFIED for latency estimate**

**Critical finding — Grammar enforcement breaks when thinking mode is active:**

GitHub issue ggml-org/llama.cpp #20345 (confirmed via WebFetch) documents that GBNF grammar constraints are **completely bypassed** when `enable_thinking: true` is set. The grammar is applied at the sampling step, but thinking mode inserts `<think>...</think>` tokens before the answer token, effectively producing unconstrained output through the thinking trace and then ignoring the grammar on the answer portion.

For Josiefied-Qwen3-8B, the situation is more complex than the Layer-B docs assume:

- GitHub issue #13189 (llama.cpp b5218, April 2025): `enable_thinking=False` and `--reasoning-format none` did NOT reliably stop `<think>` tags from appearing in Qwen3-32B. The only workaround documented is client-side regex filtering.
- GitHub issue #20182: `enable_thinking` cannot turn off thinking for Qwen3.5 in some llama.cpp builds.
- The Josiefied model is abliterated (RLHF removal pass), which may alter the chat template's thinking suppression behaviour compared to stock Qwen3.

**Consequence:** If thinking mode is active or leaks, the GBNF grammar does not constrain to `RELAY | PRIVATE | IGNORE`. The model generates a thinking trace (100–2000 tokens) and then either times out or emits a free-text response. This is a reliability failure, not just a latency failure. In production, the gate would emit garbage and Ultron would silently fail to classify.

**Latency qualification:** The 40–60 ms estimate assumes `thinking=False` and a 128–200 token prompt. If thinking leaks even 50 tokens before the grammar fires, that adds ~700–1000 ms at 50 tok/s. The Layer-B estimate is correct in the ideal case but does not survive the documented thinking-leak bugs.

**Mitigation not proposed in Layer-B docs:** After every classification call, assert that the first emitted token is exactly one of {R, P, I} or {RELAY, PRIVATE, IGNORE}; if not, default to IGNORE (fail-closed). This regression test must be part of the integration harness, not an assumption.

**Source:** github.com/ggml-org/llama.cpp issue #20345 (grammar+thinking conflict); issue #13189 (enable_thinking=False does not reliably suppress tags, b5218); issue #20182 (enable_thinking param broken for Qwen3.5); B_llm_intent_classifier §Risk 5.

---

### Claim 4 — EmbeddingGemma-300M cosine similarity with a tuned threshold handles the middle layer reliably

**Verdict: QUALIFIED — no gaming-domain validation exists; domain shift is uncharacterised; threshold tuning requires labeled data not yet collected**

**EmbeddingGemma's benchmark coverage:** The paper (arxiv 2509.20354, confirmed via WebFetch) evaluates on MTEB (Massive Text Embedding Benchmark) tasks. MTEB does not include a gaming-voice or tactical-callout domain. The paper does not discuss OOD performance or domain shift to specialised short-text domains. "State-of-the-art at <500M params" is on general-purpose semantic similarity and retrieval tasks, not on gaming utterance discrimination.

**Domain shift risk specific to Valorant:**
- Tactical callouts are extremely short (1–5 words), opaque to context ("B site", "hit 84", "tree", "plant"), and are syntactically near-identical whether addressed to Ultron or spoken to a teammate.
- EmbeddingGemma is not evaluated on sub-5-word utterances; MTEB tasks use sentence-length texts.
- The documented clinical-domain failure mode (embedding "no evidence of tumour" near "evidence of tumour") applies structurally: "tell my team Jett hit B" and "Jett hit B already" have high cosine similarity in general sentence embedding space despite opposite relay intent.
- The threshold values (cosine > 0.82 accept; cosine < 0.45 reject) proposed in B_llm_intent_classifier are explicitly flagged there as "heuristic starting points" requiring tuning on labeled data. That labeled data does not yet exist in the Ultron system.

**Without labeled gaming-voice data, the cosine gate cannot be tuned and operates at arbitrary thresholds.** An incorrectly-placed threshold floods Layer 3 (LLM) with all utterances — destroying the cascade's latency budget — or accepts/rejects all utterances at Layer 2 without the LLM's disambiguation.

**Source:** EmbeddingGemma paper (arxiv 2509.20354, no gaming-domain eval); clinical cosine failure mode (ResearchGate EmbeddingGemma review); B_llm_intent_classifier §Risk 7.

---

### Claim 5 — SAS architecture (F1 = 0.86–0.95) is the correct reference frame for feasibility

**Verdict: QUALIFIED — the SAS result is an upper bound, not a prediction for Ultron's configuration**

**Critical gaps between SAS and Ultron:**

| Factor | SAS | Ultron 1.0 |
|--------|-----|-----------|
| Microphone array | ≥2 mics (Stage 1 beamforming) | Single USB mic |
| Stage 1 contribution | −14 F1 points if removed | Permanently absent |
| Stage 2 model | 435K-param trained CNN+GRU on 600h labeled audio | No acoustic model (text-only via Whisper) |
| Training dataset | 600h proprietary multi-speaker, curriculum-trained | No training data; zero-shot |
| Test environment | Office/living-room, 1–4 English speakers, no gaming audio | Valorant gaming, Discord audio mix, game sound bleed |
| False-trigger content | TV dialogue | TV + Discord + teammate voice chat + game audio |
| Stage 3 context model | 85K-param causal transformer (trained) | Hand-coded Python dict (untrained) |

SAS at audio-only (no Stage 1) gets F1 = 0.84 on its in-domain test set. Removing Stage 3 drops it to 0.57. Ultron's equivalent has no Stage 2 acoustic model and a much weaker Stage 3. The realistic comparable configuration in the SAS ablation table is closer to **F1 = 0.57–0.70** than the headline 0.86–0.95.

Furthermore, SAS's headline false-trigger rate of 2.1% is on smart-speaker environments. In TV-heavy sessions it rises to 7.8% at the same threshold. Valorant is analogous to the TV-heavy environment (continuous ambient audio) — expect false-trigger rates in the 7–15% range unless the threshold is raised significantly (at the cost of missed relays).

**Source:** SAS paper Table 3 ablation and §5.2 limitations (WebFetch confirmed); B_ddsd_architectures §3e; B_wakefree_production §1.

---

### Claim 6 — Cost-asymmetric Platt-scaled threshold τ* ≈ 0.75 gives the right operating point

**Verdict: CONFIRMED in principle, QUALIFIED for bootstrapping**

The cost-ratio formula τ* = C_FP / (C_FP + C_FN) is standard calibration theory (Bayes-optimal under calibrated posteriors). The critique here is practical: Platt scaling requires calibrated posteriors, and calibrated posteriors require labeled data. The Layer-B docs themselves say the minimum is 100 labeled examples per gate before Platt is reliable (B_calibration_fusion §Risk: Small Calibration Set Risk). Below 80 examples, "use fixed τ from cost-ratio formula and uncalibrated rule/embedding scores."

Since no labeled gaming-voice intent dataset exists for Ultron yet, the τ* = 0.75 is the correct starting point but must be treated as a raw uncalibrated heuristic until ≥100 labeled turns are collected. The framework is sound; the bootstrapping timeline is not addressed.

**Additionally:** The 3-way RELAY/PRIVATE/IGNORE decomposition proposed in B_calibration_fusion is correctly noted to require binary cascade decomposition at small data scales. This requires TWO independent gate tuning pipelines (addressing gate + relay gate), each needing ≥100 labeled turns. The combined labeling burden is 200+ turns before any calibration is principled.

**Source:** B_calibration_fusion §Risks (Small Calibration Set Risk); §3 (Calibration Method Hierarchy).

---

### Claim 7 — ASR confidence (`avg_logprob`, `no_speech_prob`) is a free high-value pre-reject signal

**Verdict: CONFIRMED**

The Apple paper (arxiv 2403.14438) shows that adding ASR decoder confidence signals ("graph cost, acoustic cost, word-level posterior, competing hypothesis count") to a text+audio fusion model delivers a further 6.9% relative EER reduction (6.81% → 6.34%). faster-whisper's `avg_logprob` and `no_speech_prob` are the practical equivalents. These are already computed in Ultron's STT pipeline and cost zero additional inference.

The Layer-B recommendation to gate on `no_speech_prob > 0.6` (reject as ambient noise) and adjust cosine threshold when `avg_logprob < -1.2` is well-grounded. The only caution: these thresholds are also untuned estimates. A gaming session with heavy gunfire audio bleed will have consistently low `avg_logprob` even on clear user speech — if the gate is too aggressive, genuine relay commands get pre-rejected.

**Source:** arxiv 2403.14438 (Apple multimodal DDSD); B_wakefree_production §B (ASR confidence gate).

---

## Corrected recommendation for Ultron 1.0

The Layer-B design is architecturally sound. The three-layer cascade is the right approach. The following corrections and additions are required before it can achieve acceptable false-accept rates in the Valorant/Discord gaming context:

**1. Do not claim the SAS F1 = 0.86–0.95 ceiling is achievable without the acoustic model and without training data.** The realistic target for Ultron's text-only, zero-shot, single-mic configuration is F1 ≈ 0.65–0.75 initially, improving with labeled data and threshold tuning. Set expectations accordingly.

**2. Treat the GBNF + `/no_think` constraint as unreliable until verified on the specific in-process llama-cpp-python 0.3.22 + Josiefied-Qwen3-8B-abliterated build.** Add an assertion after every intent gate call:
```python
assert label in {"RELAY", "PRIVATE", "IGNORE", "R", "P", "I"}, f"Gate emitted unexpected token: {label!r}"
```
If the assertion fails, default to IGNORE. Log the raw output for debugging. Test this at startup with a synthetic utterance before opening the live gate.

**3. For the follow-up window, adopt the 8–10 second production spec (not the 120-second window that caused 114 FA/session).** This alone eliminates the majority of the observed false-accept rate. The current `config.yaml addressing.follow_up_enabled: false` is the correct safe default.

**4. Add VoiceMeeter channel isolation verification as a prerequisite.** If game audio or Discord party audio bleeds into the B1 bus (user mic path → Ultron), no amount of intent gating will prevent false triggers on teammate speech. Verify that only the user's physical mic reaches Ultron's STT input before enabling always-listening mode.

**5. Bootstrap the exemplar set with gaming-specific labeled data before tuning thresholds.** Collect 200+ labeled turns from live sessions (at least 50 RELAY, 50 PRIVATE, 100 IGNORE), including:
   - Teammate-voice-chat false triggers (the primary failure mode)
   - Terse tactical callouts that ARE relays ("Jett B", "three here", "one left")
   - Discord/stream ambient speech ("nice bro", "what rank", "let's go")
   
   Only after this corpus exists should Platt scaling or cosine threshold tuning be attempted.

**6. Keep wake-word mode as the stable default for competitive play.** The always-listening gate should be an opt-in feature flag with explicit user consent, not the default mode. The data from 114 FA/session shows that even a competent gating design produces significant noise if the temporal and threshold parameters are wrong. In a competitive match, each false trigger produces a team-visible relay blast — the cost is not symmetric to a missed relay.

**7. Temporal context dict must handle the teammate-speech case explicitly.** After a classified IGNORE, set a short skepticism window (2–3 seconds) during which the RELAY prior is suppressed. This handles the most common false-trigger sequence in gaming: user relays → Ultron responds → teammate speaks within 3s → Ultron wrongly classifies teammate as user.

---

## Residual risks

| Risk | Severity | Mitigation status |
|------|----------|-------------------|
| Grammar + thinking mode conflict in llama.cpp (issues #20345, #13189, #20182) | HIGH — silent gate failure | Not mitigated in Layer-B docs; requires startup assertion |
| Teammate voice bleed via VoiceMeeter into user mic bus | HIGH — undetectable false triggers | Must be verified as architectural prerequisite |
| No gaming-domain validation for EmbeddingGemma cosine gate | HIGH — untuned thresholds flood Layer 3 or create blind spots | Requires 200+ labeled turns before deployment |
| SAS F1 reference is unachievable without acoustic model | MEDIUM — sets wrong expectations | Acknowledged; target F1 0.65–0.75 is more realistic |
| Short utterance semantic proximity in gaming tactical text | MEDIUM — "Jett B" looks like IGNORE and like RELAY to embedding model | Requires gaming-specific exemplars and potentially per-class exemplar weighting |
| Platt scaling requires ≥100 labeled examples; none exist yet | MEDIUM — τ* is heuristic until data exists | Known in Layer-B docs; timeline not specified |
| Valorant game audio (gunfire, abilities) causing false VAD triggers that reach STT | MEDIUM — adds ambient speech candidates to the gate | `no_speech_prob` gate mitigates but thresholds untuned |
| Calibration collapse of Qwen3 P(YES) on RELAY class (AUC < 0.55) | LOW-MEDIUM — LLM column in fusion becomes noise | Monitor; drop LLM column if AUC < 0.55 on labeled logs |
| always-listening in competitive Valorant (anticheat risk from continuous processing) | LOW (design is anticheat-safe) but HIGH (trust risk if false relays broadcast to team) | Keep as opt-in; document clearly |

---

## Sources

1. SAS paper (Kim et al., 2026) full text — limitations section: dataset is proprietary, English-only, office/living-room, not gaming-validated. Single-mic F1 = 0.84. TV false-trigger rate = 7.8% at τ=0.70. https://arxiv.org/html/2604.08412

2. llama.cpp GitHub issue #20345 — Grammar enforcement completely inactive when `enable_thinking: true`, confirmed on Qwen3-VL-8B and Qwen3.5-35B. No fix merged as of the issue date. https://github.com/ggml-org/llama.cpp/issues/20345

3. llama.cpp GitHub issue #13189 — `enable_thinking=False` and `--reasoning-format none` do NOT stop Qwen3-32B thinking tags (b5218). Only workaround is client-side regex. Bug labeled stale. https://github.com/ggml-org/llama.cpp/issues/13189

4. llama.cpp GitHub issue #20182 — `enable_thinking` param cannot turn off thinking for Qwen3.5. Active bug. https://github.com/ggml-org/llama.cpp/issues/20182

5. EmbeddingGemma paper (arxiv 2509.20354, WebFetch) — MTEB evaluation only; no gaming-domain or short-tactical-text evaluation; no OOD or domain shift discussion. https://arxiv.org/pdf/2509.20354

6. Apple multimodal DDSD paper (arxiv 2403.14438) — ASR decoder confidence signals add 6.9% relative EER improvement for free. Text+audio fusion = 6.81% EER. https://arxiv.org/html/2403.14438v2

7. Ultron live system memory (ad186cf) — 114 false-accepts/session from 120-second follow-up window, flan-T5 accepting "Okay." and conversational teammate speech. Confirmed root cause: temporal window too long, threshold too permissive.

8. Ultron live system memory (A_gate.md codebase scan) — Current HEAD: `ZeroShotAddresseeModel.classify()` flat 0.75 constant (not real P(YES)); `_DIRECT_ADDRESS` regex kenning-only ("ultron" absent); log-odds fusion (9438fc5) NOT on HEAD. Confirms gap between Layer-B recommendation and current implementation.

9. B_ddsd_architectures §3e — SAS ablation table: removing Stage 3 (temporal context model) drops F1 from 0.95 to 0.57; removing Stage 1 (beamforming) drops from 0.95 to 0.81. Ultron lacks both.

10. B_calibration_fusion §Risks — Minimum 100 labeled examples per gate before Platt scaling is reliable. Below 80, use fixed cost-ratio τ only.

11. B_llm_intent_classifier §Risk 7 — Cosine similarity thresholds (0.45, 0.82) are heuristic starting points requiring labeled data tuning. Not yet tuned for Ultron.
