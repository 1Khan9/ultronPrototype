# Are there better local serving stacks than llama-cpp-python for an 8B with grammar + thinking on Windows/CUDA?

**Research date:** 2026-06-20
**System under evaluation:** Ultron 1.0 — Windows 11, RTX 4070 Ti (12 GB; 10 GB design cap), in-process voice pipeline, anticheat-safe import constraints, Josiefied-Qwen3-8B Q5_K_M via llama-cpp-python 0.3.22, grammar-constrained intent classification, thinking-mode enabled.

---

## TL;DR recommendation for Ultron 1.0

**Stay on llama-cpp-python. Do not switch.**

The alternatives all fail on at least one hard constraint:

| Constraint | llama-cpp-python | ExLlamaV2/V3 + TabbyAPI | vLLM | SGLang | MLC-LLM | TGI |
|---|---|---|---|---|---|---|
| Native Windows w/ CUDA, no Docker/WSL | YES | YES | Community fork only | No | YES (limited) | NO |
| In-process Python (anticheat: no heavy imports from relay path) | YES (load model once, call in-process) | NO (requires separate HTTP server process) | NO | NO | Partial | NO |
| Grammar/GBNF constrained decoding + JSON schema | YES (GBNF native; llguidance integration) | NO (no native grammar; lm-format-enforcer wrapper only, unmaintained) | YES (xgrammar/guidance) | YES (xgrammar) | Unknown | YES (deprecated) |
| Grammar + thinking mode simultaneously | BROKEN (issue #20345, March 2026) | N/A (no grammar at all) | Reportedly works | Reportedly works | Unknown | N/A |
| GGUF Q5_K_M model format (existing asset) | YES | NO (requires EXL2 re-quantization) | NO | NO | NO | NO |
| 10 GB VRAM hard cap | YES (full layer offload, KV compression) | YES | YES (but PagedAttention reserves more base overhead) | YES | YES | NO (Docker overhead) |
| Real-time single-user voice latency (not batch throughput) | Excellent (in-process, zero IPC overhead) | Good (loopback HTTP overhead) | Poor (batch-optimized) | Poor (batch-optimized) | Untested | N/A |

The single valid reason to switch would be raw token throughput, where ExLlamaV2 (EXL2 4.0bpw) is 1.6-2.2x faster than llama.cpp (Q4_K_M) on 13B benchmarks. For an 8B model at Q5_K_M on a RTX 4070 Ti with a single concurrent user, llama.cpp is already delivering 50-80 tok/s — fast enough that the voice relay TTS bottleneck (Kokoro generation time) dominates, not LLM decode. The switching cost (re-quantize the model, lose grammar, add an HTTP server subprocess, route around anticheat constraints) is not justified by the throughput gain in this architecture.

**The one actionable finding is a CRITICAL BUG to work around:** llama-cpp-python's grammar enforcement is completely broken when `enable_thinking=True` simultaneously (llama.cpp issue #20345, filed 2026-03-10, still open as of this writing). The intent classifier that runs with grammar-constrained JSON output MUST have thinking disabled, or must run a two-pass strategy (thinking pass unconstrained → structured-output pass with grammar). This is NOT a reason to switch stacks — vLLM/SGLang handle this combination, but at the cost of every other constraint.

---

## Findings (detailed)

### 1. llama-cpp-python 0.3.22 — current baseline

**Strengths for Ultron 1.0:**

- **In-process Python**: The model is loaded once at boot and called directly from Python via C-extension. Zero IPC, zero HTTP, zero subprocess overhead. For a voice pipeline where every millisecond of TTFT matters, this is the largest latency advantage no benchmark captures: no network stack, no serialization, no process startup.
- **GGUF format**: The existing Josiefied-Qwen3-8B Q5_K_M is already in GGUF format. Re-quantizing to EXL2 takes hours, requires a separate calibration dataset, and produces a format that only ExLlamaV2 can consume.
- **GBNF grammar**: Full native support for grammar-constrained decoding. JSON schema is auto-converted. BNF + regex-like features allow encoding intent routing output schemas precisely. llguidance (Microsoft Rust Earley parser, ~50 µs/token overhead) is now integrated.
- **Windows CUDA**: First-class support. Pre-built wheels on PyPI for CUDA 12.x. No community fork required.
- **Anticheat safety**: The relay speech path only imports numpy/scipy/stdlib/rapidfuzz. The model is loaded in the orchestrator which is a separate Python process from the relay path. llama-cpp-python's C extension loads `ggml_cuda.dll` — not a user-mode driver hook, not a kernel driver, not a process scanner. Safe.
- **KV cache quantization**: `--cache-type-k q8_0 --cache-type-v q8_0` reduces KV cache VRAM from ~2 GB (fp16) to ~1 GB for a 32K context window, staying well within the 10 GB cap.
- **Thinking mode via `/no_think`**: Qwen3 supports both `enable_thinking=True` (slow, deep) and `enable_thinking=False` (fast snap). llama.cpp supports `--reasoning-format deepseek` and `--reasoning-budget N` for thinking token budgeting.

**Critical bug: Grammar + Thinking mode conflict (llama.cpp issue #20345, filed 2026-03-10, unresolved)**

When `response_format` (JSON schema grammar) is active AND `enable_thinking=True`, grammar enforcement is completely inactive. Two failure modes:
- *Loud failure*: Model wraps JSON in markdown fences → 500 error from PEG parser
- *Silent failure*: Model produces bare JSON ignoring the requested schema

This means the intent classifier (which needs structured JSON output: `{intent: "RELAY"|"PRIVATE"|"IGNORE", confidence: float}`) CANNOT use thinking mode simultaneously. Options:
1. Run the intent gate with `enable_thinking=False` always (it uses rules + embeddings for the easy 90%, only needs LLM for the ambiguous band — thinking is less critical here)
2. Two-pass: thinking pass unconstrained → extract reasoning → structured-output pass without thinking
3. Wait for the bug fix (vLLM/SGLang reportedly handle this correctly — the fix pattern is known)

The pragmatic Ultron 1.0 recommendation: disable thinking for the intent gate, reserve thinking for the response-generation path. This costs nothing in practice because the intent gate is already cheap (rules → embeddings → LLM only for ambiguous band).

**Performance on RTX 4070 / 4070 Ti with 8B models:**

Official benchmark (llama.cpp GPU scoreboard, April 2026, Llama 2 7B Q4_0):
- RTX 4070 Ti SUPER, CUDA + FA: `pp512=7612 t/s`, `tg128=132 t/s`
- RTX 4070, CUDA + FA: `pp512=4293 t/s`, `tg128=91 t/s`

Flash Attention impact: ~10% gain on prompt processing (pp512), near-zero gain on decode throughput (tg128). FA is worth enabling via `-fa` flag but is not a dramatic uplift for decode-bound single-user inference.

Community reports for Qwen3 8B on RTX 4070 class hardware: 50-80 tok/s decode depending on Q-level and context fill. Q5_K_M sits at the higher end of quality/VRAM tradeoff vs Q4_K_M.

**Speculative decoding verdict for Qwen3 8B on single GPU:**

All benchmark results for Qwen3 family in llama.cpp show speculative decoding does NOT improve and often degrades performance on single consumer GPUs:
- RTX 3090 + Qwen3.6-35B-A3B: all 19 ngram/draft configurations slower than baseline (−13% to −60%)
- Root cause: for dense 8B models, each draft verification requires a full forward pass that burns more bandwidth than the draft saves; for MoE models, each drafted token activates a fresh expert slice
- The lone exception is Qwen 3.6 MTP (native multi-token-prediction heads baked into the model), which achieved ~30% improvement on RTX 4070 — but that's a different model architecture than the 8B dense Qwen3-instruct we're running

**Bottom line for baseline:** llama-cpp-python at current settings is already at or near the ceiling for single-user decode throughput on this hardware. The voice bottleneck is Kokoro TTS generation time, not LLM decode.

---

### 2. ExLlamaV2 / ExLlamaV3 + TabbyAPI

**What it is:** ExLlamaV2 is a custom CUDA inference library with hand-written kernels optimized for NVIDIA consumer GPUs. ExLlamaV3 (active development, v0.0.43 as of June 14, 2026) uses the EXL3 quantization format (a QTIP variant) capable of 1.6 bpw, enabling 70B models in 24 GB VRAM. TabbyAPI is the OpenAI-compatible HTTP server front-end.

**Performance advantage:**
- 13B benchmark (oobabooga, RTX 3090): EXL2 4.5bpw = 56.9 tok/s vs llama.cpp Q4_K_M = ~25-30 tok/s → **~2.2x faster**
- TabbyAPI/ExLlamaV2 RTX 4090, 8B EXL2 4.0bpw: **165 tok/s** vs llama.cpp Q4_K_M: ~130 tok/s → **~27% faster**
- The throughput advantage shrinks as models get smaller (8B vs 13B) and as the quality comparison is apples-to-oranges (EXL2 4.0bpw ≠ Q5_K_M in perplexity)

**Critical deficits for Ultron 1.0:**

1. **No grammar / constrained decoding**: ExLlamaV2 has no native support for grammar-constrained generation. The only community option is lm-format-enforcer (a token-filtering wrapper at the application layer), but that project is "not under active development recently" and has noted slowdowns when applied to ExLlamaV2. There is an open feature request for xgrammar integration (ExLlamaV2 issue #723) with no ETA.

2. **Requires a separate process (TabbyAPI HTTP server)**: Cannot be used in-process like llama-cpp-python. Every LLM call goes through a loopback HTTP round-trip. For voice relay where TTFT is critical, this adds latency. More critically, from an anticheat perspective, this means running an HTTP server process on a gaming machine — not inherently dangerous but adds complexity.

3. **EXL2/EXL3 format required**: The existing Josiefied-Qwen3-8B Q5_K_M GGUF cannot be used. Re-quantizing requires: downloading the base FP16 model, running exllamav2's `convert.py` with calibration data (several hours on GPU), storing the result. The abliterated fine-tuning (Josiefied weights) makes this more complex — standard calibration data may not preserve the abliteration characteristics.

4. **ExLlamaV3 is alpha**: As of June 2026, v0.0.43 with 1,096 commits. Active development but not production-stable. Grammar support: not documented. Qwen3 support: listed in architecture table, so model loads, but no evidence of Qwen3 thinking mode handling.

5. **Windows requirements**: ExLlamaV2 requires FlashAttention 2 for full performance, which on Windows requires CUDA 12.1+. A community fork (sdbds/exllamav2-for-windows) eases the setup. ExLlamaV3 requires `triton-windows` package. Both work on Windows but require more setup than llama-cpp-python's pre-built wheels.

**Verdict**: ExLlamaV2/V3 is the right choice if grammar is not needed and throughput is the only goal. For Ultron 1.0's grammar-gated intent classifier, it is not viable without a significant application-layer workaround that would likely negate the performance gain.

---

### 3. vLLM

**What it is:** UC Berkeley's batch inference engine, optimized for throughput via PagedAttention, continuous batching, and XGrammar structured output. The de facto standard for multi-user production LLM serving.

**Windows support status (June 2026):**
- **No official Windows support**. The official installation docs list Linux only.
- **Community fork (SystemPanic/vllm-windows)**: v0.20.0 released April 30, 2026. Supports CUDA 13, Python 3.12, RTX 4070 Ti (Ampere, compute cap 8.0+). First to add multi-GPU on Windows.
- **Another community build (aivrar/vllm-windows-build)**: v0.21.0 for Python 3.13, CUDA 12.8, RTX 50-series.
- **WSL2 path**: Official vLLM + WSL2; 20-40% performance overhead vs native due to GPU passthrough/Hyper-V.
- Community native Windows benchmarks claim "up to 40% higher throughput vs WSL2" — but this applies to server-class workloads, not single-user consumer hardware.

**Grammar / structured output:**
vLLM supports XGrammar (default as of March 2026) and `guidance` backends. XGrammar achieves <40 µs/token overhead for JSON schema enforcement. This is **better** than llama.cpp's GBNF/llguidance implementation in throughput-at-scale terms. Critically, vLLM reportedly handles `thinking=True` + structured output simultaneously (what llama.cpp bug #20345 fails at).

**Single-user latency vs. throughput:**
vLLM's design is fundamentally batch-throughput-optimized. PagedAttention and continuous batching maximize GPU utilization across many concurrent requests. For a single voice user:
- **TTFT**: vLLM 157ms vs llama.cpp 208ms (27B model bakeoff on RTX 5060 Ti pair) — vLLM wins on prefill
- **Decode ITL**: llama.cpp 49-175ms/token (variable) vs vLLM 64-67ms/token (very consistent)
- For a single-user voice assistant, llama.cpp is comparable or faster because vLLM's batching overhead adds latency on single requests
- vLLM's throughput advantage (3-4x at c=64 concurrency) is irrelevant for Ultron's single-user voice use case

**VRAM constraints:**
vLLM's PagedAttention reserves more base VRAM than llama.cpp's slot-based KV cache. On a 10 GB cap, this reduces headroom for context windows. In the 27B bakeoff, vLLM capped at 16K context while llama.cpp reached 43K context on the same hardware via KV quantization.

**Integration complexity:**
- Community fork required (not pip-installable from PyPI on Windows without patching)
- Python 3.12 or 3.13 required (if existing environment is 3.11, this is a breaking change)
- CUDA 13.0 recommended for the latest community builds (CUDA 12.x should still work for older versions)
- Runs as a separate server process — same anticheat concern as TabbyAPI but heavier footprint

**Verdict**: vLLM is the right tool for a multi-user cloud deployment or for solving the grammar+thinking bug at the cost of all other constraints. For Ultron 1.0 (single user, Windows native, in-process, anticheat, GGUF model, 10 GB cap), the switching cost and constraint violations make it non-viable.

---

### 4. SGLang

**What it is:** Structured generation + high-performance serving framework from the LMSys group. Key differentiator: RadixAttention (KV cache reuse across requests sharing prefixes) and native XGrammar integration for 3x faster JSON decode vs naive constrained sampling.

**Performance benchmarks (2026, H100 class):**
- SGLang: 16,215 tok/s vs vLLM: 12,553 tok/s → 29% throughput advantage
- SGLang TTFT: 79ms vs vLLM 103ms
- These numbers are on server-grade hardware at high concurrency — not directly applicable to RTX 4070 Ti single user

**Windows support:**
SGLang has **no official Windows support**. Installation requires Linux. No community Windows fork was found (unlike vLLM's SystemPanic fork). SGLang's custom CUDA kernels (sglang-kernel wheels) are built against specific CUDA versions and may not have Windows builds.

**Grammar / structured output:**
First-class. XGrammar default, regex constraint support. 3x faster JSON decoding via compressed finite state machine. Speculative decoding (DFlash, Spec V2 announced June 2026) integrated. Grammar + thinking: reportedly handled correctly.

**Consumer GPU:**
SGLang targets distributed serving (H100 clusters are the primary benchmark environment). Single-consumer-GPU documentation and community reports are sparse. It is functionally capable of running on a single RTX 4070 Ti but is under-optimized for that use case compared to ExLlamaV2 or llama.cpp.

**Verdict**: More powerful than vLLM for prefix-heavy workloads; same fundamental constraints apply. Not suitable for Ultron 1.0. Windows is a hard blocker.

---

### 5. TGI (Hugging Face Text Generation Inference)

**Status: DEPRECATED / MAINTENANCE MODE**

As of **March 21, 2026**, TGI entered maintenance mode and is now archived. The authoritative guidance from the Bizon-tech inference engine comparison (2026): "New projects should not start on TGI."

TGI was Docker-first, Linux-focused, and its structured output support was superseded by vLLM's XGrammar integration. Do not use.

---

### 6. MLC-LLM

**What it is:** TVM-based compilation framework that compiles model weights to platform-specific kernels (CUDA, Vulkan, WebGPU, Metal). Can run in-browser (WebLLM). Claims CUDA + Vulkan on Windows.

**Current state:**
- Active development (22.8k stars, Apache-2.0)
- Windows CUDA support advertised but community reports are sparse for RTX 4070 class
- Grammar / structured output: Not documented in accessible sources; no evidence of GBNF or XGrammar integration
- Model format: Requires MLC-compiled weights (not GGUF). Re-compiling the Josiefied GGUF to MLC format would require the original FP16 weights + MLC calibration

**Performance:**
MLC-LLM has shown competitive throughput on the same hardware as llama.cpp in some benchmarks (slight edge on some GPU-heavy models). However, for 8B models on RTX 4070 Ti, concrete comparative numbers are not available in the literature.

**Verdict**: The compilation-based approach is interesting but introduces fragility (kernel recompilation on driver updates, GPU driver quirks on Windows, no GGUF support). The lack of documented grammar/constrained output support is disqualifying. Not suitable for Ultron 1.0.

---

### 7. Speculative Decoding — is it worth enabling within llama-cpp-python?

The literature is clear for Qwen3-class models on single consumer GPU:

- **Dense 8B models (our case)**: No published benchmarks show net speedup with ngram or draft-model speculative decoding. The bandwidth cost of running the draft model + verification passes consumes the GPU memory bandwidth faster than the drafts save forward passes.
- **Exception**: Qwen 3.6 MTP architecture (multi-token-prediction heads embedded in the model weights) showed ~30% speedup on RTX 4070. But Qwen3-8B instruct (our model) does not have MTP heads.
- **Recommendation**: Do not enable speculative decoding for Josiefied-Qwen3-8B Q5_K_M. The baseline 50-80 tok/s is already ahead of TTS generation speed.

---

### 8. Competitive summary and recommendation matrix

| Framework | Windows Native | In-Process | Grammar | GGUF | 10GB OK | Anticheat | Single-User Latency |
|---|---|---|---|---|---|---|---|
| **llama-cpp-python** | YES | YES | YES (bug w/ thinking) | YES | YES | YES | Excellent |
| ExLlamaV2/V3 + TabbyAPI | YES (extra setup) | NO (HTTP) | NO | NO (EXL2 req) | YES | OK (separate process) | Good (HTTP overhead) |
| vLLM (community fork) | Community only | NO (HTTP) | YES (xgrammar) | NO | Tight | OK | Poor (batch-optimized) |
| SGLang | NO | NO (HTTP) | YES (xgrammar) | NO | YES | No (WSL) | Poor (batch-optimized) |
| MLC-LLM | Partial | Partial | Unknown | NO | YES | Unknown | Unknown |
| TGI | NO | NO | YES (deprecated) | NO | NO | No (Docker) | N/A (deprecated) |

---

## Concrete techniques/params we should adopt

1. **Fix the grammar+thinking conflict in our own pipeline** (don't wait for upstream fix): Run the intent classifier with `enable_thinking=False`. The gate uses rules → EmbeddingGemma → LLM-only-for-ambiguous, so thinking-mode depth is not needed for the binary `{RELAY, PRIVATE, IGNORE}` decision. Reserve `enable_thinking=True` for the response-generation path where grammar is not applied.

2. **Enable Flash Attention**: Add `-fa` to the llama-cpp-python init args (`n_gpu_layers=99, flash_attn=True`). ~10% prefill improvement on RTX 4070 Ti class hardware.

3. **KV cache quantization to shrink VRAM footprint**: `cache_type_k="q8_0", cache_type_v="q8_0"` halves KV cache VRAM, allowing either larger context or reserving headroom for the EmbeddingGemma sidecar.

4. **Do NOT enable speculative decoding**: No net gain for dense 8B on single consumer GPU with standard draft methods. Skip `-ngram-cache` and draft model options.

5. **Thinking budget for response path**: Use `--reasoning-budget 512` or programmatic budget injection in the system prompt to cap thinking token overflow. Voice relay responses don't need multi-thousand-token reasoning chains; 256-512 thinking tokens is sufficient for most Ultron responses.

6. **Monitor llama.cpp issue #20345**: If the grammar+thinking fix lands upstream and is pulled into llama-cpp-python, we can re-enable thinking for the intent gate. Track the PR that addresses the issue (xgrammar integration for the llama.cpp server was identified as the fix pattern by vLLM/SGLang's successful handling).

7. **For future model format**: If we ever hit a performance ceiling that actually matters (i.e., Kokoro TTS is no longer the bottleneck), ExLlamaV2/V3 re-quantization is the right path — but only after abandoning the grammar requirement or after xgrammar lands in ExLlamaV2. EXL2 4.0bpw ≈ Q4_K_M in quality while being ~27% faster on RTX 4090; the quality difference vs Q5_K_M is real and should be benchmarked on Valorant relay outputs before committing.

---

## Risks/caveats for our constraints

1. **Grammar+thinking bug is the most pressing risk** in the current stack. If Ultron 1.0 requires the intent classifier to use thinking-mode AND output structured JSON, the current llama-cpp-python is broken for that combination. Mitigation: separate the two paths as described above.

2. **ExLlamaV2/V3 grammar gap may close**: If xgrammar integration lands in ExLlamaV2 (open issue #723), the case for switching gets stronger. Watch that issue. If it lands before Ultron 1.0 ships, re-evaluate — but the in-process vs HTTP-server constraint remains.

3. **vLLM community Windows fork stability**: The SystemPanic fork is not official. API-breaking changes in vLLM upstream may take weeks to propagate. If we were already on vLLM, this would be a maintenance concern.

4. **CUDA 13 requirement for latest vLLM builds**: The RTX 4070 Ti supports CUDA 12.x; some of the newest vLLM builds target CUDA 13.0 which may require driver updates that interact with anticheat (VALORANT's vanguard does monitor certain driver-level changes).

5. **TGI is dead** — any documentation or blog posts recommending TGI predate its March 2026 archival. Ignore all TGI suggestions.

6. **Speculative decoding vendor claims vs. benchmarks**: Marketing materials claim 2-5x speedups. Real benchmarks on single-consumer-GPU Qwen3 models show zero gain or regression. Discount vendor claims; trust the RTX 3090/Qwen3.6 benchmark data.

7. **MLC-LLM fragility**: MLC's compilation approach means each new llama.cpp or CUDA driver version may invalidate compiled kernels, requiring a recompile. This is operational overhead incompatible with a gaming machine that receives driver updates frequently.

8. **ExLlamaV3 alpha status**: 0.0.43 as of June 2026 means the API and format may change. Early adopters of EXL3 format risk needing to re-quantize as the spec evolves.

---

## Sources

- [ExLlamaV2: The Fastest Library to Run LLMs | Towards Data Science](https://towardsdatascience.com/exllamav2-the-fastest-library-to-run-llms-32aeda294d26/)
- [ExLlamaV2 + TabbyAPI: Best INT4 Inference Single GPU (2026) | Local AI Master](https://localaimaster.com/blog/exllamav2-tabbyapi-guide)
- [turboderp-org/exllamav2 — GitHub](https://github.com/turboderp-org/exllamav2)
- [turboderp-org/exllamav3 — GitHub](https://github.com/turboderp-org/exllamav3)
- [Grammar enforcement not applied when thinking is enabled · Issue #20345 · ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/issues/20345)
- [llama.cpp GPU Benchmark Scoreboard (CUDA/ROCm/Vulkan, pp512/tg128/FA) | knightli.com, April 2026](https://knightli.com/en/2026/04/23/llama-cpp-gpu-benchmark-cuda-rocm-vulkan-scoreboard/)
- [Tested every llama.cpp speculative-decode mode on Qwen3.6-35B-A3B + RTX 3090 | HackMD](https://hackmd.io/ODXuOQNzSiyUITz7g9mtBw)
- [qwen3.6-speculative-decoding-rtx3090 — GitHub benchmark repository](https://github.com/thc1006/qwen3.6-speculative-decoding-rtx3090)
- [SGLang vs vLLM: Complete LLM Inference Engine Comparison 2026 | Local AI Master](https://localaimaster.com/blog/sglang-vs-vllm-comparison)
- [LLM Inference Servers Compared — vLLM, SGLang, llama.cpp, Ollama | TensorFoundry](https://tensorfoundry.io/blog/llm-inference-servers-compared)
- [vLLM on Windows in 2026: what officially works, what doesn't | fazm.ai](https://fazm.ai/t/vllm-windows-support-2026)
- [Run vLLM natively on Windows without WSL | dasroot.net, May 2026](https://dasroot.net/posts/2026/05/run-vllm-natively-windows-without-wsl/)
- [SystemPanic/vllm-windows — GitHub community fork](https://github.com/SystemPanic/vllm-windows)
- [vLLM, Ollama, LM Studio, llama.cpp: Choosing the best LLM inference engine in 2026 | BIZON](https://bizon-tech.com/blog/best-llm-inference-engines)
- [We ran Qwen3.6-27B on $800 of consumer GPUs: llama.cpp vs vLLM bakeoff | LLMKube](https://llmkube.com/blog/qwen3-6-27b-bakeoff)
- [Qwen3 llama.cpp documentation | qwen.readthedocs.io](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html)
- [llama.cpp grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- [lm-format-enforcer ExLlamaV2 integration notebook | noamgat/lm-format-enforcer](https://github.com/noamgat/lm-format-enforcer/blob/main/samples/colab_exllamav2_integration.ipynb)
- [XGrammar: Flexible and Efficient Structured Generation (MLSys 2025) | arXiv 2411.15100](https://arxiv.org/pdf/2411.15100)
- [XGrammar-2 paper | arXiv 2601.04426](https://arxiv.org/pdf/2601.04426)
- [Detailed quantization comparison: GPTQ, AWQ, EXL2, Q4_K_M | oobabooga blog](https://oobabooga.github.io/blog/posts/gptq-awq-exl2-llamacpp/)
- [TabbyAPI FAQ | theroyallab/tabbyAPI Wiki](https://github.com/theroyallab/tabbyAPI/wiki/05.-FAQ)
- [SGLang GitHub](https://github.com/sgl-project/sglang)
- [XGrammar: Flexible and Efficient Structured Generation Feature Request for ExLlamaV2 | Issue #723](https://github.com/turboderp-org/exllamav2/issues/723)
- [Text Generation Inference (deprecated) | Hugging Face](https://huggingface.co/docs/text-generation-inference/en/index)
- [mlc-ai/mlc-llm — GitHub](https://github.com/mlc-ai/mlc-llm)
