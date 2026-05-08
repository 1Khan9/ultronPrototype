# Ultron development guide

How to work in the codebase: tests, debugging, common tasks.

## Setup (worktree workflow)

The project uses git worktrees for parallel feature work. The main
checkout (`C:\STC\ultronPrototype\`) holds the venv + `models/` +
`.env`. Worktrees share the venv but not the models — heavy
measurement / live-stack runs happen in the main checkout.

```powershell
cd C:\STC\ultronPrototype
.venv\Scripts\activate
# Worktree:
git worktree add .claude/worktrees/feature-x -b feature/x
cd .claude/worktrees/feature-x
# Worktrees use the same venv via the absolute path.
```

## Running tests

```powershell
# Default fast suite (~30 s, 670+ tests)
pytest tests/ -q

# Focused — most useful day-to-day
pytest tests/routing/ -q
pytest tests/error_recovery/ -q
pytest tests/integration/ -q
pytest tests/coding/test_orchestration.py -v

# Slow / GPU-gated tests
$env:PYTEST_RUN_GPU_TESTS = "1"
pytest tests/ -q
```

Slow tests load real models or hit the Claude API. `tests/integration/mocks.md`
catalogs which is which.

## Test layout

```
tests/
  test_*.py                ← unit tests by subsystem
  coding/
    test_orchestration.py        ← 11 mock-bridge orchestration scenarios
    test_orchestration_real.py   ← gated; same scenarios with real Claude
  error_recovery/          ← Phase 4: per-dependency failure modes (52)
  routing/                 ← Phase 5: classifier + dispatcher + decomposer (148)
  integration/             ← Phase 6: end-to-end pipeline (83)
```

## Adding new tests

Patterns proven across phases:

- **Unit tests** for a new module: drop a file at `tests/test_<module>.py`. Use `pytest.mark.parametrize` for table-driven cases.
- **Error-recovery tests**: under `tests/error_recovery/`. Use the `errors_log` + `read_errors` fixtures from `tests/error_recovery/conftest.py` to verify `errors.jsonl` writes and recovery contracts.
- **Integration tests**: under `tests/integration/`. Use the `cap_stack` + `routing_log` + `read_routing` fixtures from `tests/integration/conftest.py`. The `dispatch_utterance(cap_stack, utt)` helper mirrors the orchestrator's main-loop dispatch without needing audio.

## Debugging

### Latency

```powershell
# Re-run baseline measurements (lite mode is CPU-only, ~30 s)
python scripts/measure_baseline_extended.py --lite

# Full mode loads real models (~3 min); locks the GPU
python scripts/measure_baseline_extended.py --full
```

Numbers land in `baselines.json` under `phase_foundation_start.measurements_extended`.
Compare across runs to detect regressions.

For per-call timing inside Python:

```python
from ultron.utils.logging import get_logger
import time
logger = get_logger("debug.timing")

t0 = time.monotonic()
# ... thing under test ...
logger.info("X took %.0f ms", (time.monotonic() - t0) * 1000)
```

### VRAM

```powershell
# Idle + per-component snapshot
python scripts/check_vram.py

# Live monitor
nvidia-smi -l 1
```

### Errors not surfacing to the user

Check `logs/errors.jsonl` first:

```powershell
Get-Content logs/errors.jsonl -Tail 20 | ConvertFrom-Json | Format-Table dependency, error_type, message, recovery
```

Each error record carries:
- `dependency` — short label (`brave_api`, `qdrant`, `piper_tts`, etc.)
- `error_type` — typed exception class name
- `message` — human-readable summary
- `context` — diagnostic key/value pairs
- `recovery` — what fallback was taken

If an error path isn't logging, the wrapper for that dependency
probably isn't using `get_error_log().record(...)`. Phase 3.5
followup tracks the wrappers still pending migration to typed errors.

### Routing decisions

```powershell
Get-Content logs/routing_decisions.jsonl -Tail 20 | ConvertFrom-Json | ft timestamp, intent, outcome, handler
```

If an utterance is classifying wrong, the rule-based regexes are the
first thing to look at. The classifier file is
[src/ultron/openclaw_routing/classifier.py](../src/ultron/openclaw_routing/classifier.py);
each category has its own regex with strong-signal alternation. Add a
test in `tests/routing/test_classifier.py` for the offending utterance,
verify it fails, then tighten the regex.

## Adding a new MCP tool

The MCP server at [src/ultron/coding/mcp_server.py](../src/ultron/coding/mcp_server.py)
exposes tools that Qwen can call. To add one:

1. Add a method on `UltronMCPServer` with a Python signature (typed args + return type).
2. If the tool needs state from the session, fetch it via `self.store.get(session_id)`.
3. **Critical:** if the tool returns session state to Qwen, use a projection (see [projections.py](../src/ultron/coding/projections.py)) — never pass raw `ProjectSession` objects to a context-budgeted caller.
4. Decorate appropriately if needed (the server auto-registers methods for the SSE transport).
5. Add a unit test in `tests/test_mcp_server.py`.
6. Document the tool in the appropriate place — typically [docs/architecture.md](architecture.md) under "Subsystems".

## Adding a new intent category

The capability routing classifier at
[src/ultron/openclaw_routing/classifier.py](../src/ultron/openclaw_routing/classifier.py)
returns one of the kinds in `RoutingIntentKind`. To add a new one:

1. Add an enum value to [intents.py:RoutingIntentKind](../src/ultron/openclaw_routing/intents.py).
2. Add a structured-intent dataclass if the new kind needs payload (e.g. like `BrowserIntent`).
3. Add a regex pattern + a builder function (`_build_X_intent`) in `classifier.py`.
4. Add a branch in `classify_routing` to fire the pattern + populate the new structured intent.
5. Extend [`_CODING_KIND_MAP`](../src/ultron/openclaw_routing/classifier.py) only if the new kind delegates to the existing coding pipeline.
6. Add a handler branch in
   [voice.py:CapabilityVoiceController.handle_capability_intent](../src/ultron/coding/voice.py).
7. Add tests:
   - 10+ utterances in `tests/routing/test_classifier.py`
   - A dispatcher test in `tests/routing/test_dispatcher.py` if it routes to OpenClaw
   - An integration test in `tests/integration/test_routing_dispatch.py`

## Configuration changes

1. Add the field to the appropriate sub-model in
   [src/ultron/config.py](../src/ultron/config.py).
   Use `Field(default=..., ge=..., le=...)` for range constraints.
2. Add the field to [config.yaml](../config.yaml) with a comment explaining what it does and safe range.
3. Document in [docs/configuration.md](configuration.md).
4. If the field replaces an existing `settings.X` constant: migrate the
   subsystem to read directly from `get_config()` and remove the
   constant from [config/settings.py](../config/settings.py). See
   [phase3_5_followup.md](phase3_5_followup.md) for the recipe.
5. Confirm the loader rejects malformed values:
   `python scripts/validate_config.py`.

## Adding a new external dependency

1. Define a typed exception in
   [src/ultron/errors.py](../src/ultron/errors.py) (subclass
   `DependencyUnavailableError`).
2. Wrap the call sites: typed-error raising on failure, recovery
   description in `with_recovery(...)`, log to `errors.jsonl` via
   `get_error_log().record(...)`.
3. If the dependency is failure-prone AND remote, add a circuit
   breaker (per the Brave / Jina pattern in
   [src/ultron/web_search/](../src/ultron/web_search/)). In-process
   dependencies don't need breakers.
4. Add an `error_phrases.X` pool to [config.yaml](../config.yaml) for
   the user-facing voice message.
5. Add tests in `tests/error_recovery/`. Use the existing fixtures.

## Code style

- Type hints on every public function signature.
- Docstrings on every public function/class — describe behavior, not implementation.
- No bare `except:`. Broad `except Exception:` is fine for explicit best-effort paths (cleanup, optional fallbacks); add a comment explaining why.
- Paths via `pathlib`, not string concat.
- No magic numbers in subsystem code — they go in
  [config.yaml](../config.yaml) with a comment in
  [src/ultron/config.py](../src/ultron/config.py).
- Logging at INFO/WARN/ERROR/DEBUG per [docs/architecture.md](architecture.md) "Logging conventions".
- No fire-and-forget `asyncio.create_task` without storing the reference or attaching exception handling.

## Common pitfalls

- **Loading models in tests.** Don't. Use mocks. Real-model tests go in PYTEST_RUN_GPU_TESTS=1-gated files.
- **Session state to Qwen.** Always go through a projection. Direct `ProjectSession` exposure overflows the context budget on long sessions. See [docs/configuration.md](configuration.md) §Projections + [projections.py](../src/ultron/coding/projections.py).
- **Mutating module state for "scoping".** [coordinator.py:895](../src/ultron/coding/coordinator.py:895) sets `settings.LLM_MAX_TOKENS = ...` to scope a max-tokens override. This is a hack — refactor target. See [phase3_5_followup.md](phase3_5_followup.md) "KNOWN HAZARD".
- **Threads outliving tests.** The scripted mock bridge spawns daemon threads that try to call back into test fixtures. If you see "cannot schedule new futures after interpreter shutdown", you're calling fixtures from a thread that survived test exit. Fix: either join the thread synchronously in the test, or stub the call differently.
- **Worktree path resolution.** When running scripts that load models, `chdir` to the main checkout first — the `.env` file and relative paths resolve from cwd. [scripts/measure_baseline_extended.py](../scripts/measure_baseline_extended.py) shows the pattern.

## Where things are documented

| Topic | Doc |
|---|---|
| **Codebase structure (start here)** | **[docs/codebase_structure.md](codebase_structure.md)** |
| Architecture overview | [docs/architecture.md](architecture.md) |
| Configuration reference | [docs/configuration.md](configuration.md) |
| Operations + recovery | [docs/operations.md](operations.md) |
| Error handling catalog | [docs/error_handling.md](error_handling.md) |
| Capability routing | [docs/routing.md](routing.md) |
| System inventory (Phase 1 snapshot) | [docs/system_inventory.md](system_inventory.md) |
| Mock setup for integration tests | [tests/integration/mocks.md](../tests/integration/mocks.md) |
| Phase 3 config-discovery catalog | [docs/config_discovery.md](config_discovery.md) |
| Phase 3.5 followup punch list | [docs/phase3_5_followup.md](phase3_5_followup.md) |
| 16-step real-stack smoke test | [docs/smoke_test.md](smoke_test.md) |

**`docs/codebase_structure.md` has a maintenance contract — when you
add/change a module, function, script, or significant interface, update
that file as part of the same change.**
