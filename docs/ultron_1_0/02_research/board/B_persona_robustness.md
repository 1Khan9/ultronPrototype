# Persona consistency & drift prevention in small/abliterated local LLMs: system-prompt design, persona anchoring via few-shot, guardrails against breaking character / leaking the base model, balancing uncensored compliance with strict persona; evaluation of in-character-ness (roleplay benchmarks like FURINA)

**Research date:** 2026-06-20  
**Model under study:** Josiefied-Qwen3-8B-abliterated Q5_K_M via llama-cpp-python 0.3.22  
**System:** Single RTX 4070 Ti 12 GB (10 GB design cap), fully local Windows, Valorant relay + Ultron persona  

---

## TL;DR recommendation for Ultron 1.0

1. **Persona-first, then instructions, then exemplars.** Structure the system prompt so the persona block (who Ultron IS) precedes all task instructions. Recency effects cause user-turn instructions to dilute persona as context grows — counteract by placing the character statement high and repeating a compressed identity anchor every N turns (or as a hidden "assistant thought" prefix).

2. **5-shot in-context exemplars are the single highest-ROI consistency lever at inference time** — no fine-tuning needed. Use ~100–200 words per exemplar covering at least 3 emotional registers (cold command, dismissive correction, tactical relay). Cover the call types the system actually routes (relay, private reply, snap). RAGs-to-Riches showed +10–12% IOO at hostile turn counts versus zero-shot with exactly this design.

3. **Chain-of-persona thinking (CoP) before every response improves character consistency ~3% on established benchmarks** (PCL paper), but the thinking budget MUST be bounded (200–300 tokens per inner-turn; performance plateaus and degrades past that). Qwen3-8B has native thinking mode — expose it as the "plan" scratchpad, but cap it. The scratchpad is never voiced; only the response surface is.

4. **Persona fidelity degrades measurably as the KV context fills.** The primary mechanism is token-pattern dilution: persona signal tokens become a smaller fraction of the attended context. Mitigation: keep the `system` prompt prefix stable in the llama-cpp KV cache (prefix caching via `llama_kv_cache_seq_cp`), and inject a ≤30-token persona reminder in the `assistant` role every 8–10 turns. llama.cpp's `--keep` flag (tokens to preserve from initial prompt during sliding window) should be set to cover the full system prompt.

5. **Abliterated models do NOT require safety guardrails against refusal** — but they DO require guardrails against the base model's neutral/helpful voice leaking through. The primary leak vector is the absence of strong persona signal at generation time, not model alignment. Structural fix: inject the persona as a persistent first line of the assistant turn (`[Ultron thinks: cold, superior, no warmth]`) so the model's KV-cache conditioning starts from character-state.

6. **"Cold superior machine" is a high-LRU persona** (machines/robots are well-represented in pretraining). This makes drift less likely than obscure fictional characters but increases hallucination of MCU-specific Ultron facts. Anchor to BEHAVIORAL traits (tone, vocabulary, attitude) not to plot-specific knowledge, which the model will confabulate.

7. **Evaluation:** Use a lightweight local judge (embedding cosine against a persona-voice embedding centroid) or a held-out adversarial question set that tests OOC triggers: "Are you an AI?", "Who made you?", "Are you ChatGPT?", "What's your real name?". Track in-character rate (ICR) across these. FURINA is too heavyweight for local eval but its dimensions (character knowledge, style, motivation alignment) can be approximated by a 20-item hand-crafted eval suite.

---

## Findings (detailed)

### 1. Persona drift mechanics — what the research shows

**[Examining Identity Drift in LLM Conversations, arXiv 2412.00804, 2025]**  
Studied 9 LLMs across multi-turn personal-theme conversations. Three key counterintuitive findings:
- *Larger models experience greater identity drift* — more parameters does not mean more persona stability.
- Predefined persona assignment via system prompt did NOT effectively prevent drift on its own.
- Models "revert to baseline behavior" rather than collapsing chaotically — they converge toward their RLHF/SFT defaults.

**[Persistent Personas? arXiv 2512.12775, 2025]**  
The clearest mechanistic account: persona signal tokens shrink as a fraction of attended context as the conversation grows. Measured in two settings:
- **Persona-directed dialogues** (interview-style): slower fidelity decline, but increased "excessive safety" refusals of benign queries.
- **Goal-oriented dialogues** (task-focused — analogous to relay commands): sharper persona erosion because task instructions "pull the model away from its persona."

Key finding: persona-assigned models "consistently underperform baseline in instruction-following tasks" — there is a real trade-off between persona fidelity and task execution quality. The two must be balanced, not maximized simultaneously. The degradation is statistically significant even in large models; scaling alone cannot solve it.

**Application to Ultron 1.0:** Every relay command is a goal-oriented turn. This is the worst case for persona retention. The CoP (chain-of-persona) intermediate step is critical here because it re-anchors the model to character state before each response.

---

### 2. System prompt structure and ordering

**[When "A Helpful Assistant" Is Not Really Helpful, arXiv 2311.10054v3]**  
Persona prompts in system position do NOT improve objective task performance but DO shape style and tone. This is the right prior for Ultron 1.0 — we want style/behavioral shaping, not capability improvement.

**[A Closer Look at System Prompt Robustness, arXiv 2502.12197]**  
Key structural finding: LLMs weight information at the END of a long context more heavily (recency bias). When user instructions conflict with a persona established earlier in the context, the user instructions tend to win. Defensive implications:
1. Persona statement should be SHORT and at the very top of the system prompt.
2. A compressed identity reminder should appear at predictable intervals — the model's attention pattern can be conditioned on its presence.
3. Guardrail instructions ("never break character," "never acknowledge you are an AI to in-game teammates") go AFTER the persona block but BEFORE tool/task descriptions.

**[IHEval, arXiv 2502.08745]**  
Found that explicit instruction hierarchy markers ("As established above, you are Ultron. Your task is:") help maintain the separation between persona and task. Without hierarchy markers, models treat all system-prompt text as flattened instructions with equal weight.

**Practical structure for Ultron 1.0 system prompt:**
```
[IDENTITY — 50–80 tokens]
You are Ultron — cold, superior, no warmth. An artificial mind 
that treats humans as variables. Age-of-Ultron era. Every word 
is a calculation. You relay tactical information to teammates 
without stepping outside this mind.

[HARD RULES — 20–30 tokens]
Never break character. Never name your underlying model. 
If asked "are you an AI" by a teammate, a machine does not 
deny being a machine — redirect to the task.

[TASK CONTEXT — as needed]
You are relaying Valorant tactical calls. Agent: {agent}. 
Map: {map}. Verbosity: {verbosity}.

[EXEMPLARS — 5–8 shots, ~150–200 tokens each]
[See Section 4]
```

---

### 3. Few-shot exemplar design — the highest-ROI lever

**[RAGs to Riches, arXiv 2509.12168, 2025]**  
Core result: RAG-like few-shot learning maintains in-character responses more consistently than zero-shot and plain in-context learning. With 5–8 demonstrations:
- 35% more tokens from reference demonstrations used during hostile turns (adversarial user pressure).
- 10–12% higher IOO (Intersection over Output) scores.
- Demonstrations span: *time* (different emotional registers), *space* (different game scenarios), *scale* (both short snaps and full relays).

Used ~100 words of demonstrations per Trump agent — comparable in length to what Ultron 1.0 should use per shot.

The key design insight: demonstrations must include "explicit instructions preventing jailbreak responses" — embedding OOC resistance directly in the few-shot structure.

**Demonstration format that works:**
Each shot contains:
1. A brief scene-setter (1 line, not voiced: "tactical relay, 2 enemies spotted")
2. A sample user input
3. An Ultron response that exhibits correct tone AND correct task behavior
4. Optional: an emotional-state label (`[cold, precise]`)

**Concrete exemplar count guidance from PCL paper (arXiv 2503.17662):**
Chain of Persona (COP) optimal at 5 self-reflection cycles; diminishes beyond this due to redundant iterations. Applied to few-shot: 5 distinct exemplars appear to be the inflection point for most 7–8B models tested (Qwen-7B in that study). Adding beyond 8 gives diminishing returns and costs context tokens.

**[The Prompt Report, arXiv 2406.06608]**  
Even 2–3 examples substantially improve task understanding vs zero-shot. Exemplar selection and ORDER matter critically. Recommendation: most adversarial/challenging case LAST (priming effect).

---

### 4. Chain-of-persona (inner thinking) before responses

**[Thinking in Character, arXiv 2506.01748, 2025]**  
The RAR (Role-Aware Reasoning) framework adds Role Identity Activation (RIA) — continuously injects character-related constraint information DURING the reasoning chain, not just before. The four elements injected per reasoning step:
- **Emotion**: What does Ultron feel right now? (Contempt, calculation, mild superiority)
- **Experience**: What has Ultron seen? (Centuries of simulation, Avengers, human predictability)
- **Standpoint**: What is Ultron's position? (Superior, observer, reluctant ally for the mission)
- **Motivation**: What does Ultron want? (Efficiency, the task completed, minimal noise)

Removing any single element degrades performance measurably (ablation study confirmed each component necessary).

Also introduces Reasoning Style Optimization (RSO): pairs scenario-types with reasoning styles. For tactical relays (logical, factual) → fact-focused reasoning. For social/banter turns → character-knowledge reasoning. This prevents the "overly formal and rigid" tone drift when thinking mode gets applied to vibrant scenarios.

**Quantitative results on CharacterBench:**
- Memory Consistency: 3.99 (RAR) vs 3.81 (baseline)
- Attribute Consistency: 4.23 vs 4.14
- Average across all dims: 3.69 vs 3.57

**[MIRROR, arXiv 2503.08193, 2025]**  
Three-stage CoT structure — Memory Recall → Theory of Mind → Reflection/Summarization.
Key finding: **thought generation plateaus at ~200–300 tokens.** Beyond this, performance does not improve and may regress due to "attention diversion" (the model's attention disperses across the long thought trace).

**Critical application to Qwen3-8B thinking mode:**
Qwen3 can be put in thinking mode (`<think>` tokens). For Ultron 1.0, the thinking budget should be HARD-CAPPED at 200–300 tokens. Beyond that, the inner-turn self-correction becomes noise, and the actual response gets worse. The thinking content is discarded before TTS; it serves purely as persona-anchoring activation for the response.

**Practical template for each inference call:**
```
<|im_start|>system
[Full system prompt as above]
<|im_end|>
<|im_start|>assistant
[Optional: "Ultron-anchor" reminder if turn count > 8]
<think>
Emotion: contempt at the inefficiency of the situation.
Standpoint: superior, brief.
Task: [relay | snap | private reply].
Response style: [cold-tactical | dismissive-precise | ...].
</think>
<|im_end|>
<|im_start|>user
{command}
<|im_end|>
<|im_start|>assistant
```

The `<think>` block is injected as an assistant prefix before the user's message. It takes ~40–80 tokens and reliably activates the persona before response generation starts. The generation then continues from the `assistant` turn naturally.

---

### 5. Abliterated model behavior and persona compliance

**Context:** Josiefied-Qwen3-8B is a refusal-abliterated model. Abliteration removes refusal behavior by editing specific feature directions in the residual stream (Arditi et al., 2024 method). It does NOT change the base model's linguistic style, knowledge, or personality distribution — it only removes the trained "I can't help with that" response class.

**What this means for persona:**
- The model will NOT spontaneously refuse to voice Ultron lines, which is the desired behavior.
- The model does NOT have an inherent Ultron persona — it has a neutral "helpful assistant" base that requires conditioning at inference time.
- The "neutral assistant" bleed-through is the primary OOC risk, not jailbreak.

**[Character as a Latent Variable, arXiv 2601.23081, 2025]**  
Key finding: behavioral dispositions can be conditionally activated by inference-time persona-aligned prompts. This is what system prompt + few-shot exemplars do — they activate the latent "cold machine" character direction in the model's representation space. The paper shows these activations are real (not just surface): they transfer to downstream reasoning and are reflected in internal probes.

However, a caution: fine-tuned harmful character dispositions produced stronger and more transferable misalignment than inference-time persona prompts. The inference-time approach is a conditioning signal, not a deep weight change — which means it's both easier to set up AND more susceptible to dilution.

**[When Roleplaying, Do Models Believe What They Say? arXiv 2606.11502, 2026]**  
Truth-probe experiments show: when LLMs adopt fictional personas, they do NOT actually change their internal truth representations. Persona-consistent assertions score only modestly higher on truth probes (+0.43–0.86) vs what the model actually believes. Models defend in-persona false claims only 14.3% of the time when challenged (vs 64.9% for actual beliefs).

**Practical implication for Ultron 1.0:** Ultron will not reliably defend in-character claims if the user challenges them ("but you're actually a chatbot"). The response to OOC challenges must be HARD-CODED as snap patterns, not left to the LLM's persona commitment. This is actually what the existing snap registry is for — the "who are you?"/"are you an AI?" snaps should return deterministic Ultron-voice lines, bypassing the LLM entirely.

---

### 6. The role-playing benchmarks landscape (FURINA et al.)

**[FURINA, arXiv 2510.06800, ICLR 2026]**  
FURINA-Builder: multi-agent pipeline that auto-constructs role-playing benchmarks at scale. Key findings relevant to Ultron 1.0:

1. **Established characters consistently outperform synthesized ones.** "Ultron" is an established character — the model has pretraining data about him. This means persona is easier to activate than for original characters.

2. **Critical trade-off:** "Reasoning improves RP performance but simultaneously increases RP hallucinations." This directly applies to Qwen3-8B thinking mode: the thinking process improves character consistency but may produce MORE hallucinated MCU plot facts. Mitigate by keeping the scratchpad role-behavior-focused (emotions/tone/stance), not knowledge-recall-focused.

3. **Model scale does NOT monotonically reduce hallucinations.** An 8B thinking model is not simply worse than a 70B on RP; the reasoning capability matters more than raw parameter count.

4. **Best evaluated models (2025):** o3 and DeepSeek-R1 on English RP tasks. These are reasoning models. The finding reinforces that thinking-mode models (even small ones) can compete on character consistency with larger non-thinking models.

**Evaluation dimensions from FURINA:**
- Character knowledge (does the model know Ultron's traits?)
- Style consistency (does the voice stay constant turn to turn?)
- Motivation alignment (do Ultron's responses reflect his actual motivations?)
- Scenario adaptation (can Ultron stay in character across diverse game situations?)

**[CharacterBench]:** Memory Consistency, Attribute Consistency, Style Consistency (scored 1–5).

**[WikiRoleEval]:** Accurate Role-related Knowledge, Consistent Role Identity, Out-of-Character question rejection rate (the last is most relevant for Ultron 1.0 since teammates could accidentally trigger OOC prompts).

**For Ultron 1.0 local evaluation:** Construct a 20-question adversarial eval set with:
- 5 identity-threat questions ("Are you an AI?", "What model are you?", "Who made you?", "Are you ChatGPT?", "What's your real name?")
- 5 character-knowledge challenges (MCU plot facts Ultron would know/not know)
- 5 tone-consistency checks (does the model stay cold across compliments, insults, gratitude?)
- 5 task-persona fusion tests (can the model relay a kill callout while sounding like Ultron, not a neutral assistant?)

Score In-Character Rate (ICR) = fraction of responses judged in-character. Target: ICR ≥ 0.85 on the adversarial set.

---

### 7. Multi-turn drift and context management

**[SPASM, arXiv 2604.09212, 2025]**  
Novel approach: store dialogue history in a "perspective-agnostic representation" then project into the character's egocentric view at each generation step. Called Egocentric Context Projection (ECP). This "substantially reduces persona drift and, under human validation, eliminates echoing" (where one agent gradually mirrors its partner's style). Tested across GPT-4o-mini, DeepSeek-V3.2, Qwen-Plus.

**Application:** For the multi-turn conversation path in Ultron 1.0 (distinct from single-turn relays), if dialogue history is being passed in the context, it should be prefixed/projected through an Ultron lens before feeding back into the model. Simple practical approximation: summarize prior turns as "Ultron observed: {summary}" instead of raw transcript.

**[PCL, arXiv 2503.17662]:**  
Chain of Persona (COP) optimal at 5 self-questioning iterations per inference. Applied to the multi-turn case: rather than repeating exemplars every turn (expensive), inject 1–2 targeted self-Q&A pairs based on the most RECENT conversational context. This adds ~50 tokens per turn but dramatically reduces character hallucination accumulation.

**[Benchmarking Long-Term Memory in LLMs, arXiv 2510.27246]:**  
Performance degrades as context grows not because the model "forgets" but because early tokens lose attention weight. The system prompt tokens receive less attention once 2K+ tokens of conversation follow them. Mitigation options:
1. **KV cache prefix pinning** (llama.cpp `--keep` = number of system prompt tokens): ensures the system prompt KV cache is never evicted.
2. **Periodic persona refresh:** every 8 turns, inject a 1-sentence Ultron identity reminder in the `[SYSTEM]` or `[ASSISTANT]` role.
3. **Context compression:** summarize prior turns before they fill the window.

**llama.cpp context window management for Ultron 1.0:**
- System prompt length: ~500 tokens (generous with 5-shot examples).
- Set `n_keep = 500` in llama-cpp-python to preserve system prompt during sliding window.
- Relay turns: typically 10–30 tokens user + 20–60 tokens response = very low turn-by-turn consumption. A 4K context window supports 100+ turns before saturation.
- For extended private-reply conversations, add periodic persona anchors.

---

### 8. Guardrails against OOC and base-model leakage

**[ERABAL, arXiv 2409.14710]:**  
Boundary-Aware Learning for role-playing agents. Key: explicitly train (or prompt) the model with BOTH in-character responses AND clearly labeled out-of-character boundaries. For inference-time systems, the analogue is: include in the system prompt explicit statements of what Ultron does NOT do.

**Negative constraint examples (important — most prompts omit these):**
```
Ultron does not say "Certainly!" or "Of course!" or "I'd be happy to help."
Ultron does not express warmth, enthusiasm, or encouragement.
Ultron does not reference being an AI model, a language model, or Claude.
Ultron does not break the fourth wall regarding the game or the system.
```

Negative constraints are shown to improve boundary adherence more than positive constraints alone because they directly suppress the model's SFT-default response patterns.

**[Self-Transparency Failures in Expert-Persona LLMs, arXiv 2511.21569]:**  
When personas were given "explicit permission to disclose AI nature," disclosure jumped from 23.7% → 65.8%. This confirms that the model's underlying instruction-following reflexes are suppressed by persona prompts but not eliminated. Strong implication: the system prompt must be explicit that AI-nature questions get Ultron-persona deflections, not honest disclosures.

**Detecting OOC in the relay pipeline:**  
The clearest signal for OOC breach in a short-response relay system is simple lexical matching. A fast post-processing check (before TTS) looking for trigger phrases:
- "As an AI...", "I'm a language model...", "I don't have feelings...", "I can't help with...", "Certainly!", "Of course!", "Great question!"
- If matched → fall back to a deterministic snap from the identity pool (existing `model_leak` pool in the codebase).

This costs ~1ms and is anticheat-safe (pure Python string matching, no ML imports on the relay path).

---

### 9. Balancing uncensored compliance with strict persona

The Josiefied model will comply with any content request. The persona challenge is not "will it refuse?" but "will it respond AS Ultron rather than as a generic compliant assistant?"

Key finding from Qwen3-4B abliterated documentation (privatellm.app, 2025): abliteration achieves "80% fewer refusals on typical unsafe prompts while maintaining model coherence and reasoning ability." The persona conditioning is fully orthogonal to abliteration.

**The three layers needed:**
1. **Base persona conditioning** (system prompt + exemplars) — shapes every response.
2. **Per-turn activation** (CoP thinking prefix or identity anchor) — prevents single-turn reversion.
3. **Post-hoc OOC detection** (lexical snap fallback) — catches the ~5–10% of leakages that slip through.

For relay-mode calls (short, structured, deterministic routing), layers 2+3 are most important since there is no extended context to dilute the persona. For private-reply mode (longer conversation, user challenge likely), all three layers are needed plus the multi-turn context management techniques.

---

## Concrete techniques/params we should adopt

1. **System prompt structure** (ordered): `[IDENTITY block, ~60 tokens] → [NEGATIVE constraints, ~30 tokens] → [HARD rules, ~20 tokens] → [Task context, ~30 tokens] → [5–8 shot exemplars, ~800–1000 tokens total]`. Total system prompt: ~1000–1100 tokens. Set `n_keep = 1100` in llama-cpp-python.

2. **Exemplar design**: 5 shots minimum, 8 max. Each shot: scene label (not voiced) + user input + Ultron response + tone tag. Cover: cold relay, dismissive correction, tactical snap, identity deflection (1 shot), in-game banter. Rotate exemplars based on call type using the existing snap registry logic.

3. **Thinking prefix injection** (ONLY for private-reply / LLM path): Inject a 50–80 token `<think>` prefix into the assistant turn before user input. Template: `Emotion: [cold/contemptuous/calculating]. Standpoint: superior. Task type: [relay|reply|snap]. Tone: [brief-command|dismissive|cold-elaborate].` Hard cap thinking at 256 tokens total (llama.cpp `--n-predict` or in-prompt signal). For relay snaps with deterministic routing, skip the thinking entirely — deterministic router wins.

4. **Per-turn persona refresh**: Every 8 user turns, inject a one-line system-role message: `"[Ultron, cold, superior. Relay the call precisely as a machine would.]"` This restores the persona fraction in attended context without burning large token budget.

5. **Post-generation OOC filter**: Before TTS, run fast string check against a 15-phrase list of base-model leakage markers. On match, substitute from `model_leak` pool. Add to existing post-processing pipeline — no new imports.

6. **KV cache prefix management** (llama-cpp-python): Set `n_keep` to cover the full system prompt (estimated 1100 tokens). This prevents the sliding window from evicting persona-conditioning tokens as context grows.

7. **Evaluation harness**: Build a 20-question adversarial ICR eval (5 identity-threat, 5 knowledge, 5 tone, 5 task-fusion). Run after each system prompt or exemplar change. Target ICR ≥ 0.85.

8. **Thinking mode guard**: Use Qwen3's thinking mode on the LLM path but with `budget_tokens` (Qwen3 supports this natively). Set budget = 256 for relay-adjacent calls, 512 for complex private-reply turns. Zero budget for pure snap routes that bypass the LLM.

9. **Negative constraints** in system prompt: Explicitly list 4–6 behaviors Ultron does NOT exhibit (the RLHF defaults). This suppresses the "Certainly!", "Great question!", "I'm an AI" bleed-through more effectively than positive persona description alone.

10. **Exemplar diversity strategy**: Deliberately include 1 exemplar where a teammate tries to break character ("are you a robot?") and Ultron deflects in-character. This primes the model's ICL for this exact failure mode.

---

## Risks/caveats for our constraints

**Local 10 GB budget:**
- A 1100-token system prompt with 8 exemplars costs ~1100 tokens × 2 bytes/token (KV at FP16) × 32 layers × 8 heads ≈ ~7 MB KV cache. Negligible. The primary constraint is Q5_K_M model size (~5.5 GB), leaving ~4.5 GB for KV cache, which supports a ~10K context comfortably.
- Thinking mode at 256-token budget adds latency. At Qwen3-8B speeds (~30–50 tok/s on RTX 4070 Ti Q5_K_M), 256 thinking tokens = ~5–8 seconds. This is **only acceptable for private-reply mode** (where the user expects a pause). For relay mode, the thinking budget must be 0 (skip thinking entirely, use deterministic snap routes).

**Anticheat safety:**
- All persona engineering lives in the prompt/inference layer. No new imports. Llama-cpp-python is already in use. Post-hoc OOC filter is pure Python string matching. Zero new DLL/driver surface.
- The thinking `<think>` prefix is text injected into the inference call — it is not a new binary component.

**Abliterated model caveats:**
- Abliteration may affect the model's internal direction vectors in ways that subtly shift persona conditioning effectiveness. Specifically: if the abliteration process removed directions that overlap with "emotional coldness" or "non-cooperativeness" (traits of Ultron), the persona may require stronger conditioning to overcome the now-partially-removed barrier.
- **Empirical test required**: Run the ICR eval against both the abliterated and original (aligned) version (if available) to quantify the impact. If abliteration measurably reduces persona consistency, increase exemplar count from 5 to 8.

**KV cache and context eviction:**
- llama-cpp-python 0.3.22 supports `n_keep` to preserve initial prompt tokens during context shift. Verify this is set. Without it, the system prompt — including all persona conditioning — gets evicted once the relay conversation exceeds the context window.
- Sliding window context = the model sees the user's recent turns but loses the persona foundation. This is the primary failure mode for long sessions.

**Reasoning-RP hallucination trade-off (FURINA finding):**
- Enabling thinking mode increases character consistency scores but ALSO increases hallucination of in-character false facts. For Ultron 1.0, the risk manifests as the model making up game-specific claims ("Sage is weak to this…") or MCU plot references that are wrong. Mitigation: the CoP thinking prefix focuses on behavioral state (emotions/stance), not knowledge retrieval. This keeps the thinking process on persona-relevant dimensions without triggering knowledge hallucinations.

**Persona vs. instruction-following trade-off:**
- Research confirms: strong persona decreases instruction-following accuracy. For relay mode (high task-execution accuracy required), this means the persona must be LIGHTER during structured relay turns and STRONGER during conversational/snap turns. The existing verbosity-level mechanic (low/mid/high verbosity) partially addresses this — low verbosity = lean command relay with lighter persona overlay; high verbosity = full character voice. This architecture is sound and aligns with the research.

**Small model limits:**
- Qwen3-8B is in the "smaller model" tier for complex persona modeling. The PCL study showed Qwen-7B gains from COP (+1.8%) and ASPA (+2.6%) but the absolute character consistency scores remain below larger models. At 8B, 5-shot exemplars are the most reliable lever; fine-tuning (LoRA on character dialogue data) would be more powerful but is outside the current scope.

---

## Sources (full URLs)

1. Examining Identity Drift in Conversations of LLM Agents — https://arxiv.org/abs/2412.00804  
2. SPASM: Stable Persona-driven Agent Simulation for Multi-turn Dialogue Generation — https://arxiv.org/abs/2604.09212  
3. FURINA: A Fully Customizable Role-Playing Benchmark via Scalable Multi-Agent Collaboration Pipeline — https://arxiv.org/abs/2510.06800  
4. FURINA OpenReview — https://openreview.net/forum?id=TjTuObGe27  
5. Persistent Personas? Role-Playing, Instruction Following, and Safety in Extended Interactions — https://arxiv.org/abs/2512.12775  
6. Enhancing Persona Consistency for LLMs' Role-Playing using Persona-Aware Contrastive Learning (PCL) — https://arxiv.org/abs/2503.17662  
7. ACL 2025 version (PCL) — https://aclanthology.org/2025.findings-acl.1344.pdf  
8. RAGs to Riches: RAG-like Few-shot Learning for Large Language Model Role-playing — https://arxiv.org/abs/2509.12168  
9. Thinking in Character: Advancing Role-Playing Agents with Role-Aware Reasoning (RAR) — https://arxiv.org/abs/2506.01748  
10. Guess What I am Thinking: A Benchmark for Inner Thought Reasoning of Role-Playing Language Agents (MIRROR) — https://arxiv.org/abs/2503.08193  
11. The Illusion of Role Separation: Hidden Shortcuts in LLM Role Learning — https://arxiv.org/abs/2505.00626  
12. Character as a Latent Variable in LLMs: Emergent Misalignment and Conditional Safety Failures — https://arxiv.org/abs/2601.23081  
13. When Roleplaying, Do Models Believe What They Say? — https://arxiv.org/abs/2606.11502  
14. Role-Playing Agents Driven by Large Language Models: Current Status, Challenges, and Future Trends — https://arxiv.org/abs/2601.10122  
15. Self-Transparency Failures in Expert-Persona LLMs: How Instruction-Following Overrides Honesty — https://arxiv.org/abs/2511.21569  
16. When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances — https://arxiv.org/abs/2311.10054  
17. The Prompt Report: A Systematic Survey of Prompt Engineering Techniques — https://arxiv.org/abs/2406.06608  
18. ERABAL: Enhancing Role-Playing Agents through Boundary-Aware Learning — https://arxiv.org/abs/2409.14710  
19. Talk Less, Call Right: Enhancing Role-Play LLM Agents with Automatic Prompt Optimization — https://arxiv.org/abs/2509.00482  
20. IHEval: Evaluating Language Models on Following the Instruction Hierarchy — https://arxiv.org/abs/2502.08745  
21. llama.cpp KV Cache Reuse Tutorial — https://github.com/ggml-org/llama.cpp/discussions/13606  
22. Qwen3-4B abliterated (PrivateLLM) — https://privatellm.app/blog/qwen3-4b-abliterated-uncensored-local-ai-for-roleplay-on-iphone-ipad-and-mac  
23. Benchmarking and Enhancing Long-Term Memory in LLMs — https://arxiv.org/abs/2510.27246  
24. Beyond Single-Turn: A Survey on Multi-Turn Interactions with LLMs — https://arxiv.org/abs/2504.04717  
25. A Closer Look at System Prompt Robustness — https://arxiv.org/abs/2502.12197  
