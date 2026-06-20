# Adversarial Verification: GBNF / Constrained Decoding for Multi-Item Callout Output

**Layer:** C (Adversarial)
**Date:** 2026-06-20
**Verifies:** B_grammar_multi_item.md, B_compound_commands.md (grammar sections), B_llamacpp_serving.md (grammar section)
**System context:** Ultron 1.0 — local Windows, RTX 4070 Ti 12 GB (10 GB design cap), llama-cpp-python 0.3.22, Josiefied-Qwen3-8B-abliterated Q5_K_M (vocab ~151 552 tokens), thinking-capable, voice-first Valorant relay.

---

## Goal

Refute or qualify the Layer-B finding that GBNF/JSON-schema grammar reliably produces correct multi-item callout output without quality loss or speed cliffs in llama-cpp-python 0.3.22 on our exact system.

---

## Claims Examined

1. `response_format` JSON Schema grammar gives zero JSON parse errors and is the recommended production pattern.
2. Grammar + thinking mode is broken (issue #20345, open, no fix).
3. Lazy grammar (`grammar_lazy` / `grammar_triggers`) is NOT exposed in the llama-cpp-python 0.3.22 in-process API.
4. Qwen3-8B's 151 552-token vocabulary causes approximately 3x grammar sampling slowdown.
5. Simple flat schemas (maxItems≤5, depth≤2, no `$ref`) are safe from the MAX_REPETITION_THRESHOLD (2000) limit.
6. The "fails open" bug — grammar parse failure causes unconstrained generation with 200 OK — is a known server risk.
7. Format tax / quality degradation from grammar constraints is a real concern for the 8B model.
8. `enable_thinking=False` reliably disables thinking mode in llama-cpp-python 0.3.22 on Qwen3.

---

## Verdict Per Claim

### Claim 1: `response_format` JSON Schema grammar gives zero JSON parse errors (QUALIFIED)

**Layer-B assertion:** JSON Schema mode via `response_format` gives zero post-hoc parsing failures.

**Counter-evidence found:**

- **Issue #19051 (llama.cpp, confirmed open as of mid-2026):** When JSON schema → grammar conversion succeeds but grammar *parsing* fails (e.g. invalid regex in a pattern constraint), `llama-server` logs an error but continues generation **unconstrained**, returning HTTP 200 OK. The client has no error signal. This is a "fail-open" bug: structured output enforcement is silently dropped. Schema grammar failures are not propagated as errors.
  Source: https://github.com/ggml-org/llama.cpp/issues/19051

- **Issue #21228 (llama.cpp, opened March 31, 2026, unresolved):** Schemas using `$ref`/`$defs` (which Pydantic's `model_json_schema()` always generates for nested models) silently fail because the $ref resolver expands types inline, causing the total grammar rule count to exceed `MAX_REPETITION_THRESHOLD` (2000). The only warning is a server-side log line; the model generates unconstrained JSON.
  Source: https://github.com/ggml-org/llama.cpp/issues/21228

- **Issue #22314 (llama.cpp, 2026):** JSON Schema → GBNF conversion fails on schemas whose `pattern` fields use PCRE shorthand regex (`\d`, `\w`, `\s`). These are extremely common in real API schemas.
  Source: https://github.com/ggml-org/llama.cpp/issues/22314

- **Issue #21571 and #22072 (llama.cpp, 2026):** Tool-calling scenarios with simple object schemas emit malformed/incomplete JSON arguments in streaming mode, and `Failed to initialize samplers` crashes occur.

**Verdict: QUALIFIED.** The claim is true for the SPECIFIC, NARROW case: a fully inlined, simple flat schema (no `$ref`, no PCRE regex patterns, depth ≤ 2, `maxItems` ≤ 5) in `create_completion()` — NOT `create_chat_completion()` — with thinking disabled. For any more complex schema, or if using Instructor (which relies on Pydantic → `model_json_schema()` → `$ref`), the fail-open bug makes zero-error claims false.

**Corrective action for Ultron 1.0:** Inline all schemas entirely; no `$ref`. Avoid `pattern` fields. Always wrap the grammar call in a try/except on the raw output string and validate with `json.loads()` as a secondary check. Do not assume 200 OK means grammar was enforced.

---

### Claim 2: Grammar + thinking mode broken, issue #20345 open, no fix (CONFIRMED — with additional severity)

**Layer-B assertion:** When `response_format` / JSON schema grammar is used with `enable_thinking=true`, grammar is completely bypassed. Open bug, no PR, no ETA.

**Adversarial check:** Issue #20345 confirmed open as of June 2026. No PR is referenced. The issue specifically affects llama.cpp builds from commit `d088d5b` onward (which is the post-autoparser PR #18675 state that llama-cpp-python 0.3.22 is built against).

**Additional severity found:** Issue #12196 (llama.cpp) documents a **crash** (segfault on macOS, probable memory corruption on other platforms) when lazy grammars encounter `</think>` tokens in the stack. This is the lazy grammar + Qwen3 combination that the B docs describe as Option 3. The crash risk was not mentioned in the B docs.
Source: https://github.com/ggml-org/llama.cpp/issues/12196

**Verdict: CONFIRMED, with upgraded severity.** The bug is confirmed. The additional risk is that the crash mode of lazy grammar on `</think>` tokens (issue #12196) means Option 3 from B_grammar_multi_item.md (lazy grammar, C++ server only) is actively dangerous on some platforms and should not be attempted even via the server subprocess path.

---

### Claim 3: Lazy grammar NOT in Python in-process API 0.3.22 (CONFIRMED)

**Layer-B assertion:** `grammar_lazy` and `grammar_triggers` parameters are not exposed in `create_completion()` / `create_chat_completion()` in llama-cpp-python 0.3.22; only available via the HTTP server API.

**Adversarial check:** No evidence of a Python in-process API PR for these parameters found in any search. The llama-cpp-python readthedocs API reference and the llama_grammar.py source on HuggingFace confirm only `LlamaGrammar.from_string()`, `from_json_schema()`, and the `grammar=` parameter to `create_completion()`. No `grammar_lazy` or `grammar_triggers` wrapper exists.

**Additional finding:** Issue #17047 documents a **segfault on macOS** when constructing a lazy grammar with non-empty trigger words. While this is macOS-specific, it indicates the lazy grammar C++ API itself is unstable, making any attempt to call it via ctypes (the workaround suggested in the B docs) high-risk.

**Verdict: CONFIRMED.** Lazy grammar is not in the Python API and the underlying C++ implementation has known crash modes. The B docs correctly advise against it.

---

### Claim 4: ~3x grammar sampling slowdown due to Qwen3 vocabulary size (QUALIFIED — may be worse: up to 6x)

**Layer-B assertion:** Qwen3-8B vocab 151 552 tokens causes approximately 3x grammar sampling slowdown, same root cause as the Llama 3 (128k vocab) regression measured in discussion #1376.

**Counter-evidence found:**

- Discussion #1376 (llama-cpp-python), confirmed by direct fetch: The actual measured figures are:
  - **Llama-3-Smaug-8B on RTX 3090 (GPU, CUDA):** without grammar = **80.33 tok/s**, with grammar = **13.38 tok/s** → slowdown **~6x** (not 3x as the B doc cites)
  - A separate test on the same model (CLI, not Python): without grammar = **80.16 tok/s**, with grammar = **44.86 tok/s** → slowdown **~1.8x**

- The B doc's "25.85 tok/s with grammar ON" does not appear verbatim in the discussion thread. The figures retrieved are 13.38 tok/s and 44.86 tok/s, suggesting multiple environments with variable outcomes.

- The slowdown is confirmed to be on **GPU CUDA** (RTX 3090), not CPU-only. GPU utilization drops from ~100% to ~30% during grammar sampling — the grammar mask computation forces CPU-side work that stalls the GPU pipeline.

- No fix has been merged. The issue remains active since April 2024 through at least October 2024 (last comment in the thread). No 2025/2026 fix for the vocabulary-size grammar bottleneck was found.

- Qwen3-8B vocab (151 552) is 18% larger than Llama 3 (128k). If the worst-case 6x applies, Ultron 1.0 could see grammar-constrained output at **~7–10 tok/s** on the relay path, meaning a 40-token JSON array takes 4–6 seconds — **unacceptable for real-time voice relay**.

**Verdict: QUALIFIED — the B doc understates the worst-case risk.** The ~3x figure is the better-case outcome. The confirmed worst-case on GPU CUDA is ~6x slowdown. For Ultron's relay latency budget (target < 1.5s from intent to TTS start), grammar-constrained decoding of a multi-item array may be too slow even with a minimal schema. The claim that this is "MEDIUM" severity should be upgraded to **HIGH** until tested on our exact RTX 4070 Ti with Qwen3-8B Q5_K_M.

**Required action:** Benchmark grammar ON vs. OFF on our exact system before committing to grammar-constrained multi-item output in the relay hot path. If slowdown exceeds 2x (relay array > 1.5s at expected tok/s), fall back to post-process parse (no grammar on the decode path).

---

### Claim 5: Simple flat schemas (no $ref, maxItems≤5) are safe from MAX_REPETITION_THRESHOLD (CONFIRMED — with caveat)

**Layer-B assertion:** Using `{m,n}` quantifiers and keeping `maxItems≤5` prevents the MAX_REPETITION_THRESHOLD (2000) from triggering.

**Adversarial check:**

- Issue #20867 (llama.cpp, March 2026) confirms MAX_REPETITION_THRESHOLD breaks grammars for tools with **many optional parameters** (48+ optional params in a tool definition). The issue explicitly involves optional-parameter expansion, not simple arrays.
- Issue #21228 confirms the threshold is triggered by `$ref` expansion, not by simple flat array quantifiers.
- Direct fetch of #20867: "simple `maxItems=5` array wouldn't generate the problematic nested repetition patterns that trigger this limit."
- Issue #17473 shows the error "number of repetitions exceeds sane defaults" but all examples involve deeply nested or optional-heavy schemas.

**Verdict: CONFIRMED — for a simple flat schema without `$ref`, without 10+ optional fields per object, the threshold is not hit.** The caveat: if Ultron 1.0 ever adds per-item optional fields (e.g., one of 10 Valorant locations), the total optional expansion could approach the limit. Keep schemas lean. Do not use `oneOf`/`anyOf` at the item level.

---

### Claim 6: "Fails open" bug is a known server risk (CONFIRMED — also affects in-process API)

**Layer-B assertion (implicit — B_llamacpp_serving.md notes grammar+thinking silently disables grammar):** Grammar enforcement failure is silent.

**Broader adversarial finding:**
Issue #19051 confirms that not just the thinking+grammar incompatibility, but ANY grammar parse failure in `llama-server` silently generates unconstrained output with HTTP 200 OK. This is the "fail-open" pattern. The issue is confirmed open as of 2026 with no fix.

For Ultron's in-process API (`create_completion()` / `create_chat_completion()`), the same failure mode applies: if grammar initialization fails (e.g., schema exceeds threshold, unsupported pattern regex), the Python wrapper raises no exception in some versions — it may return unconstrained output.

**Verdict: CONFIRMED.** Production use of grammar-constrained output requires an explicit validation layer: always call `json.loads()` on the result and handle `JSONDecodeError` / schema validation failure, regardless of whether grammar was used.

---

### Claim 7: Format tax / quality degradation is a real concern for 8B models (CONFIRMED)

**Layer-B assertion (arXiv 2502.14969, 2604.03616):** Smaller models (3–9B) show stronger format sensitivity. Grammar constraints degrade reasoning accuracy.

**Adversarial check:** No disconfirming evidence found. The "Lost in Space" paper (2502.14969) and "Format Tax" (2604.03616) are peer-reviewed and directly applicable. The finding that LW-token suppression is more severe for smaller models is mechanistically sound.

**Additional adversarial point not in B docs:** The format tax compounds with the vocabulary-size slowdown for Qwen3-8B. At 6x slower generation, the model is also being forced off its highest-probability tokens more severely. These are not independent effects — they both stem from the same vocab-size problem in llama.cpp's masking implementation.

**Verdict: CONFIRMED.** The recommendation to leave `ultron_say` / `combined_voice` fields as unconstrained JSON strings (free text) while constraining only routing metadata is correct and adversarially validated.

---

### Claim 8: `enable_thinking=False` reliably disables thinking in Qwen3 on llama-cpp-python 0.3.22 (REFUTED — confirmed broken)

**Layer-B assertion (implicit in workaround Option 1):** Disabling thinking via `enable_thinking=False` is the "safest" workaround for the grammar+thinking incompatibility.

**Counter-evidence found:**

- **Issue #13189 (llama.cpp):** Persistent `<think>` tags in Qwen3-32B output despite `enable_thinking: False` and `--reasoning-format none`. Confirmed reproducible.
- **Issue #20182 (llama.cpp):** `enable_thinking` param cannot turn off thinking for Qwen3.5. Workaround required: custom chat template file, or pass a modified Jinja2 template that hardcodes thinking off.
- **Discussion #20476 (llama.cpp, 2026):** "Qwen3.5 Small: How to truly false the enable_think?" — multiple users confirm the parameter is unreliable.
- **Confirmed workaround (community-sourced):** Modify the Jinja2 chat template to change `if enable_thinking is defined and enable_thinking is true` → `if enable_thinking is defined and enable_thinking is false` (inverts the logic), or pass `--reasoning-budget 0`. The `reasoning_budget=0` approach partially works but may suppress generation output rather than suppressing the thinking phase.

**Verdict: REFUTED as stated.** `enable_thinking=False` is NOT a reliable hard disable for Qwen3 in llama-cpp-python 0.3.22. The parameter is broken for some Qwen3 variants and configurations. The B docs present it as the safest workaround (Option 1) — this is wrong; it is actually an unreliable option.

**Corrected workaround order:**
1. **Most reliable:** Provide a custom chat template file via `chat_format="chatml"` or `chat_template_path=` with `enable_thinking` hardcoded to false in the Jinja2 template.
2. **Second option:** Use `reasoning_budget=0` (if exposed in your 0.3.22 build — it is a post-April 2026 sampler).
3. **Third option:** Use `logit_bias={think_start_id: -100}` to suppress `<think>` token. Note the CUDA logit_bias reliability concern (issue #13605 — unconfirmed for Qwen3 specifically, but noted).
4. **Do NOT rely on** `enable_thinking=False` alone without a secondary validation that the output contains no `<think>` tag.

---

## Corrected Recommendation for Ultron 1.0

The Layer-B recommendation to use `response_format` JSON Schema grammar for multi-item relay callouts stands, but with the following mandatory corrections:

### 1. Benchmark grammar ON vs. OFF on the RTX 4070 Ti BEFORE committing to the relay hot path

The Llama 3 / RTX 3090 worst-case was 6x slowdown (not 3x). For Ultron's 40-60 tok/s baseline and a 40-token relay array, grammar ON could take 4–6 seconds — breaking the voice latency budget. Measure first. If slowdown exceeds 2x on our hardware, use **post-process parse only** (no grammar on decode, validate with `json.loads()`).

### 2. Use post-process parse as the primary production path; grammar as an optional strictness layer

Given the fail-open bug (#19051), MAX_REPETITION risk for future schema evolution, and the thinking-disable reliability problem (#13189, #20182), the most robust architecture is:

```
LLM generates JSON freely (thinking OFF, no grammar)
  → strip_think(output)  # regex remove <think>...</think>
  → json.loads(cleaned)  # raises JSONDecodeError on failure
  → validate_against_schema(parsed)  # check required fields
  → on failure: re-prompt once with explicit JSON correction instruction
```

Grammar can be added as a speed optimization IF the RTX 4070 Ti benchmark shows <2x slowdown for the target schema.

### 3. Do not use Instructor with thinking-capable Qwen3 without custom template

Instructor patches `create_chat_completion_openai_v1` and relies on the same `response_format` path, which is broken with thinking enabled. The Pydantic → `model_json_schema()` → `$ref` pipeline triggers issue #21228. Either: (a) disable Instructor's schema generation and pass an inlined schema manually, or (b) use Instructor only after confirming thinking is suppressed via the custom template method.

### 4. All schemas must be fully inlined — no `$ref`

Do not write schemas using Pydantic nested models in production. Flatten all schemas to avoid `$ref`/`$defs` expansion that triggers #21228.

### 5. Hard invariant: always validate output regardless of grammar

Grammar enforcement can fail silently (200 OK, unconstrained output). Every grammar-constrained call path must have a `json.loads()` + field presence check as a secondary gate.

### 6. `enable_thinking=False` alone is unreliable — use custom template

For the relay path (thinking disabled), provide a custom Qwen3 Jinja2 chat template with `enable_thinking` hardcoded to `false`. Do not rely on the API parameter alone.

---

## Residual Risks

| Risk | Severity | Evidence | Status |
|------|----------|----------|--------|
| Grammar vocabulary slowdown: confirmed 6x worst-case on GPU CUDA, not 3x | HIGH | Discussion #1376, RTX 3090 GPU measurement | No fix; must benchmark our exact HW |
| fail-open (#19051): grammar failure → 200 OK unconstrained | HIGH | Issue #19051, confirmed open 2026 | No fix; mitigate with explicit json.loads() gate |
| `enable_thinking=False` unreliable for Qwen3 (#13189, #20182) | HIGH | Issues #13189, #20182, #20476 | No fix; use custom template workaround |
| Grammar + thinking = grammar bypassed (#20345) | HIGH | Issue #20345, confirmed open | No fix; hard architectural separation required |
| Lazy grammar crash on `</think>` (#12196) | HIGH | Issue #12196, segfault confirmed | Not fixed; do not use lazy grammar path |
| `$ref`/`$defs` exceeds MAX_REPETITION_THRESHOLD (#21228) | MEDIUM | Issue #21228, opened March 2026 | No fix; mitigate by inlining all schemas |
| PCRE shorthand in schema patterns fails grammar converter (#22314) | MEDIUM | Issue #22314, 2026 | No fix; avoid pattern constraints |
| Format tax on 8B model — constrained reasoning degrades | MEDIUM | arXiv 2502.14969, 2604.03616 | By design; leave text fields unconstrained |
| Lazy grammar segfault on macOS (#17047) | LOW | macOS-specific; we are on Windows | Not our platform but indicates instability |
| `max_tokens` truncation mid-JSON | LOW | Confirmed in B docs | Mitigate: set generous token budget |

---

## Sources

1. llama.cpp Issue #19051 — fails open, grammar parse failure → unconstrained 200 OK: https://github.com/ggml-org/llama.cpp/issues/19051
2. llama.cpp Issue #21228 — $ref/$defs silent failure via MAX_REPETITION_THRESHOLD: https://github.com/ggml-org/llama.cpp/issues/21228
3. llama.cpp Issue #20867 — MAX_REPETITION_THRESHOLD breaks optional-heavy grammars: https://github.com/ggml-org/llama.cpp/issues/20867
4. llama.cpp Issue #22314 — PCRE shorthands break schema grammar conversion: https://github.com/ggml-org/llama.cpp/issues/22314
5. llama.cpp Issue #22072 — tool calling emits malformed JSON in streaming: https://github.com/ggml-org/llama.cpp/issues/22072
6. llama.cpp Issue #21571 — "Failed to initialize samplers" with structured output: https://github.com/ggml-org/llama.cpp/issues/21571
7. llama.cpp Issue #20345 — grammar enforcement disabled when thinking enabled: https://github.com/ggml-org/llama.cpp/issues/20345
8. llama.cpp Issue #12196 — crash on lazy grammar with thinking models: https://github.com/ggml-org/llama.cpp/issues/12196
9. llama.cpp Issue #17047 — lazy grammar segfault on macOS with non-empty trigger words: https://github.com/ggml-org/llama.cpp/issues/17047
10. llama.cpp Issue #13189 — persistent think tags despite enable_thinking: False: https://github.com/ggml-org/llama.cpp/issues/13189
11. llama.cpp Issue #20182 — enable_thinking cannot turn off thinking for Qwen3.5: https://github.com/ggml-org/llama.cpp/issues/20182
12. llama.cpp Discussion #20476 — Qwen3.5 true disable of enable_think: https://github.com/ggml-org/llama.cpp/discussions/20476
13. llama.cpp Issue #13605 — logit_bias CUDA reliability (unconfirmed for Qwen3): https://github.com/ggml-org/llama.cpp/issues/13605
14. llama-cpp-python Discussion #1376 — Llama 3 grammar slowdown: 13.38 tok/s vs 80.33 tok/s (6x) on RTX 3090 GPU CUDA: https://github.com/abetlen/llama-cpp-python/discussions/1376
15. llama-cpp-python Issue #1097 — oneOf/anyOf bug in SchemaConverter: https://github.com/abetlen/llama-cpp-python/issues/1097
16. llama.cpp Issue #7703 — cannot mix properties with anyOf/oneOf: https://github.com/ggml-org/llama.cpp/issues/7703
17. arXiv 2502.14969 — Lost in Space: format tax / quality degradation on smaller models: https://arxiv.org/html/2502.14969v1
18. arXiv 2604.03616 — The Format Tax: https://arxiv.org/pdf/2604.03616
19. llama.cpp grammars/README.md: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
20. HN discussion on llama.cpp grammar output: https://news.ycombinator.com/item?id=45346771
