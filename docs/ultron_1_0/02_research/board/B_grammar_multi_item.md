# Constrained Decoding / GBNF / JSON-Schema Grammars for Multi-Item Structured Output

**Research layer:** Frontier  
**Date:** 2026-06-20  
**System context:** Ultron 1.0 — local Windows, RTX 4070 Ti 12 GB (10 GB design cap), llama-cpp-python 0.3.22, Josiefied-Qwen3-8B Q5_K_M (vocab 151 552 tokens), thinking-capable, voice-first Valorant relay.

---

## TL;DR recommendation for Ultron 1.0

**Use `response_format` JSON Schema mode (NOT raw grammar strings) for multi-item structured output, but ONLY when thinking is OFF.** When thinking is ON, grammar enforcement is currently broken in llama.cpp (open issue #20345, March 2026 — no fix yet). The recommended production pattern for Ultron 1.0 is:

1. **Non-thinking path** (fast snaps, relay parsing): `response_format={"type":"json_object","schema":{...}}` in `create_chat_completion()`. This gives you a typed JSON object or array with zero prompt-engineering brittleness.
2. **Thinking path** (complex multi-step reasoning): Disable thinking (`enable_thinking=false` via chat template kwarg), then apply JSON Schema grammar. Alternatively, strip the `<think>...</think>` block from the raw completion in post-processing and parse the remainder.
3. **The lazy grammar / trigger pattern** exists in llama.cpp C++ but is NOT reliably exposed through llama-cpp-python 0.3.x in-process API; treat it as experimental.
4. **For the "free-text persona + structured callout list" hybrid**: emit JSON exclusively; move the Ultron persona voice to a system prompt that shapes the text *inside* the JSON fields (e.g., `"reply": "Three back rotating, initiating countermeasures."`). Do NOT try to mix raw free-text with JSON in one token stream under a grammar — this is the canonical footgun.
5. **Qwen3-8B's 151 552-token vocabulary causes a ~3x grammar sampling slowdown** in llama.cpp's current masking implementation. This is the same root cause as the Llama 3 regression (Llama 3 = 128 k vocab, Qwen3 = 152 k). Mitigation: keep schemas small (few required fields, no deeply nested objects), use `top_k=20` (recommended by Qwen3 anyway) which limits the candidate set the grammar must filter.

---

## Findings

### 1. How GBNF / constrained decoding works in llama.cpp

Grammar-constrained decoding in llama.cpp works at the **sampling step**, not at generation/attention time. After the model produces a logit vector over the full vocabulary, the sampler:

1. Calls `llama_grammar_apply_impl()` which maintains a set of active **parsing stacks** (vectors of rule element pointers).
2. For every candidate token, tests whether it can extend any active stack.
3. **Sets probability to 0 (logit to -inf)** for tokens that cannot continue a valid parse.
4. Accepts the sampled token via `llama_grammar_accept_token()`, advancing all stacks.

The grammar is written in **GBNF** (GGML Backus-Naur Form) — a BNF variant with regex-like quantifiers (`*`, `+`, `?`, `{m,n}`), character ranges (`[a-z]`, `[^\n]`), Unicode escapes, and direct token matching (`<think>`, `<[1000]>`). The mandatory entry point is the `root` rule.

Source: [DeepWiki: Grammar and Structured Output in llama.cpp](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output), [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

---

### 2. JSON Schema → GBNF automatic conversion

llama.cpp ships a `json_schema_to_grammar.py` converter (C++ port also available) that handles a substantial subset of JSON Schema Draft 7:

**Supported:**
- Types: string, number, integer, boolean, null, array, object
- String: `minLength`, `maxLength`, `pattern` (must be anchored `^...$`)
- Numeric: `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` (integers only)
- Array: `minItems`, `maxItems` (via `{m,n}` GBNF repetition)
- Object: `properties`, `required`, `additionalProperties` (defaults to false)
- Combinators: `oneOf`, `anyOf`, `allOf`
- Enums, `$ref` (single-level)

**Known broken/unsupported:**
- Nested `$ref`s (issue #8073)
- Cannot mix `properties` with `anyOf`/`oneOf` (issue #7703)
- `prefixItems` broken; use `items` instead
- `uniqueItems`, `contains`, `$anchor`, `not`, `if`/`then`/`else` unsupported
- Remote `$ref`s unsupported in C++ (Python version works)

**In llama-cpp-python**, the two clean paths are:
```python
# Path A: raw GBNF string
from llama_cpp import LlamaGrammar
grammar = LlamaGrammar.from_string(gbnf_string)
output = llm.create_completion(prompt, grammar=grammar)

# Path B: JSON schema (recommended for arrays/objects)
output = llm.create_chat_completion(
    messages=[...],
    response_format={
        "type": "json_object",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "location": {"type": "string"},
                    "reply": {"type": "string"}
                },
                "required": ["target", "location", "reply"]
            },
            "minItems": 1,
            "maxItems": 5
        }
    }
)
```

The schema is NOT injected into the prompt; it only constrains sampling. You must describe the expected structure in the system prompt yourself.

Sources: [Simon Willison's TIL on llama-cpp-python grammars](https://til.simonwillison.net/llms/llama-cpp-python-grammars), [DeepWiki llama-cpp-python grammar](https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation), [llama-cpp-python readthedocs](https://llama-cpp-python.readthedocs.io/)

---

### 3. Multi-item structured output: arrays and lists

A list of callouts → single combined response is the exact Ultron 1.0 use case. Three grammar patterns:

**Pattern A — JSON array of objects (recommended)**
```
root ::= "[" space item ("," space item)* "]" space
item ::= "{" space
         "\"target\"" space ":" space string "," space
         "\"location\"" space ":" space string "," space
         "\"reply\"" space ":" space string
         "}" space
string ::= "\"" ([^"\\] | "\\" .)* "\""
space ::= [ \t\n]*
```
Or generate automatically via JSON Schema as shown in §2.

**Pattern B — Markdown bulleted list (built-in `LIST_GBNF`)**
```python
from llama_cpp import LIST_GBNF
grammar = LlamaGrammar.from_string(LIST_GBNF)
```
This is good for quick enumeration but gives untyped strings — you'd need to parse each line. For Ultron relay callouts (structured slots), Pattern A is better.

**Pattern C — Mixed: thin wrapper JSON with a free-text field**
```json
{
  "type": "object",
  "properties": {
    "callouts": {
      "type": "array",
      "items": {"type": "object", "properties": {
        "agent": {"type": "string"},
        "info": {"type": "string"},
        "ultron_say": {"type": "string"}
      }, "required": ["agent", "info", "ultron_say"]}
    },
    "ultron_response": {"type": "string"}
  },
  "required": ["callouts", "ultron_response"]
}
```
Here `ultron_say` and `ultron_response` are free-text string fields. The grammar enforces valid JSON but the *content* of those strings is unconstrained (persona-style). This is the recommended hybrid for Ultron 1.0 — structure the relay routing metadata, free-text the voice lines.

**Performance note on arrays:** The `build_repetition()` function converts `minItems`/`maxItems` to `{m,n}` repetition syntax. Using `x? x? x? x? x?` style is catastrophically slow — always use `{m,n}` or let the schema converter do it.

---

### 4. Speed overhead: the vocabulary size problem

**Hard numbers from production:**
- Llama 3 8B (vocab 128k): grammar ON = **25.85 tok/s** vs grammar OFF = **80.33 tok/s** — roughly **3x slowdown**. Sample time per token 0.54ms → 74.76ms (138x increase in sampling overhead, masked by generation).
- The root cause: llama.cpp's grammar engine checks the **entire vocabulary** per token to build the mask, which does not scale with vocabulary size.
- Qwen3-8B vocabulary = **151 552 tokens** — roughly 18% larger than Llama 3's 128k. Expect a comparable or slightly worse 3x overhead.

**XGrammar comparison (2024, MLSys 2025):**
XGrammar pre-computes context-independent token masks (~99% of vocab for JSON grammars) during the prompt prefill phase, leaving only ~1% context-dependent tokens to validate per step. It achieves **<40 µs per-token masking** vs llama.cpp's dynamic approach. End-to-end speedup on H100: **up to 80x**. XGrammar is integrated into TVM/MLC and vLLM but NOT into llama-cpp-python as of June 2026.

**Practical mitigation for Ultron 1.0:**
- Keep schemas minimal: 3–5 fields per item, arrays capped at `maxItems=5`.
- Use `top_k=20` (already the Qwen3 recommended setting). This doesn't reduce grammar checking but limits the logit sort overhead.
- Use grammar only on the final structured output call; don't apply it to the full thinking path.
- If 3x slowdown is unacceptable (relay latency budget), consider post-processing: let the model output JSON freely in the prompt, then validate/repair with a Python JSON parser and re-prompt only on failure.

Sources: [Discussion #1376 llama-cpp-python Llama 3 grammar slowdown](https://github.com/abetlen/llama-cpp-python/discussions/1376), [XGrammar paper (arXiv 2411.15100)](https://arxiv.org/html/2411.15100)

---

### 5. Quality degradation: the format tax

**"Lost in Space" (arXiv 2502.14969) — key findings:**
- Grammar forces the model off its highest-probability tokens. The bias is introduced by whitespace/tokenization mismatches: leading-whitespace (LW) and non-LW token variants have cosine similarity of only 0.369–0.386.
- LW tokens appear 2.5–2.7x more frequently in pre-training, so non-LW-constrained grammars systematically suppress the model's most natural choices.
- **Smaller models (3–9B) show stronger format sensitivity** — critical for Ultron's 8B Qwen3.
- Recommendation: include leading whitespace tokens in grammar rules, e.g., start string values with `(" " | "\n")` to allow the model's preferred preamble tokens.

**"Format Tax" (arXiv 2604.03616) — key findings:**
- Structured format constraints (JSON, XML, strict schema) degrade reasoning accuracy measurably even for large models.
- More restrictive grammars → higher tax. Arrays of objects with many required fields are higher cost than simple `{"reply": "..."}` wrappers.
- Recommendation: **make schema fields optional where possible** (`additionalProperties` or nullable types) unless you truly require the field for routing logic.

**"AdapTrack: Constrained Decoding without Distorting LLM's Output Intent" (arXiv 2510.17376):**
- Documents that hard masking to zero causes semantic drift when high-probability tokens are blocked.
- SOTA mitigation (not yet in llama.cpp): soft constraint projection rather than hard masking.

**For Ultron 1.0:** The format tax is a real concern for the Ultron persona voice quality. The recommendation is to constrain only the routing/metadata fields tightly (agent name enum, location string) and leave the `ultron_say` / `response` field as an unconstrained JSON string. The grammar still enforces valid JSON structure while allowing free persona expression in the string content.

Sources: [arXiv 2502.14969](https://arxiv.org/pdf/2502.14969), [arXiv 2604.03616](https://arxiv.org/pdf/2604.03616), [arXiv 2510.17376](https://arxiv.org/pdf/2510.17376)

---

### 6. Thinking mode + grammar: BROKEN in llama.cpp (as of 2026-06-20)

**Issue #20345 (opened March 10, 2026, OPEN, no PR):**
When `response_format` / JSON schema grammar is used with `enable_thinking: true`, grammar constraints are completely bypassed. Two failure modes:
- Qwen3.5-35B: wraps JSON in markdown fences → PEG parser rejection (500 error)
- Qwen3-VL-8B: generates wrong schema fields without grammar blocking deviation

**Why it breaks:** The grammar sampler is not currently applied during the `<think>...</think>` phase, and the transition from think block to structured output is not triggering the lazy grammar activation correctly.

**vLLM and SGLang** both support grammar with reasoning models (issue #20345 notes this). They implement the "think freely, then constrain" pattern via lazy/deferred grammar activation.

**PR #18675 (autoparser)** was merged February 2026 and refactored the parser architecture, but the issue reporter confirms it did NOT resolve the grammar+thinking incompatibility.

**Workarounds:**

Option 1 (safest for Ultron 1.0): **Disable thinking**
```python
llm = Llama(
    model_path="qwen3-8b.gguf",
    chat_format="qwen3",
    # In the call:
)
output = llm.create_chat_completion(
    messages=[...],
    chat_format_kwargs={"enable_thinking": False},  # or via chat_template_kwargs
    response_format={"type": "json_object", "schema": schema}
)
```
Or pass a modified Jinja2 chat template file with `enable_thinking=False` hardcoded.

Option 2: **Post-process strip**: Let thinking run free (no grammar), then extract the JSON blob from after the `</think>` token in post-processing with a regex or streaming parser, and validate with Python `json.loads()`. Re-prompt on failure (rare with well-instructed Qwen3).

Option 3 (experimental — C++ only, not Python): Use lazy grammar with `grammar_lazy: true` and `grammar_triggers: [{"word": "</think>", "at_start": false}]`. This activates the GBNF grammar only after the `</think>` token. The grammar's `root` rule should begin with `</think>`. This works from the llama-server JSON API but is NOT exposed in llama-cpp-python in-process `create_completion()` as of 0.3.22.

Sources: [Issue #20345](https://github.com/ggml-org/llama.cpp/issues/20345), [Discussion #12110 lazy grammars](https://github.com/ggml-org/llama.cpp/discussions/12110), [Qwen docs llama.cpp](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html)

---

### 7. Lazy grammar: mechanism and current state

The lazy grammar mechanism (added ~late 2024, referenced in issue #12110 and the DeepWiki article) allows a grammar to stay dormant until a **trigger token sequence** appears in the model output:

```json
{
  "grammar": "root ::= </think> json-object",
  "grammar_lazy": true,
  "grammar_triggers": [{"word": "</think>", "at_start": false}]
}
```

Before the trigger, the sampler runs unconstrained. After the trigger fires, all subsequent tokens are constrained by the grammar. The `trigger_buffer` replays buffered tokens so the grammar parser receives the trigger token as part of the stream.

**Key limitation:** No "anti-trigger" — once constrained, you cannot return to free generation within the same request. This is fine for think→JSON but prevents interleaving (think→JSON→more-think).

**Current Python API status in llama-cpp-python 0.3.22:** The `grammar_triggers` and `grammar_lazy` parameters are NOT exposed in the `create_completion()` or `create_chat_completion()` Python API. They exist only in the llama-server HTTP API. To use lazy grammar in-process you would need to either:
a) Call `_lib.llama_sampler_init_grammar_lazy()` via ctypes directly (fragile, undocumented)
b) Spawn llama-server as a subprocess and hit the HTTP API (adds latency but fully supported)
c) Wait for llama-cpp-python to expose this parameter (no open PR for it as of 2026-06-20)

**Recommendation for Ultron 1.0:** Do not rely on lazy grammar via the Python in-process API for 1.0. Post-process strip (Option 2 above) is simpler, equally correct, and anticheat-safe.

Sources: [Discussion #12110](https://github.com/ggml-org/llama.cpp/discussions/12110), [DeepWiki grammar article](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output), [Autoparser docs](https://github.com/Mintplex-Labs/prism-ml-llama.cpp/blob/prism/docs/autoparser.md)

---

### 8. The "think freely then emit structured JSON" pattern (best practice 2025–2026)

The research literature converges on a clear winner for quality + structure:

**"In-Writing" framework (arXiv 2601.07525):** Unconstrained reasoning until a trigger token (`</think>` or `<eos>`), then grammar-constrained structured output. Tested on LLaMA 3-8B: **up to 27% accuracy gain** over vanilla constrained decoding. Achieves 100% format validity without sacrificing reasoning expressiveness.

**Why this matters for Ultron 1.0:** Qwen3-8B's thinking mode is its primary quality lever for complex multi-callout relay synthesis. Constraining the thinking phase with grammar would degrade reasoning quality. The correct pattern is:

```
<|im_start|>system
You are Ultron. When asked to relay multiple callouts, output ONLY valid JSON...
<|im_end|>
<|im_start|>user
[3 callouts: Jett B-main, Sage window, Reyna heaven]
<|im_end|>
<|im_start|>assistant
<think>
[unconstrained reasoning — Ultron plans the combined relay message]
</think>
{"callouts": [...], "ultron_response": "Three hostiles detected..."}
```

In llama-cpp-python 0.3.22 in-process: trigger thinking OFF, emit the JSON block, validate. Or trigger thinking ON, strip the `<think>...</think>` block from the raw output string, parse the remainder as JSON.

**Concrete implementation (post-process strip):**
```python
import re, json

def parse_qwen3_structured(raw: str, schema: dict) -> dict:
    # Strip thinking block
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # First JSON object or array in remaining text
    match = re.search(r'(\{.*\}|\[.*\])', cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in output: {raw[:200]}")
    return json.loads(match.group(1))
```

Sources: [arXiv 2601.07525 "Thinking Before Constraining"](https://arxiv.org/html/2601.07525), [DeepWiki grammar](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output)

---

### 9. Instructor library as an alternative integration layer

[Instructor](https://python.useinstructor.com/integrations/llama-cpp-python/) patches `create_chat_completion_openai_v1` to return validated Pydantic models:

```python
import instructor
from pydantic import BaseModel
from typing import List

class Callout(BaseModel):
    agent: str
    info: str
    ultron_say: str

class RelayResponse(BaseModel):
    callouts: List[Callout]
    ultron_response: str

create = instructor.patch(
    create=llm.create_chat_completion_openai_v1,
    mode=instructor.Mode.JSON_SCHEMA,
)
result: RelayResponse = create(
    messages=[...],
    response_model=RelayResponse,
    max_retries=2,  # auto-retry on validation failure
)
```

This is cleaner than manual GBNF string writing. The `max_retries=2` gives automatic retry with error context (Instructor sends the JSON parse error back to the model). Works with llama-cpp-python's OpenAI-compatible in-process API.

**Caveat:** Instructor uses `Mode.JSON_SCHEMA` which routes through `response_format`, same underlying grammar mechanism — so the thinking+grammar bug still applies. With thinking OFF or post-process strip, Instructor is a strong choice.

---

### 10. Anticheat / import safety

Grammar-constrained decoding is entirely in-process within llama.cpp's C++ backend. Python-side it's a single parameter to `create_completion()`. No new imports, no network calls, no heavy ML dependencies in the relay path. The `LlamaGrammar` class is part of `llama_cpp` which is already loaded in the LLM inference process (the sidecar). **Anticheat risk: zero** — this is compute configuration, not any kind of injection or external tool.

The Instructor library adds `instructor` as a dependency (pure Python, no native extensions), which is safe. The Pydantic dependency is already likely present.

---

## Concrete techniques / params we should adopt

1. **Schema design for relay callouts:**
```json
{
  "type": "object",
  "properties": {
    "relays": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "agent": {"type": "string"},
          "location": {"type": "string"},
          "status": {"type": "string"},
          "ultron_say": {"type": "string"}
        },
        "required": ["agent", "ultron_say"],
        "additionalProperties": false
      },
      "minItems": 1,
      "maxItems": 6
    },
    "combined_voice": {"type": "string"}
  },
  "required": ["relays", "combined_voice"]
}
```
`agent` + `ultron_say` required; `location` + `status` optional (reduces format tax). `combined_voice` is the single TTS string Ultron speaks aloud. The `relays` array feeds the team relay routing logic.

2. **Thinking mode OFF for grammar path** (fastest + most reliable in 0.3.22):
```python
# In create_chat_completion, add thinking-off token to system prompt
# or use chat_format_kwargs if exposed. Fallback: prepend /no_think to user message.
```
Qwen3 respects `/no_think` prepended to the user message as a soft switch even when `enable_thinking` is not directly exposed.

3. **Post-process strip for thinking ON path:**
```python
THINK_RE = re.compile(r'<think>.*?</think>\s*', re.DOTALL)
def strip_think(text: str) -> str:
    return THINK_RE.sub('', text).strip()
```

4. **GBNF performance — always use `{m,n}` syntax**, never chain `x? x? x?`. The schema converter does this correctly; only applies if writing raw GBNF by hand.

5. **Whitespace in grammar rules** — include a `space ::= (" " | "\n" | "\t")*` rule and use it between elements. This keeps leading-whitespace tokens available for the model's preferred sampling path, reducing the format tax.

6. **Top-k=20** (Qwen3's own recommendation). While this doesn't eliminate grammar overhead, it keeps the candidate set small and is the correct sampling regime for Qwen3 thinking mode.

7. **Instructor + Pydantic** for complex multi-item schemas with auto-retry. The `max_retries=2` pattern handles rare JSON truncation (max_tokens exhaustion) cleanly.

8. **Schema must be described in the system prompt** — llama.cpp does NOT inject the schema into the prompt automatically. Include a JSON example or field descriptions in `<|im_start|>system`.

---

## Risks / caveats for our constraints

| Risk | Severity | Detail |
|------|----------|--------|
| Thinking + grammar incompatible (issue #20345) | HIGH | Open bug, no ETA. Workaround: disable thinking or post-process strip. |
| Qwen3 vocab 151 552 → ~3x grammar sampling overhead | MEDIUM | Measured ~3x on Llama 3 (128k vocab). Qwen3 is 18% larger. Relay latency budget may be tight. Mitigation: minimal schema, top_k=20. |
| Format tax on reasoning quality | MEDIUM | Constraining the 8B model degrades semantic quality. Keep free-text fields unconstrained (just JSON string type). |
| lazy grammar not in Python in-process API | MEDIUM | Only available via llama-server HTTP. If needed, spawn server subprocess or wait for llama-cpp-python PR. |
| max_tokens truncation of JSON mid-output | LOW | Grammar ensures valid incremental JSON but can't ensure completion before token budget. Always set `max_tokens` generously for the expected output size; use streaming + early-stop on `]` or `}`. |
| `$ref` nesting broken in C++ converter | LOW | Workaround: inline all schemas; avoid `$ref` for now. |
| `additionalProperties: true` may emit unescaped newlines | LOW | Keep `additionalProperties: false` (default). |
| Instructor dependency added | NEGLIGIBLE | Pure Python, anticheat-clean, small package. |
| Token matching (`<think>`) in grammar requires single-token match | LOW | Qwen3's `<think>` and `</think>` are single tokens in its tokenizer. Test before relying on this. |

---

## Sources

Full URLs for all primary sources consulted:

1. [DeepWiki: Grammar and Structured Output in llama.cpp](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output)
2. [DeepWiki: Grammar-Based Generation in llama-cpp-python](https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation)
3. [llama.cpp grammars/README.md (official)](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
4. [Simon Willison's TIL: Using llama-cpp-python grammars to generate JSON](https://til.simonwillison.net/llms/llama-cpp-python-grammars)
5. [Structured outputs with llama-cpp-python — Instructor library](https://python.useinstructor.com/integrations/llama-cpp-python/)
6. [arXiv 2502.14969: Lost in Space — Finding the Right Tokens for Structured Output](https://arxiv.org/html/2502.14969v1)
7. [arXiv 2604.03616: The Format Tax](https://arxiv.org/pdf/2604.03616)
8. [arXiv 2510.17376: AdapTrack — Constrained Decoding without Distorting LLM's Output Intent](https://arxiv.org/pdf/2510.17376)
9. [arXiv 2601.07525: Thinking Before Constraining — Unified Decoding Framework](https://arxiv.org/html/2601.07525)
10. [arXiv 2411.15100: XGrammar — Flexible and Efficient Structured Generation Engine](https://arxiv.org/html/2411.15100)
11. [GitHub issue #20345: Grammar enforcement not applied when thinking is enabled](https://github.com/ggml-org/llama.cpp/issues/20345)
12. [GitHub Discussion #12110: How to use lazy grammars?](https://github.com/ggml-org/llama.cpp/discussions/12110)
13. [GitHub Discussion #1376: Llama 3 much slower with grammar](https://github.com/abetlen/llama-cpp-python/discussions/1376)
14. [Autoparser PR #18675 — complete refactoring of parser architecture](https://github.com/ggml-org/llama.cpp/pull/18675)
15. [Prism fork autoparser.md documentation](https://github.com/Mintplex-Labs/prism-ml-llama.cpp/blob/prism/docs/autoparser.md)
16. [Qwen docs: Running Qwen3 locally with llama.cpp](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html)
17. [arXiv 2502.05111: Flexible and Efficient Grammar-Constrained Decoding](https://arxiv.org/pdf/2502.05111)
18. [arXiv 2506.03887: Pre^3 — Deterministic Pushdown Automata for Faster Structured LLM Generation](https://arxiv.org/pdf/2506.03887)
19. [llama-cpp-python readthedocs (Getting Started)](https://llama-cpp-python.readthedocs.io/)
20. [Medium: Testing out llama.cpp grammar constraint based sampling](https://medium.com/better-programming/testing-out-llama-cpp-grammar-constraint-based-sampling-f154e48e6028)
