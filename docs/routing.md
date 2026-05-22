# Capability routing


> **Currency note (2026-05-22):** this document is a historical snapshot.
> For the **current** state (DualSTTRegistry, Kokoro TTS, qwen3.5-4b,
> intent recognizer, supervisor stack, news-category SearxNG routing,
> gaming-mode VRAM reclaim, event bus, OPEN_LAST_SOURCE / NAVIGATE_TO_SITE
> intents, etc.), see [`codebase_structure.md`](codebase_structure.md)
> which is kept current via the binding maintenance contract. The
> high-level shape and intent here are still accurate; specific subsystem
> identities and per-knob defaults have evolved.

Phase 5 of the Foundation phase. Sits between the orchestrator's voice
path and the existing coding pipeline; classifies utterances across
coding, automation (OpenClaw-bound), conversational, and hybrid
categories; dispatches them to the right handler.

## Architectural position

```
User utterance
      │
      ▼
Wake word check (COLD) or addressing classifier (WARM)
      │
      ▼
classify_routing()  ← rule-based classifier; LLM disambiguation on tie
      │
      ▼
RoutingIntent
      │
      ▼
CapabilityVoiceController.handle_capability_intent(intent)
      │
      ├──► CONVERSATIONAL → return None; orchestrator uses default voice path
      ├──► CODE_TASK / PROGRESS_QUERY / CANCEL / ADJUSTMENT / CLARIFICATION
      │      → CodingTaskRunner (existing path)
      ├──► BROWSER_AUTOMATION / MEDIA_GENERATION / MESSAGING /
      │   FILE_OPERATION / SHELL_OPERATION
      │      → OpenClawDispatcher (currently STUBBED — voice message says
      │        "the gateway isn't connected yet")
      └──► HYBRID_TASK → HybridTaskDecomposer splits into subtasks; each
                         subtask goes to its handler. Currently stub-narrated.
```

## Key types

[src/ultron/openclaw_routing/intents.py](../src/ultron/openclaw_routing/intents.py):

| Type | Purpose |
|---|---|
| `RoutingIntentKind` | enum: CONVERSATIONAL, CODE_TASK, PROGRESS_QUERY, CANCEL, MID_SESSION_ADJUSTMENT, CLARIFICATION_RESPONSE, BROWSER_AUTOMATION, MEDIA_GENERATION, MESSAGING, FILE_OPERATION, SHELL_OPERATION, HYBRID_TASK |
| `RoutingIntent` | top-level dataclass — wraps a coding intent OR an automation intent OR subtasks (for hybrid) |
| `BrowserIntent` / `MediaGenIntent` / `MessagingIntent` / `FileOpIntent` / `ShellOpIntent` | per-category structured intents |
| `HybridSubtask` | one ordered step in a HYBRID_TASK decomposition |
| `DispatchResult` | what the OpenClawDispatcher returns: `success`, `voice_message`, `error`, `metadata` |
| `TaskInfo` | tracks an in-flight or completed automation task (used by AutomationTaskRunner) |

## Public API

[src/ultron/openclaw_routing/](../src/ultron/openclaw_routing/):

```python
from ultron.openclaw_routing import (
    classify_routing,        # main classifier
    OpenClawDispatcher,      # stubbed dispatch surface
    AutomationTaskRunner,    # stubbed-but-functional task runner mirror
    HybridTaskDecomposer,    # Qwen-driven subtask decomposition
    IntentDisambiguator,     # Qwen-driven coding-vs-automation tiebreaker
    RoutingDecisionLog,      # JSONL audit log writer
    get_routing_log,         # singleton accessor
    RoutingIntent,
    RoutingIntentKind,
)
```

## Classifier

[src/ultron/openclaw_routing/classifier.py](../src/ultron/openclaw_routing/classifier.py)

Rule-based with explicit signal patterns per category. Order:

1. **In-flight task commands** (cancel / progress / adjustment / clarification
   response) — must take precedence so "stop the task" cancels even when an
   utterance contains automation-keyword overlap.
2. **HYBRID signals** — "set up environment", "deploy", "automate workflow",
   "write a script that opens chrome" — checked BEFORE single-category
   coding rules because hybrid utterances often contain coding verbs.
3. **CODE_TASK** — the existing coding classifier's CODE_TASK kind.
4. **Single-category automation rules** — browser, media, messaging, file,
   shell. Each category has its own signal regex.
5. **CONVERSATIONAL** fallback — anything that doesn't match.

Signal examples (full lists in classifier.py):

| Category | Strong signals |
|---|---|
| BROWSER_AUTOMATION | "open <site>", "navigate to", "click on", "fill out the form", "take a screenshot", "log into <site>", "scroll the page" |
| MEDIA_GENERATION | "make me an image of", "generate a picture", "compose music", "draw me", "render me", "generate a (short) video" |
| MESSAGING | "send a message to my phone", "text me", "notify me when", "tell me on telegram", "send me a push notification" |
| FILE_OPERATION | "read the file at <path>", "show me the contents of", "write to / save to", "delete the file at", "list the files in" |
| SHELL_OPERATION | "run dir / ls / git / npm / pip / python ...", "execute the command", "what's the output of" |
| HYBRID_TASK | "set up a dev environment", "install dependencies for", "deploy this to", "automate my workflow", "write a script that opens chrome", "build a tool for my browser" |

## OpenClawDispatcher

[src/ultron/openclaw_routing/dispatcher.py](../src/ultron/openclaw_routing/dispatcher.py)

Five handler methods (`handle_browser`, `handle_media_generation`,
`handle_messaging`, `handle_file_operation`, `handle_shell_operation`).
Phase 5 returns stubs; the OpenClaw integration prompt replaces each
stub body with real Gateway calls.

Stub voice messages stay in Ultron's voice — verified by
[tests/routing/test_dispatcher.py::test_voice_messages_in_ultron_voice](../tests/routing/test_dispatcher.py).

## AutomationTaskRunner

[src/ultron/openclaw_routing/runner.py](../src/ultron/openclaw_routing/runner.py)

Mirror of `CodingTaskRunner`: `submit_task` / `progress_narration` /
`completion_narration` / `cancel` / `list_active`. In Phase 5 every task
completes synchronously inside `submit_task` because the dispatcher
returns immediately. Once OpenClaw is integrated and dispatch is
long-lived, the runner already has the lifecycle hooks for intermediate
narration.

Audit log: [logs/automation_tasks.jsonl](../logs/automation_tasks.jsonl)
(created on first task).

## HybridTaskDecomposer

[src/ultron/openclaw_routing/decomposer.py](../src/ultron/openclaw_routing/decomposer.py)

Calls the local LLM with a JSON-output prompt; expects:

```json
{
  "subtasks": [
    {"order": 1, "type": "automation", "subtype": "file_op",
     "description": "Read C:/data.csv"},
    {"order": 2, "type": "coding",
     "description": "Build a Python script that processes the data"}
  ]
}
```

Robust parsing: strips `<think>...</think>` blocks, handles markdown
fences, drops invalid entries, sorts by `order`. On any parse failure
falls back to a one-element plan that preserves the original utterance
under `type: "coding"` so the user gets a best-effort response.

Disabled by `config.routing.hybrid_task_decomposition_enabled = false`
— in that case decompose() returns the fallback without calling the LLM.

## IntentDisambiguator

[src/ultron/openclaw_routing/disambiguator.py](../src/ultron/openclaw_routing/disambiguator.py)

Two-shot LLM call: "Is this CODING / AUTOMATION / HYBRID / UNCLEAR?".
Token budget: ~50 tokens output. On UNCLEAR the disambiguator returns
a clarifying question for the orchestrator to ask the user.

Disabled by `config.routing.llm_disambiguation_enabled = false` — in
that case disambiguate() always returns UNCLEAR with the default
clarifying question.

## RoutingDecisionLog

[src/ultron/openclaw_routing/decision_log.py](../src/ultron/openclaw_routing/decision_log.py)

Append-only JSONL writer to
`config.routing.routing_log_path` (default `logs/routing_decisions.jsonl`).
Each routed utterance writes one line:

```json
{
  "timestamp": "2026-05-08T...",
  "utterance": "open hacker news",
  "intent": "browser_automation",
  "confidence": 0.85,
  "source": "rule",
  "reason": "browser-automation pattern matched",
  "rule_based": true,
  "handler": "OpenClawDispatcher.handle_browser_automation",
  "outcome": "stub",
  "needs_clarification": false,
  "clarification_question": null,
  "stub_reason": "OpenClaw integration not yet complete"
}
```

Best-effort writes — never raises. Singleton via `get_routing_log()`.

## CapabilityVoiceController (renamed from CodingVoiceController)

[src/ultron/coding/voice.py](../src/ultron/coding/voice.py)

The coding voice controller was renamed to `CapabilityVoiceController`
in Phase 5 because it now dispatches across capabilities, not just
coding. The legacy name is preserved as a module-level alias:

```python
CodingVoiceController = CapabilityVoiceController
```

Existing imports keep working unchanged. The new
`handle_capability_intent(routing_intent)` method routes a `RoutingIntent`
to the right handler (coding / OpenClaw / passthrough) and writes a
routing-decision log entry.

## Configuration

`config.routing` ([config.yaml](../config.yaml)):

```yaml
routing:
  llm_disambiguation_enabled: true
  hybrid_task_decomposition_enabled: true
  disambiguation_question_template: "Did you mean to {coding_interpretation}, or to {automation_interpretation}?"
  routing_log_path: "logs/routing_decisions.jsonl"
  classifier:
    rule_based_first: true
    llm_fallback_enabled: true
    confidence_threshold: 0.7
  stub_responses_enabled: true   # set false after OpenClaw integration completes
```

`config.openclaw`:

```yaml
openclaw:
  enabled: false                      # flip to true once Gateway is up
  gateway_url: null
  auth_token_env: "OPENCLAW_AUTH_TOKEN"
  health_check_timeout_seconds: 30.0
  health_check_interval_seconds: 60.0
  fail_open: true                     # unreachable → in-character stub, not hard error
  required_agent_id: "ultron"
```

## Tests

[tests/routing/](../tests/routing/) — 148 tests in 5 files:

| File | Coverage |
|---|---|
| [test_classifier.py](../tests/routing/test_classifier.py) | 90 tests: 20 BROWSER, 10 each of MEDIA / MESSAGING / FILE / SHELL / HYBRID / CONVERSATIONAL / CODE_TASK + edge cases |
| [test_dispatcher.py](../tests/routing/test_dispatcher.py) | per-stub correctness, Ultron-voice consistency, classify→dispatch round trip |
| [test_decomposer.py](../tests/routing/test_decomposer.py) | well-formed JSON, fenced JSON, thinking blocks, malformed fallback, exception fallback, sort order, disabled-via-config |
| [test_disambiguator.py](../tests/routing/test_disambiguator.py) | clean verdicts, UNCLEAR with/without question, garbage fallback, exception fallback, disabled-via-config, 15 ambiguous round-trip cases |
| [test_decision_log.py](../tests/routing/test_decision_log.py) | append, subtasks, truncation, extra-merge, error-swallowing, singleton |
| [test_backward_compat.py](../tests/routing/test_backward_compat.py) | `CodingVoiceController is CapabilityVoiceController`, `__all__` exports both |

## Removed: OpenClawBridge slot

The Phase A foundation reserved an `"openclaw"` branch in
`build_default_bridge` that pointed at a never-built
`ultron.coding.openclaw_bridge` module. Phase 5 removed the reservation
because OpenClaw is a peer dispatcher under the new architecture, not a
coding-bridge alternative. References in
[bridge.py](../src/ultron/coding/bridge.py) and
[direct_bridge.py](../src/ultron/coding/direct_bridge.py) docstrings
were updated to reflect the new shape.

## Out of scope for Phase 5

These are the responsibility of the OpenClaw integration prompt that
follows this Foundation phase:

- Replace `OpenClawDispatcher`'s stub bodies with real Gateway HTTP calls.
- Wire the `AutomationTaskRunner` to long-lived async dispatch (currently
  every task completes synchronously because dispatch returns instantly).
- Wire the `HybridTaskDecomposer` to schedule its automation subtasks
  through the `AutomationTaskRunner` and its coding subtasks through
  the existing `CodingTaskRunner` — currently HYBRID_TASK utterances
  get a single voice stub.
- Set `config.routing.stub_responses_enabled: false` and
  `config.openclaw.enabled: true` in the OpenClaw integration prompt's
  config additions.

The architecture is in place; the integration is purely additive — no
existing routing code changes when the stubs become real.
