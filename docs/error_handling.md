# Ultron error handling


> **Currency note (2026-05-22):** this document is a historical snapshot.
> For the **current** state (DualSTTRegistry, Kokoro TTS, qwen3.5-4b,
> intent recognizer, supervisor stack, news-category SearxNG routing,
> gaming-mode VRAM reclaim, event bus, OPEN_LAST_SOURCE / NAVIGATE_TO_SITE
> intents, etc.), see [`codebase_structure.md`](codebase_structure.md)
> which is kept current via the binding maintenance contract. The
> high-level shape and intent here are still accurate; specific subsystem
> identities and per-knob defaults have evolved.

Phase 4 of the Foundation phase. Single source for: what fails, how
we detect it, how we degrade, and how the user finds out.

## Principles

1. **No silent failures.** If Ultron can't do what was asked, the user
   knows. The system never returns plausible-looking-but-wrong output.
2. **Typed errors.** Every external dependency raises a typed
   `UltronError` subclass. Callers branch on type, not message text.
3. **Structured error log.** `logs/errors.jsonl` records every
   dependency failure as one JSON object per line: timestamp,
   dependency, error type, context, recovery taken, optional traceback.
4. **Circuit breakers for failure-prone APIs.** Three failures in five
   minutes trips Brave OPEN; calls fail fast for 5 minutes; then a
   single probe decides. Same shape for Jina (looser thresholds because
   degradation is cheaper).
5. **Voice-character error phrases.** `config.error_phrases.<mode>`
   defines pools of one-line user-facing messages. Empty pool silences
   narration for that failure mode (the error still logs).

## Type hierarchy ([src/ultron/errors.py](../src/ultron/errors.py))

```
UltronError
├── DependencyUnavailableError
│   ├── BraveAPIError
│   ├── JinaReaderError
│   ├── QdrantUnavailableError
│   ├── AnthropicAPIError
│   ├── OllamaUnavailableError       (declared; not used by voice pipeline)
│   └── OpenClawGatewayError         (anticipated; Part 5+)
├── ClaudeCodeError
├── AudioPipelineError
│   ├── WhisperTranscriptionError
│   ├── PiperSynthesisError
│   ├── RVCConversionError
│   ├── WakeWordModelError
│   └── AddressingClassifierError
├── MCPServerError
├── ConfigurationError
└── FilesystemError
```

Each error carries:
- `message`: short human-readable summary
- `context`: dict of diagnostic key/value pairs (NEVER include secrets)
- `recovery`: one-line description of the fallback the wrapper took
- `traceback`: optional, attached at log time

## Per-dependency catalog

### Brave Search API ([src/ultron/web_search/brave.py](../src/ultron/web_search/brave.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Timeout (per-call > 8 s) | `requests.Timeout` | `[]` returned, base knowledge fallback | `brave_api` |
| 4xx / 5xx HTTP | `HTTPError` | `[]` + log status code | `brave_api` |
| 429 rate limit | `HTTPError(status=429)` | `[]` + log; circuit breaker counts | `brave_api` |
| Malformed JSON | `ValueError` | `[]` + log | `brave_api` |
| Connection refused | `ConnectionError` | `[]` + log | `brave_api` |
| Circuit breaker OPEN | `CircuitOpenError` | `[]` + log; no API call made | `brave_api` |

Circuit breaker: 3 failures / 5 min window → OPEN; 5 min cooldown; HALF_OPEN
probe; success closes. Threshold tighter than Jina because Brave costs
money per call.

User-facing voice (config.error_phrases.brave_unavailable): "Search isn't
working right now." / "I can't reach the web search service."

### Jina Reader ([src/ultron/web_search/jina.py](../src/ultron/web_search/jina.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Timeout (15 s) | `requests.Timeout` | `None` returned, snippet-only | `jina` |
| 4xx | `HTTPError(status=4xx)` | `None`, snippet-only | `jina` |
| 5xx | `HTTPError(status=5xx)` | `None`, snippet-only | `jina` |
| Connection error | `ConnectionError` | `None`, snippet-only | `jina` |
| Circuit OPEN | `CircuitOpenError` | `None` + log, no fetch | `jina` |

Circuit breaker: 5 failures / 5 min window → OPEN; 3 min cooldown.
Looser than Brave because losing Jina is non-fatal — we keep Brave
snippets, the answer is just less detailed.

User-facing voice: "I got search results but couldn't read the full pages."

### Qdrant ([src/ultron/memory/qdrant_store.py](../src/ultron/memory/qdrant_store.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Query embedding error (FastEmbed runtime) | catch-all | `[]` + log | `qdrant_embedder` |
| `query_points` runtime error | catch-all | `[]` + log | `qdrant` |
| Missing collection at startup | thrown by `_ensure_collections` | bubbles up at startup; user sees init error | `qdrant` (manual) |

No circuit breaker — Qdrant is embedded (in-process), so failures are
typically corruption / disk issues, not transient network problems. A
breaker doesn't add value for an in-process dependency.

User-facing voice: "Memory's not responding right now." / "I can't reach
my long-term memory at the moment."

### Whisper ([src/ultron/transcription/whisper_engine.py](../src/ultron/transcription/whisper_engine.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| `transcribe()` raises (CUDA OOM, model corrupt, etc.) | catch-all | `""` returned; orchestrator skips this turn | `whisper` |
| Empty audio | length check | `""` returned (not an error) | n/a |

No circuit breaker — Whisper is in-process. The orchestrator's
repeated-failure detection is what surfaces "Speech recognition is having
trouble." after 3+ consecutive failures (currently TODO; the phrase
exists in config but the counter wiring lives in the orchestrator and
is part of the unfinished migration).

### Piper TTS ([src/ultron/tts/speech.py](../src/ultron/tts/speech.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| `synthesize_wav` raises | catch-all in `_piper_synth` | empty int16 array returned | `piper_tts` |
| `synthesize` raises (older API) | catch-all in `_piper_synth` | empty int16 array returned | `piper_tts` |

When Piper returns empty PCM, the orchestrator's `_speak()` does
nothing audible. Recovery suggested: caller falls back to `print()` to
the terminal so the user sees the response. (Wiring lives in the
orchestrator; documented as the contract.)

### RVC ([src/ultron/tts/speech.py](../src/ultron/tts/speech.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| `rvc.convert(...)` raises | catch-all in `_synthesize` | raw Piper PCM returned (no Ultron filter) | `rvc` |

User-facing voice: "Voice conversion is offline. You'll hear me without
the Ultron filter for now."

### Addressing classifier ([src/ultron/addressing/classifier.py](../src/ultron/addressing/classifier.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Zero-shot model raises | catch-all | `default_silent` → NOT_ADDRESSED; else → UNCERTAIN | `addressing_zero_shot` |

Recent-turns provider failures are caught silently and treated as "no
context"; that's not an error, just degraded input.

User-facing voice (in pool but not auto-spoken): "Addressing detection
is degraded; I'll respond to everything for now."

### Configuration ([src/ultron/config.py](../src/ultron/config.py))

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Missing config.yaml | path check | raise `ConfigurationError` (startup fails loud) | n/a (raised, not logged) |
| Invalid YAML | `yaml.YAMLError` | raise `ConfigurationError` | n/a |
| OSError reading file | `OSError` | raise `ConfigurationError` | n/a |
| Schema validation fails (`extra="forbid"`, range constraints) | pydantic `ValidationError` | raise `ConfigurationError` | n/a |
| Env var reference unset | n/a | resolves to `""` (consumer handles) | n/a |

Config errors fail loud at startup — the system does NOT proceed with
a partial config. `error_phrases.config_invalid` is defined for
completeness but practically unreachable (voice stack isn't loaded
when config errors are caught).

### MCP server (anticipated, not yet wrapped)

When the MCP server crashes during a coding session:

1. Active sessions transition to FAILED.
2. Orchestrator narrates: "Lost connection to the coding orchestrator.
   The current task can't continue."
3. Document auto-restart on next startup.

Wiring lives in the coding cluster (still going through the Phase 3
shim — see [phase3_5_followup.md](phase3_5_followup.md)). The
`MCPServerError` type and the phrase exist; the orchestrator-level
wiring lands when the coding cluster migrates.

### Claude Code subprocess (anticipated)

| Failure mode | Detection | Recovery | Log dependency |
|---|---|---|---|
| Nonzero exit | subprocess `returncode != 0` | capture stderr; narrate via `claude_code_subprocess_failed` phrase; ask retry/abandon | `claude_code` |
| Hang (> task_timeout_seconds) | wait timeout | kill subprocess; narrate; ask retry/abandon | `claude_code` |
| Malformed stream-json | parse error | capture last-good event; narrate | `claude_code` |
| Anthropic API 4xx/5xx (visible to subprocess) | subprocess error | wrapped as `AnthropicAPIError`; narrate "Anthropic's API isn't responding." | `anthropic_api` |

Wired in [direct_bridge.py](../src/ultron/coding/direct_bridge.py) (still
going through Phase 3 shim).

## Resilience primitives

### Circuit breaker ([src/ultron/resilience/circuit_breaker.py](../src/ultron/resilience/circuit_breaker.py))

Standard three-state breaker with rolling failure window. Per-dependency
configuration via the `expected_exceptions` tuple — only those types
count as failures, so a programming bug doesn't trip the breaker.

```python
from ultron.resilience import CircuitBreaker

breaker = CircuitBreaker(
    name="my_service",
    failure_threshold=3,
    window_seconds=300,
    cooldown_seconds=300,
    expected_exceptions=(MyServiceError,),
)
result = breaker.call(my_func, args, kwargs)
# Raises CircuitOpenError if circuit is OPEN; propagates MyServiceError otherwise.
```

States: CLOSED → (threshold failures) → OPEN → (cooldown) → HALF_OPEN →
(probe success → CLOSED; probe failure → OPEN).

### Error log ([src/ultron/resilience/error_log.py](../src/ultron/resilience/error_log.py))

```python
from ultron.errors import BraveAPIError
from ultron.resilience import get_error_log

err = BraveAPIError("rate limited", context={"query": q})
err.with_recovery("fell back to base knowledge with caveat")
get_error_log().record(err, dependency="brave_api")
```

Best-effort append to `logs/errors.jsonl`. Never raises — write
failures log to the in-process logger only. Singleton; tests inject a
tmp-path log via `set_error_log()`.

Sample log entry:

```json
{
  "timestamp": "2026-05-08T05:42:11.392Z",
  "monotonic": 1234.567,
  "dependency": "brave_api",
  "session_id": null,
  "error_type": "BraveAPIError",
  "message": "Brave HTTP 503",
  "context": {"query": "what's the latest", "status_code": 503},
  "recovery": "returned empty results; caller falls back to base knowledge",
  "traceback": "Traceback (most recent call last):..."
}
```

### Phrase library ([src/ultron/resilience/phrases.py](../src/ultron/resilience/phrases.py))

```python
from ultron.resilience import phrase_for

msg = phrase_for("brave_unavailable")
if msg:
    speak(msg)
```

Backed by `config.error_phrases.<mode>`. Shuffled non-repeating cycles
per failure mode. Returns `None` when the pool is empty (operator
silenced narration for that mode).

## Tests ([tests/error_recovery/](../tests/error_recovery))

52 tests covering:

| File | Coverage |
|---|---|
| [test_brave_failures.py](../tests/error_recovery/test_brave_failures.py) | timeout / 5xx / 429 / malformed JSON; circuit OPEN; HALF_OPEN→CLOSED; HALF_OPEN→OPEN |
| [test_jina_failures.py](../tests/error_recovery/test_jina_failures.py) | timeout / 404 / 5xx / connection error; subsequent call works |
| [test_qdrant_failures.py](../tests/error_recovery/test_qdrant_failures.py) | embedding failure / search failure; subsequent retrieve works |
| [test_audio_failures.py](../tests/error_recovery/test_audio_failures.py) | Whisper transcribe / Piper synth / RVC convert failures |
| [test_addressing_failures.py](../tests/error_recovery/test_addressing_failures.py) | zero-shot raises; default-silent vs default-loud fallbacks |
| [test_config_failures.py](../tests/error_recovery/test_config_failures.py) | missing file / invalid YAML / unknown key / out-of-range / unset env var |
| [test_circuit_breaker.py](../tests/error_recovery/test_circuit_breaker.py) | breaker primitive: states, threshold, window, cooldown, exception filtering |
| [test_error_log.py](../tests/error_recovery/test_error_log.py) | error log writer + phrase library |

Each test verifies: system doesn't crash, errors.jsonl records the
failure with the right shape, recovery happens, subsequent operations
continue normally.

## Out of scope for Phase 4

- **MCP server failure narration** — wiring lives in the coding cluster
  which is still going through the Phase 3 shim. Phase 3.5 followup.
- **Claude Code subprocess error narration** — same; the bridge in
  [direct_bridge.py](../src/ultron/coding/direct_bridge.py) catches
  failures but the user-facing phrase wiring is part of the coding
  cluster migration.
- **Whisper repeated-failure counter** — phrase exists; wiring lives in
  the orchestrator's transcription path. The `whisper_repeated_failures`
  phrase will be hooked up when the orchestrator's STT block migrates.
- **Wake-word model failure phrase** — phrase exists; the wake-word
  module would emit on load failure but currently that path is not
  instrumented. Lands with the wake-word migration in Phase 3.5.

These are documented here so the next session has a clear punch-list.
The infrastructure (typed errors, breaker, error log, phrase library)
is in place; the remaining work is wiring it into already-migrated call
sites and the still-shimmed ones.
