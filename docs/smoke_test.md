# Foundation phase final smoke test

End-to-end real-stack walkthrough simulating real user experience.
Run from the main checkout (`C:\STC\ultronPrototype`) — worktrees don't
have models. Coordinated execution with GPU + audio + Claude API; not
suitable for inline test runs.

This procedure is the Part 7.4 verification gate for the Foundation
phase. Each step is observable; if any fails, log the symptom and the
phase that owns the responsibility (per the per-step header).

## Pre-flight

```powershell
cd C:\STC\ultronPrototype
.venv\Scripts\activate

# Confirm config validates
python scripts/validate_config.py

# Confirm GPU is reachable + VRAM headroom
python scripts/check_vram.py

# Confirm test suite is green
pytest tests/ -q
```

Expected: validation OK, VRAM <3 GB used, 670+ tests pass, 0 failures.

If any of these fail, **stop**. The smoke test assumes a healthy
baseline.

## Sixteen-step procedure

### 1. Cold start

```powershell
python -m ultron
```

Expected: ~60 s load time. Console prints "Ultron is listening. Say
'ultron' to wake."

`scripts/check_vram.py` (in another shell) should show ~10 GB used.

**Phase responsibility:** core voice stack (Phases A + 0-5).

### 2. Voice query: "Good morning, Ultron."

Speak the wake word + greeting.

Expected: in-character response within ~1.5 s of end-of-speech. No
filler ("certainly", "of course", etc.). Slightly menacing tone.

Console shows:
```
  you: good morning ultron
  ultron: <terse, in-character greeting>
```

**Phase responsibility:** orchestrator + Whisper + LLM + Piper + RVC.

### 3. Memory recall: "What did we talk about yesterday?"

Expected: if conversation history exists in Qdrant, RAG retrieves
recent turns and Ultron summarizes. If no prior history, Ultron says
so plainly.

Verify in `logs/ultron.log` that retrieval ran (look for "memory
retrieve" lines).

**Phase responsibility:** Qdrant memory + RAG (Phase 3).

### 4. Search-triggering query: "What's the latest on Python 3.13 features?"

Expected:
- Within ~200 ms, Ultron speaks an acknowledgment phrase ("Querying
  external sources." or similar from the pool).
- Brave call → Jina Reader fetch → response with citations.
- Console shows:
  ```
    sources:
      [1] <title> -- <url>
      ...
  ```

**Phase responsibility:** web search (Phase 4 of original prompts).

### 5. Coding task: "Build me a Python script that does X"

Replace X with a small concrete task (e.g. "prints today's date in ISO
format").

Expected:
- Ultron acknowledges the task ("Acknowledged. Starting.").
- Console + `logs/coding_tasks.jsonl` show task progress.
- A new project appears under `data/sandbox/`.
- Files are created.
- After 1-3 minutes, Ultron speaks the completion narration.

**Phase responsibility:** coding orchestration (Phases A + 6 of original prompts).

### 6. Status query during coding: "How's it going?"

Speak this DURING the coding task in step 5 (within the WARM-mode
window after task acknowledgment).

Expected: status delta narration covering current stage, files
touched, time elapsed. Should be <1 s response.

Verify the status_delta projection didn't truncate (typical sessions
fit well under the 600-token budget).

**Phase responsibility:** projections (Foundation Part 2) + narration.

### 7. Mid-session adjustment: "Actually, use Y instead"

Replace Y with a reasonable adjustment (e.g. "use UTC instead of
local time").

Expected: Ultron records the adjustment and the coding task picks it
up on the next correction or follow-up. Visible in
`logs/sessions/<id>.jsonl` as an `adjustment` event.

**Phase responsibility:** coordinator + adjustment_context projection.

### 8. Cancel: "Stop the task"

Expected: graceful cancellation. Ultron narrates "Cancelled." or
similar. Subprocess terminates cleanly.

**Phase responsibility:** runner + bridge.

### 9. OpenClaw stub: "Open Wikipedia"

Expected: stub response in Ultron's voice ("I'd open that page for
you, but the gateway isn't connected yet.").

`logs/routing_decisions.jsonl` shows:
```json
{
  "intent": "browser_automation",
  "outcome": "stub",
  "stub_reason": "OpenClaw integration not yet complete"
}
```

**Phase responsibility:** capability routing (Foundation Part 5).

### 10. Hybrid task stub: "Set up a development environment for this project"

Expected: stub response acknowledging both pieces ("I can see that's a
mix of coding and automation. I'd split it up and run both, but the
gateway isn't connected yet.").

`logs/routing_decisions.jsonl` shows `intent: "hybrid_task"`,
`outcome: "stub"`.

**Phase responsibility:** capability routing + decomposer.

### 11. Restart

Stop Ultron (Ctrl+C). Restart:

```powershell
python -m ultron
```

Expected: clean shutdown of TTS / RVC / Whisper / LLM. Restart loads
the same models in ~30-60 s (file cache warm).

### 12. State persistence verification

After restart, ask: "What did we talk about earlier?"

Expected: Ultron retrieves earlier-this-session conversation from
Qdrant. The project from step 5 still exists in `data/projects.json`
(verify with `cat data/projects.json`).

**Phase responsibility:** Qdrant + project registry persistence.

### 13. Maintenance script

Stop Ultron. Run:

```powershell
python scripts/maintenance.py
```

Expected: summarization populates the `facts` collection. Cluster
labeling tags conversation clusters. Output reports counts.

Verify with:
```powershell
python -c "from ultron.config import resolve_path; from qdrant_client import QdrantClient; c = QdrantClient(path=str(resolve_path('data/qdrant'))); print(c.count('facts').count, 'facts')"
```

**Phase responsibility:** maintenance pipeline.

### 14. Inject a Brave failure

Stop Ultron. Edit `.env` to set an invalid Brave API key:

```ini
ULTRON_BRAVE_API_KEY=invalid-test-key
```

Restart Ultron. Ask a search-triggering query: "What's the latest news?"

Expected:
- The orchestrator detects the bad key OR Brave returns 4xx.
- Three failures within 5 minutes trips the breaker.
- Ultron speaks the in-character fallback ("Search isn't working
  right now." or similar).
- `logs/errors.jsonl` records `BraveAPIError` entries.

Restore the real key and restart.

**Phase responsibility:** error handling + circuit breaker
(Foundation Part 4).

### 15. Audit log inspection

Stop Ultron. Verify each log file populated:

```powershell
@(
  'logs/ultron.log',
  'logs/addressing.jsonl',
  'logs/coding_tasks.jsonl',
  'logs/routing_decisions.jsonl',
  'logs/errors.jsonl',
  'logs/automation_tasks.jsonl'
) | ForEach-Object {
  if (Test-Path $_) {
    $size = (Get-Item $_).Length
    Write-Host "$_  -- $size B"
  } else {
    Write-Host "$_  -- MISSING"
  }
}
```

Expected: all files present and non-empty (except `mcp_calls.jsonl`
and `automation_tasks.jsonl` may be empty if no MCP / automation
work happened in this run — that's OK).

Inspect a coding session:
```powershell
python scripts/dump_session.py --latest
```

Expected: a clean transcript of stages, file changes, verifications,
and completion.

### 16. Final VRAM + latency check

Restart Ultron. After full load:

```powershell
python scripts/check_vram.py
```

Expected: ≤10.4 GB used (regression target = the voice-path peak from
the Foundation Phase 0 baseline). NOT 9.2 GB — the prompt's nominal
target is below where the existing baseline already lives; the
operative no-regression rule is "don't exceed 10.4 GB peak".

Run a few representative voice queries; observe TTFT in console output.

Expected: median first-token latency similar to the baseline (~125 ms
TTFT, ~742 ms TTFA composite). Sample 10 queries; median should match
within ~10 %.

## Pass criteria

All 16 steps execute as expected. Failures are documented with:
- Step number
- Symptom (what happened vs. expected)
- Phase responsibility (per the per-step headers)
- Logs at the time of failure

## Recording results

```powershell
@{
  smoke_test_run_at = (Get-Date).ToString("o")
  pass = $true        # set to actual outcome
  notes = "..."        # any deviations
} | ConvertTo-Json | Out-File -FilePath docs/smoke_test_results.json
```

Save this file alongside the docs so the result is part of the
phase's record.
