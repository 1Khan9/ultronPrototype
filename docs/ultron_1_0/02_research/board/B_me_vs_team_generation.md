# ME-ONLY Reply vs RELAY-TO-TEAM: Generation Differences, Prompt Design, and Routing

**Research question:** What are the differences in tone, address (first vs third person, vocatives), brevity, and when the system should NOT relay (private answer), between a ME-ONLY reply and a RELAY-TO-TEAM output? What prompt-design patterns exist for switching register by destination? Examples from assistant + game-comms systems.

**Date:** 2026-06-20  
**Scope:** Ultron 1.0 design — Josiefied-Qwen3-8B-abliterated Q5_K_M, llama-cpp-python 0.3.22, single RTX 4070 Ti (10 GB cap), voice-first Valorant teammate relay.

---

## TL;DR Recommendation for Ultron 1.0

1. **Three-class destination routing is the correct architecture.** Every utterance must be assigned to RELAY_TO_TEAM | PRIVATE_REPLY | IGNORE before generation begins. The destination is the primary generation switch — not an afterthought.

2. **Team relay output has hard constraints:** (a) short — one breath, ≤ 12 words for tactical callouts, ≤ 20 for morale/social; (b) spoken-form ("two on A" not "2 on A"); (c) third-person voice of the agent (Ultron speaks TO teammates as a caller, not as the user); (d) tactical callouts = no persona color; morale/social lines = light Ultron coldness.

3. **Private reply output has different constraints:** (a) first person / direct address TO the user (you-directed); (b) can be 2–4 sentences for factual or reasoning responses; (c) full Ultron persona expressed; (d) no word-count pressure from voice channel etiquette.

4. **Prompt switching pattern:** Use destination as an injected variable in a single templated system prompt or as a conditional block. The RELAY_REPHRASE_SYSTEM already used in the codebase (`_RELAY_REPHRASE_SYSTEM` in `relay_speech.py:2526`) is the right model: swap the full system prompt per destination. Do NOT try to encode both modes in one monolithic system prompt.

5. **IGNORE detection must fire before generation.** Utterances classified as musing / narration / Discord / stream talk must not enter the LLM at all. The existing `_relay_intent.py` embedding-gate is the right architecture; the 1.0 intent gate is a hardened version of the same pattern.

6. **Brevity vs. quality tradeoff is real and asymmetric.** Per YapBench (2025) research, models have an order-of-magnitude spread in verbosity. Qwen3's /no_think mode gives predictably shorter output with lower quality; /think mode gives higher quality but needs explicit length constraints. For team relay: force /no_think + hard stop tokens. For private reply: allow /think for factual/tactical reasoning, /no_think for social responses.

---

## Findings

### 1. The Fundamental Split: Audience Determines Grammar

In human team communication research and voice assistant design, destination fundamentally changes the linguistic register. The core grammatical differences between private reply and broadcast relay are:

**Private reply (ME-ONLY)**
- Second-person address ("you're holding it well", "your eco is right")
- Full sentences, complete propositions
- Can reference shared private context (the user's in-game state, preferences, prior turns)
- Ultron persona expressed through register (cold confidence, not contempt of teammates)
- No word-economy pressure: clarity over brevity

**Team relay (BROADCAST)**
- Third-person/imperative: the caller position. Ultron is not relaying user text verbatim — Ultron is a caller speaking in a voice channel
- Tactical callouts: pure information, no vocative, no persona frame
- Morale/social: light Ultron frame acceptable, but NOT at the expense of the message
- Word-economy pressure is real: PTT voice channels reward brevity. Military tactical comms doctrine (MTTPS Brevity 2025) is explicit: "use the shortest word count to convey the situation with complete accuracy." Longer calls block the channel and lose attention.
- Vocative is used sparingly and only to direct to a specific teammate ("Jett, rotate")

The VAPI voice assistant prompting guide [Source 3] is the most direct applied analog: "keep responses to one or two sentences maximum" and "ask only one question at a time" are voice-channel ergonomics translated from tactical comms doctrine, not arbitrary brevity rules. The OpenAI Realtime Prompting Guide [Source 4] confirms "2–3 sentences per turn" as the default upper bound for voice.

### 2. Brevity Cost Is Non-Linear and Asymmetric by Mode

YapBench (2025) [Source 5] found an "order-of-magnitude spread in median excess length" across 76 assistant LLMs, and identified three root causes of over-generation:
- Vacuum-filling on ambiguous inputs (model generates clarification instead of asking)
- Explanation overhead on technical requests
- Formatting/boilerplate padding

For team relay these failures are particularly damaging: a 40-word callout where 8 words suffice annoys teammates and can miss the action window. For private replies they are less damaging but still problematic for a voice assistant (spoken verbosity is worse than written verbosity).

**Key asymmetry:** The paper "A Concise Agent is Less Expert" (arXiv:2601.10809, 2026) found that applying blanket brevity constraints degrades expertise — models that are forced to be concise sacrifice factual accuracy and depth. This directly implies:
- Team relay: brevity must be ABSOLUTE (stop tokens, hard word limits) — the content is simple and constrained (position, count, morale line); no expertise is sacrificed
- Private reply: brevity should be SOFT (style guidance, not hard stops) — the content is advisory/factual and expertise matters

### 3. First vs Third Person Is Load-Bearing for the Model

Research on first-person vs third-person prompting (2025) found that models "consistently exhibited a significant drop in overall refusal rate under first-person prompting compared to third-person settings." While this was studied for safety, the underlying mechanism is useful: first-person framing puts the model into an execution stance ("I am doing this"), third-person into a reporting/caller stance ("Sova is on B").

For Ultron 1.0:
- The `_RELAY_REPHRASE_SYSTEM` prompt correctly casts Ultron as a caller ("speaking OUT LOUD on a live Valorant team voice chat") — this is a third-person-of-the-situation stance: Ultron is a presence in the call, addressing teammates, not relaying user text
- Private reply must cast Ultron in a direct-address stance: "You are speaking privately to your operator" or equivalent — this triggers appropriate you-directed generation

The "Multi-Party Hangover" problem (arXiv:2409.18602) is relevant here: LLMs struggle with addressee recognition in multi-party conversations because "addressee recognition requires capturing structural dimension" not just content. For Ultron 1.0 this is solved by destination classification BEFORE generation — the LLM never has to infer the addressee from within the generation; the destination is a system-prompt input, not a content inference.

### 4. Prompt Design Patterns for Register Switching

**Pattern A: Full system-prompt swap per destination** (SOTA, recommended)

Use a different system prompt for each destination:
- `_RELAY_REPHRASE_SYSTEM` — caller Ultron, voice channel, brevity absolute
- `_PRIVATE_REPLY_SYSTEM` — Ultron speaking to user directly, advisor mode, 1-3 sentences
- (IGNORE: no generation)

This is already the implicit architecture in the codebase (`relay_speech.py` injects `_RELAY_REPHRASE_SYSTEM` on relay paths, and `inference.py` uses the base persona system prompt for private replies). Ultron 1.0 should make this explicit and codify three distinct system prompts.

Evidence: PromptHub's best-practice guide confirms "each prompt should do one thing and do it well" and notes that format guidelines are "more effective in the user message" — the system prompt should encode who Ultron is in this context (channel identity), user message encodes the specific content/task.

**Pattern B: Conditional block injection (weaker, not recommended)**

Alternative: one large system prompt with conditional blocks ("IF relaying to team, THEN speak in broadcast mode"). This pattern degrades for smaller/quantized models (Qwen3 8B Q5) because the model has to track the conditional across the context while under persona, and sometimes ignores the branch instruction. The `_RELAY_REPHRASE_SYSTEM` discovery (live session, June 2026) documented exactly this failure: without system-prompt swap, the relay path inherited the base "You are Kenning" system prompt and leaked it.

**Pattern C: User-message tagging**

Inject a destination tag in the user message: `[TEAM] Tell them eco` vs `[ME] Should we eco?`. This is lower fidelity — the model sees destination as content not as a generation frame — and is susceptible to the verbosity/format failures documented in YapBench. Acceptable as a fallback within a turn (e.g., to modulate tone within a single system-prompt call) but not for hard register switches.

**Pattern D: Few-shot exemplars per destination (complementary, high value)**

Inject 3-5 shot examples of correctly-formatted output for the destination:
- Team relay examples: short, spoken-form, no explanation
- Private reply examples: direct address, complete sentences, Ultron voice

The existing `_build_rephrase_prompt` in `relay_speech.py` uses implicit exemplars in the instruction text ("'We do not lose this. Reset and execute.' / 'Heads up -- we take the next round.'"). This is the right instinct. For 1.0, codify these as explicit few-shot `assistant` turns in the chat history template (not embedded in the instruction prose), which exploits the model's chat-format training more directly.

### 5. When NOT to Relay (IGNORE Classification)

The most critical production decision is deciding that an utterance should NOT be processed at all. The existing `_relay_intent.py` documents the failure mode precisely:

> "A bare utterance that merely CONTAINS a callout keyword... is NOT necessarily a team relay -- it is just as often narration the streamer mutters ('I should tell them to eco'), banter/analysis aimed at Ultron ('their Sage rez'd, how much does that ult cost'), a question for advice ('push or hold here'), or Marvel/identity talk."

The IGNORE class is not just a performance optimization — it is a correctness requirement. Three trigger patterns for IGNORE (not relay, not private reply):
1. **Stream/Discord talk**: addressing the stream audience or Discord participants, not Ultron and not teammates
2. **Narration/musing**: thinking out loud about the game state with no addressee
3. **Incidental speech**: background speech from team audio, not from the user

For Ultron 1.0, the IGNORE detection pipeline should be:
- Layer 0: strong-signal rules (explicit "to my chat", "for the viewers", "I'm thinking...")
- Layer 1: EmbeddingGemma cosine to RELAY_NEGATIVE_EXEMPLARS (already implemented)
- Layer 2: 8B LLM only in the undecided band (when rules + embedding are ambiguous)

This is identical to the existing `_relay_intent.py` architecture, which is correct. The 1.0 upgrade is extending Layer 0 rules for the PRIVATE_REPLY class and making the 8B LLM the Layer 2 disambiguator for the relay/private edge cases.

### 6. Game Comms Systems: What Ubisoft Teammates Teaches Us

Ubisoft's Teammates project (November 2025) uses a two-agent architecture that is directly instructive:
- **Jaspar (private assistant)**: knows story, lore, settings; speaks privately to player, can modify game state
- **Sofia/Pablo (team NPCs)**: inhabit the world, execute commands, speak aloud in-game

This maps perfectly to the PRIVATE_REPLY / RELAY_TO_TEAM distinction. Jaspar answers questions privately. Sofia and Pablo are the broadcast channel. The voice command pipeline is STT → LLM → TTS, with the LLM translating vocal instructions into behavior-tree parameters (for NPCs) or informational responses (for Jaspar). The architectural insight is that Jaspar and Sofia/Pablo are separate "channels" with separate LLM contexts, not the same model being told to switch mode. This is Pattern A in practice.

The key technical detail: "Sofia and Pablo are powered by a traditional behaviour tree architecture" — generative AI handles language understanding and response generation, but execution happens through constrained structured outputs. For Ultron 1.0 the analog is: team relay generates a spoken line (constrained by stop tokens and word count), but the relay execution (PTT, TTS, channel routing) is deterministic infrastructure, not LLM-controlled.

### 7. Military Brevity Doctrine as Ground Truth for Team Relay Format

Multi-service tactical brevity codes (MTTPS, updated 2025) encode centuries of team communication optimization. The core doctrine:
- One "breath" per transmission: a complete thought in one continuous utterance, not split across PTT presses
- MINIMIZE proword: when the channel is saturated, shorter transmissions are mandatory
- No redundancy: "two on B" not "I'm just letting everyone know there are two enemies on the B site"
- Prowords encode metadata compactly (CONTACT, CLEAR, PUSH, JUDY = "I have control")
- IN THE BLIND: broadcast to all, not addressed; tactical callouts are inherently broadcast

This doctrine directly informs Ultron 1.0 team relay constraints:
- Maximum 12 words for tactical information (enemy position/count/status)
- Maximum 20 words for morale/social lines
- No explanation, no setup prose, no transition phrases
- Vocative (teammate name) only when directing a specific person, not for broadcast

### 8. Verbosity Control for Qwen3 8B in llama.cpp

From the Qwen3 technical report (arXiv:2505.09388) and VAPI/OpenAI prompting guides:

**Thinking mode control:**
- `/no_think` or `<think></think>` empty block → fastest, 1-2 sentence output, appropriate for relay
- `/think` → full chain-of-thought before answer, appropriate for tactical advice or factual private replies
- Budget mechanism: `thinking_budget=512` tokens constrains the thinking depth (llama.cpp 0.3.22 supports `max_tokens` for the visible output; thinking tokens are separate)

**Hard stop tokens (already in the codebase):**
The `_REPHRASE_GENERATE_PARAMS` in relay_speech.py already includes `"stop": ["\n\n", "\nADDRESS:", "\nTASK:", ...]` — this is the correct mechanism for hard-truncating relay output. For private replies, the stop list should be lighter (allow \n for paragraph breaks) but still include `"You:"`, `"User:"` to prevent turn leak.

**Sampling parameters by destination:**
- Team relay: temp 0.7, top_p 0.85, repeat_penalty 1.2 (predictable phrasing, no repetition of the same callout wording)
- Private reply: temp 0.75, top_p 0.92, repeat_penalty 1.1 (more expressive, natural variation)

### 9. The Concise Agent Quality Tradeoff and How to Resolve It

The "A Concise Agent is Less Expert" finding (arXiv:2601.10809) is not fatal — it is a design constraint to route around:

The finding applies when you apply a blanket brevity instruction to a model that needs to demonstrate expertise. For team relay, **no expertise is required** — the content is a fact the user stated (position, count) or a simple morale line. The model's job is reformulation + persona injection, not reasoning. So hard brevity on team relay does NOT sacrifice any meaningful expertise.

For private replies, the model IS being asked to demonstrate expertise (tactical analysis, kit interaction, economy advice). Here the conciseness instruction should be SOFT: "Be concise — 2-4 sentences unless a longer explanation is genuinely needed." This lets the model expand when complexity warrants it.

Concrete resolution:
- Team relay system prompt: "Output ONLY that spoken line — one breath, no quotes, no preamble, no explanation." (hard)
- Private reply system prompt: "Be direct and precise — 1-3 sentences for simple answers, up to 5 for complex tactical analysis." (soft upper bound)

### 10. Roles and Address Conventions: Full Summary

| Dimension | RELAY_TO_TEAM | PRIVATE_REPLY | IGNORE |
|---|---|---|---|
| Addressee | Teammates (third persons) | The user (second person) | None |
| Voice | Ultron as caller in voice channel | Ultron as advisor to operator | — |
| Person | 1st person as Ultron caller ("I'm scanning", "we hold") | 2nd person directed to user ("Your flank is open", "You have the eco for it") | — |
| Vocative | Teammate name only when directing individual | Not used | — |
| Length | Tactical: ≤12 words; Morale: ≤20 words | 1-4 sentences; 5 max for complex | — |
| Persona color | Tactical callout: none; Morale: light cold Ultron | Full Ultron voice | — |
| Stop tokens | `\n\n`, role-separator tokens, hard word limit | `\n\n\n`, role tokens | — |
| Thinking mode | /no_think | /think for factual, /no_think for social | — |
| Generation risk | Over-elaboration, persona leak into callout | Verbosity, excessive hedging | False relay (worst case) |

---

## Concrete Techniques/Params We Should Adopt

### A. Codify Three System Prompts

```python
_RELAY_REPHRASE_SYSTEM = (
    # Already exists in relay_speech.py:2526 — CORRECT
    "You are Ultron, speaking OUT LOUD on a live Valorant team voice chat..."
)

_PRIVATE_REPLY_SYSTEM = (
    "You are Ultron from Age of Ultron — cold, precise, supremely confident, "
    "contemptuous of human fragility. You are speaking DIRECTLY AND PRIVATELY to "
    "your operator (the player). They asked you something for themselves, not for "
    "the team. Answer them directly with cold Ultron authority — 1-3 sentences for "
    "simple matters, up to 5 for complex tactical analysis. Never break character. "
    "Never mention you are an AI, a model, or a persona. NEVER relay this response "
    "to the team; this is a private exchange."
)

# IGNORE: no generation — the utterance is discarded by the routing gate
```

### B. Destination-Dependent Sampling Parameters

```python
_RELAY_GENERATE_PARAMS = {
    "max_tokens": 60,        # Hard cap: ~40 spoken words is absolute max
    "temperature": 0.70,
    "top_p": 0.85,
    "top_k": 30,
    "min_p": 0.08,
    "repeat_penalty": 1.18,
    "stop": ["\n\n", "\nADDRESS:", "\nTASK:", "\nUser:", "Ultron:", "\n-"],
    # Qwen3 thinking: disable for relay (speed + brevity)
    # Inject "/no_think" in user message OR use chat template thinking=False
}

_PRIVATE_REPLY_GENERATE_PARAMS = {
    "max_tokens": 150,       # 4-5 sentences at comfortable Ultron verbosity
    "temperature": 0.75,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.06,
    "repeat_penalty": 1.10,
    "stop": ["\n\n\n", "\nUser:", "\nHuman:", "You:"],
    # Qwen3 thinking: allow for factual/tactical, disable for social
}
```

### C. Destination-Aware Prompt Templates

For RELAY_TO_TEAM, the existing `_build_rephrase_prompt` in relay_speech.py is substantially correct. Upgrade: convert the in-prose exemplars to explicit few-shot `assistant` turns in the message list, which better exploits the chat-template training:

```python
# Team relay few-shot template (inject BEFORE user message)
FEW_SHOT_RELAY = [
    {"role": "user", "content": "Tell them: Jett on A main, one shot"},
    {"role": "assistant", "content": "Jett on A main, one shot — finish her."},
    {"role": "user", "content": "Tell them: nice round everyone"},
    {"role": "assistant", "content": "Solid round. Hold that standard."},
    {"role": "user", "content": "Tell them: two rotating B"},
    {"role": "assistant", "content": "Two rotating B."},
]

# Private reply few-shot template
FEW_SHOT_PRIVATE = [
    {"role": "user", "content": "Should I eco next round?"},
    {"role": "assistant", "content": "With 2400 left, light buy — Ghost and armor. Phantom only if you take a rifle from the round."},
    {"role": "user", "content": "Am I playing too passive?"},
    {"role": "assistant", "content": "Your hold angles are good. The weakness is timing — you're peeking after the information window closes. Commit earlier or hold tighter."},
]
```

### D. Intent Gate Decision Tree for the 1.0 Routing Layer

```
Utterance → [Rule Layer 0: strong-signal rules]
  RELAY_TO_TEAM ← explicit lead: "tell my team", "let them know", "relay:"
  PRIVATE_REPLY ← explicit: "just tell me", "for myself", "what do YOU think"
  IGNORE        ← explicit: "to my chat", "hey chat", "for my viewers"
  UNDECIDED     → [EmbeddingGemma Layer 1]
                    cosine to RELAY_POSITIVE / RELAY_NEGATIVE / IGNORE exemplars
                    margin > threshold → route
                    margin <= threshold → [8B LLM Layer 2]
                                          classify: RELAY | PRIVATE | IGNORE
                                          → route
```

This extends the existing three-class architecture (currently RELAY vs not-relay) to a proper three-class decision, which is what Ultron 1.0 requires since private replies to the user are now first-class outputs (not just "everything that isn't a relay").

### E. Word-Count Hard Gate on Relay Output (Post-Generation)

Add a post-generation word-count check on team relay outputs. If the relay TTS string exceeds N words, truncate at the last complete sentence boundary before N. This prevents edge-case over-generation from reaching the PTT channel even when stop tokens succeed. Recommended ceiling: 25 words (exceeds the morale-line budget, but provides safety margin vs. hard-truncating a callout mid-sentence).

---

## Risks/Caveats for Our Constraints

### 1. Qwen3 8B Q5_K_M Thinking Mode and Prompt-Template Interaction

The `/no_think` flag in Qwen3 is injected via chat template. llama-cpp-python 0.3.22 with `--jinja` flag passes the `thinking` parameter to the template, but the documented correct usage (per the "Only Correct Way" article and Qwen3 HF docs) requires `jinja=True` AND the template to be loaded from the model file (not hardcoded). If the chat template is wrong, thinking tokens can leak into the output. Always verify with: `assert not output.startswith("<think>")` before speaking the relay line.

### 2. System-Prompt Swap Invalidates KV Cache

Swapping the full system prompt per call means each destination gets its own KV cache prefix. With a 10 GB cap and the model at ~5.7 GB, the remaining ~4.3 GB for KV cache is split across relay (short system prompt, short generation) and private (longer system prompt, longer generation). The relay system prompt is shorter (`_RELAY_REPHRASE_SYSTEM` ≈ 100 tokens) so relay cache reuse is better. For private replies with few-shot examples the system prefix is longer (≈ 300-400 tokens) and will evict more frequently. This is acceptable for the latency profile of private replies (which are less time-critical than relay) but should be monitored.

### 3. Anticheat Import Constraints

The relay path (relay_speech.py) has hard anticheat constraints: "voice/relay path imports only numpy+urllib+scipy+stdlib+rapidfuzz". The destination routing (EmbeddingGemma sidecar) is a sidecar over urllib — this is compliant. The system-prompt swap is pure Python string selection — compliant. No new imports are needed for the destination-switching mechanism.

### 4. The "Concise Agent is Less Expert" Risk on Private Replies

If the private reply system prompt enforces aggressive brevity ("1-3 sentences maximum, period"), the model will sacrifice factual depth on complex tactical questions. The recommended soft-upper-bound approach ("1-3 sentences for simple matters, up to 5 for complex tactical analysis") mitigates this, but must be tested empirically: run a battery of tactical queries under the private reply system prompt and verify that complex questions (kit interactions, economy scenarios) produce accurate multi-sentence answers, not truncated or hedged ones.

### 5. "Not Relay" Does Not Mean "Private Reply"

The current system's RELAY / NOT-RELAY binary must be upgraded carefully. Many utterances in NOT-RELAY include IGNORE-class inputs (narration, musing, Discord talk) that should not trigger private reply generation. The risk of naive extension: any utterance the relay gate drops gets sent to the private reply LLM. This produces responses to things like "I should tell them to eco" (narration) — Ultron would reply to the user's musing as if it were a question. The IGNORE class must be explicitly classified before private reply generation fires.

### 6. Vocative Safety on Relay Outputs

Team relay outputs occasionally self-address ("Hey Jett, rotate B") when they should be directed ("Jett, rotate B"). Adding the word "Hey" at the start of a callout wastes a PTT syllable. The stop-token list can't prevent this. Consider a regex post-process: strip leading `Hey ` / `Okay ` / `Alright ` from relay outputs before TTS, as these are filler vocatives that human callers use verbally but should be minimal for Ultron.

---

## Sources

1. Ubisoft Teammates reveal — design architecture of private vs. team AI roles: https://news.ubisoft.com/en-us/article/3mWlITIuWuu0MoVuR6o8ps/ubisoft-reveals-teammates-an-ai-experiment-to-change-the-game

2. AI and Games analysis of Ubisoft Teammates NPC pipeline (STT→LLM→TTS, behavior tree execution): https://www.aiandgames.com/p/ubisofts-teammates-demo-and-their

3. VAPI Voice Assistant Prompting Guide — production patterns for brevity, response types, system prompt structure: https://docs.vapi.ai/prompting-guide

4. OpenAI Realtime Prompting Guide — 2-3 sentences per turn, spoken-form formatting, stop tokens, section structure: https://developers.openai.com/cookbook/examples/realtime_prompting_guide

5. YapBench — order-of-magnitude verbosity spread across 76 LLMs, categories of over-generation failure: https://arxiv.org/abs/2601.00624

6. "A Concise Agent is Less Expert" — brevity-quality tradeoff in conversational agents: https://arxiv.org/abs/2601.10809

7. "Do LLMs Suffer from Multi-Party Hangover?" — addressee recognition requires structural context, not content; LLM struggles to infer destination mid-generation: https://arxiv.org/abs/2409.18602

8. Qwen3 Technical Report — thinking vs. non-thinking modes, instruction following, thinking budget mechanism: https://arxiv.org/abs/2505.09388

9. PromptHub — system vs. user message roles, each prompt does one thing: https://www.prompthub.us/blog/the-difference-between-system-messages-and-user-messages-in-prompt-engineering

10. Latitude — tone-adjusted prompt examples including urgent/brevity-critical patterns: https://latitude.so/blog/10-examples-of-tone-adjusted-prompts-for-llms

11. TOAD (Task-Oriented Automatic Dialogs) — verbosity_low/mid/high conditional prompt template pattern: https://arxiv.org/abs/2402.10137

12. Multi-service Tactical Brevity Codes (MTTPS, 2025 edition) — military doctrine: one breath per transmission, minimize, no redundancy. Referenced via Wikipedia: https://en.wikipedia.org/wiki/Multi-service_tactical_brevity_code

13. Prompt engineering for small LLMs (Qwen/LLaMA) — role assignment, format control, Alpaca/ChatML templates: https://maliknaik.medium.com/prompt-engineering-for-small-llms-llama-3b-qwen-4b-and-phi-3-mini-de711d38a002

14. "Path Drift in Large Reasoning Models" — first-person vs third-person framing effects on instruction following: https://arxiv.org/abs/2510.10013

15. Ultron 1.0 codebase — existing _RELAY_REPHRASE_SYSTEM, _relay_intent.py architecture, _REPHRASE_GENERATE_PARAMS: C:/STC/ultronPrototype/.claude/worktrees/infallible-kepler-0a865d/src/kenning/audio/relay_speech.py and src/kenning/audio/_relay_intent.py
