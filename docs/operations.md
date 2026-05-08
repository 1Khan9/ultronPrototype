# Ultron operations

Day-to-day running, monitoring, recovery, maintenance.

## Starting up

```powershell
# from the main checkout
cd C:\STC\ultronPrototype
.venv\Scripts\activate
python -m ultron
```

First boot from cold: ~60 s as Whisper + LLM + RVC + Piper load. Subsequent starts are faster (OS file cache holds the GGUF).

Expected console output on a clean boot:

```
Ultron is listening. Say 'ultron' to wake.
[CAPTURING]
[PROCESSING]
  you: <transcribed text>
  ultron: <response>
  (still listening for ~30 s — keep talking or stay silent to drop back to wake-word mode)
```

## Required environment

Set in `.env` at the project root:

```ini
# Required for web search (Phase 4 integration)
ULTRON_BRAVE_API_KEY=brv-XXXXXXXXXXXXXXXXXXXXXXXX

# Optional — opt-in overrides
ULTRON_LLM_MODEL_PATH=models/Qwen3.5-9B-Q4_K_M.gguf
ULTRON_AUDIO_DEVICE=Yeti
ULTRON_AUDIO_OUTPUT_DEVICE=Schiit
ULTRON_LOG_LEVEL=INFO
```

The Brave key is read by name (`web_search.brave_api_key_env` in
config.yaml — defaults to `ULTRON_BRAVE_API_KEY`). The key value never
appears in config files or logs.

## Monitoring

### Live log

`logs/ultron.log` — rotating handler at DEBUG, console handler at the
configured level.

```powershell
# Tail live
Get-Content logs/ultron.log -Wait -Tail 30
```

### Audit logs (one JSON object per line)

| File | What it records |
|---|---|
| `logs/addressing.jsonl` | Every classifier verdict (decision / source / latency) |
| `logs/coding_tasks.jsonl` | Coding task lifecycle events |
| `logs/verifications.jsonl` | Verifier passes per coding session |
| `logs/clarifications.jsonl` | Clarification requests + decisions |
| `logs/mcp_calls.jsonl` | MCP tool calls |
| `logs/sessions/<id>.jsonl` | Per-session detailed coding audit |
| `logs/errors.jsonl` | Typed dependency errors (Phase 4) |
| `logs/routing_decisions.jsonl` | Routing classification + dispatch (Phase 5) |
| `logs/automation_tasks.jsonl` | OpenClaw automation task records (Phase 5) |

Quick scans:

```powershell
# Count errors by dependency
Get-Content logs/errors.jsonl | ConvertFrom-Json | Group-Object dependency | ft Name, Count

# Show recent routing decisions
Get-Content logs/routing_decisions.jsonl -Tail 20 | ConvertFrom-Json | Format-Table timestamp, intent, outcome, handler

# Most-used routing intents this session
Get-Content logs/routing_decisions.jsonl | ConvertFrom-Json | Group-Object intent | Sort-Object Count -Desc
```

### VRAM / GPU

```powershell
# One-shot
nvidia-smi

# Continuous
nvidia-smi -l 1
```

The dedicated check:

```powershell
python scripts/check_vram.py
```

Prints idle / per-component allocation snapshots and flags peak >
11.5 GB hard cap.

### Reviewing addressing decisions

```powershell
python scripts/review_addressing.py             # last 50
python scripts/review_addressing.py --tail 200
python scripts/review_addressing.py --misses    # likely false negatives
```

## Common failure modes and recovery

### "LLM model not found"

Configured path doesn't exist on disk. Either:
- `python scripts/download_models.py` to fetch the canonical Qwen3.5-9B Q4_K_M GGUF.
- Or set `ULTRON_LLM_MODEL_PATH` (or edit `config.yaml`'s `llm.model_path`) to a valid GGUF.

### "Whisper crashes with cuBLAS / cuDNN errors"

faster-whisper (via CTranslate2) needs cuDNN 9 DLLs on PATH. Install
[cuDNN 9 for CUDA 12.x](https://developer.nvidia.com/cudnn) and either
add the install dir to PATH or copy `cublas64_12.dll` and
`cudnn_ops_infer64_9.dll` next to your venv.

### "Wake word detection is offline"

`models/openwakeword/ultron.onnx` is missing. The fallback to
`hey_jarvis` triggers automatically with a startup warning. To get
true `ultron` detection, train via openWakeWord's automatic training
notebook and place the resulting ONNX at
`models/openwakeword/ultron.onnx`.

### "Memory's not responding right now"

Qdrant store at `data/qdrant` is corrupt or unreachable. The voice
pipeline keeps working from base knowledge; conversation memory just
isn't available for retrieval.

Recovery:
1. Stop Ultron.
2. Back up `data/qdrant/` (just in case).
3. Re-run `python scripts/migrate_memory_to_qdrant.py` to rebuild
   collections from `data/memory.jsonl`.
4. Restart.

### "Search isn't working right now"

Either Brave is down (rare), the API key is invalid, or the rate
limiter is throttling. Check:

```powershell
# Confirm key is set
echo $env:ULTRON_BRAVE_API_KEY

# Recent Brave-related errors
Get-Content logs/errors.jsonl | ConvertFrom-Json | Where-Object dependency -eq brave_api | Select-Object -Last 5
```

The circuit breaker (5-min cooldown after 3 failures) auto-resets on a
successful probe.

### "Anthropic's API isn't responding"

Coding session paused. Check Anthropic API status; check the
`ULTRON_CLAUDE_CLI` path resolves. The session goes to PAUSED state;
user can retry or abandon.

### Voice conversion is offline

RVC failed to convert (CUDA OOM, model corruption). Pipeline falls back
to neutral Piper voice automatically. To re-enable RVC after fixing the
underlying cause: restart Ultron.

## Maintenance

Run the periodic Qdrant maintenance pass:

```powershell
python scripts/maintenance.py
```

This:
- Summarizes old conversations into the `facts` collection.
- Extracts entities + topic tags.
- Labels conversation clusters.
- Prunes stale `web_results` cache entries.

Recommended: nightly, or whenever the conversations collection grows
substantially.

## Backups

Critical data:
- `data/qdrant/` — conversation memory (irreplaceable; backup regularly)
- `data/projects.json` — project registry
- `data/memory.jsonl` — legacy turn log (rebuilds Qdrant if needed)
- `config.yaml` + `.env` — system configuration

Models in `models/` and the RVC voice in `ultron_james_spader_mcu_6941/`
are large (~6 GB) but reproducible — re-run `scripts/download_models.py`
or recopy the RVC voice from its source.

```powershell
# Simple compressed backup
$ts = Get-Date -Format "yyyyMMdd-HHmm"
Compress-Archive -Path data\qdrant, data\projects.json, data\memory.jsonl, config.yaml `
                 -DestinationPath ".backups\ultron-$ts.zip"
```

## Updating

```powershell
git pull
pip install -e .   # if pyproject.toml changed
pytest tests/ -q   # smoke-check 600+ unit/integration tests still pass
python -m ultron   # back to live
```

If a `pull` introduces config schema changes, the loader fails loud at
startup with the offending key path. Edit `config.yaml` to match and
re-run.

## Validating config without starting

```powershell
python scripts/validate_config.py            # validate ./config.yaml
python scripts/validate_config.py path/to/config.yaml
```

Prints the resolved configuration and exits non-zero if validation
fails. No model loading.

## Dumping a coding session for inspection

```powershell
python scripts/dump_session.py <session_id>
```

Renders the per-session JSONL audit log
(`logs/sessions/<session_id>.jsonl`) into a human-readable transcript
with stages, file changes, clarifications, verification results, and
final summary.

## Performance tuning levers

The most useful knobs in `config.yaml`:

- `audio.barge_in_grace_seconds` — raise if Ultron self-triggers on
  her own onset; lower if she feels unresponsive to interruption.
- `vad.min_silence_duration_ms` — tightens turn-taking; reduces the
  pause needed before Ultron starts responding.
- `wake_word.threshold` — raise toward 0.7 if false positives are
  frequent; lower toward 0.4 if Ultron misses wake calls.
- `addressing.warm_mode_duration_seconds` — currently 30 s. Reduce to
  10-15 if follow-up window feels long.
- `tts.piper_length_scale` — main "talks too fast / slurred" lever.
  >1.0 slows speech; <1.0 speeds up.
- `tts.rvc.protect` — main lever for crisp consonants. Higher (toward
  0.5) keeps Piper's articulation; lower lets the RVC timbre dominate.
- `llm.default_temperature` — lower for more deterministic behavior;
  raise for more creative responses.

Don't touch `llm.flash_attn`, `llm.kv_cache_type`, or `llm.gpu_layers`
unless you've profiled — these are the VRAM/quality tradeoffs that the
Phase 1 baseline depends on.
