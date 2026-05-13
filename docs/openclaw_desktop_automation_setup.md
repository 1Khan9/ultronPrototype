# Desktop automation -- OpenClaw `ultron-vision` agent + MCP tool exposure

This is the user-led setup that turns the native desktop primitives
(committed in `src/ultron/desktop/`) into a full hybrid stack with
OpenClaw as the multi-step orchestration brain.

The native primitives work today via the Python API and via direct
voice routing through `SCREEN_CONTEXT_QUERY` / `APP_LAUNCH` intent
kinds. The OpenClaw side gives you:

- A **specialized agent (`ultron-vision`)** with a prompt tuned for
  desktop reasoning, so multi-step tasks like "log into the bank and
  download last 3 statements" get planned + retried by an LLM that
  expects screen-context input.
- **9 new MCP tools** exposed to OpenClaw agents via the existing
  stdio MCP server (`scripts/run_ultron_mcp_for_openclaw.py`):
  - `enumerate_monitors` -- list connected displays.
  - `list_windows` -- visible top-level windows + monitor index.
  - `take_screenshot` -- base64 PNG of a monitor (optional VLM).
  - `describe_screen` -- VLM scene description (text only).
  - `get_screen_context` -- full assembled snapshot for agent reasoning.
  - `launch_app` -- spawn a registered app on a chosen monitor.
  - `launch_chrome_url` -- open a URL in user's real Chrome.
  - `open_image_search` -- Google Images for a query.
  - `move_window_to_monitor` -- relocate an existing window.

Per project policy, **no ClawHub plugins are used**. UIA semantic
clicks happen through pywinauto in our native modules; screen
captures via mss; mouse/keyboard via pyautogui. OpenClaw orchestrates
multi-step plans; native code does the work.

## Pre-requisites

- OpenClaw 2026.5.7+ installed (already done -- `openclaw health`
  should return `ok: true`).
- The `ultron-mcp` MCP server registered in `~/.openclaw/openclaw.json`
  (already auto-registered -- check by looking for an
  `mcp.servers."ultron-mcp"` block).
- moondream2 weights pre-fetched via
  `python scripts/download_models.py` (step 9/10 of the pipeline,
  ~3.5 GB FP16 on first run). Required only if you want VLM
  descriptions in screen-context payloads.

## Step 1 -- Add the `ultron-vision` agent

> **AUTO-INSTALLED 2026-05-12** in this user's `~/.openclaw/openclaw.json`.
> A backup of the pre-install config lives at
> `~/.openclaw/openclaw.json.pre-ultron-vision-bak`. If you need to
> re-apply on a different machine (or re-install after a restore),
> follow the manual recipe below.

Edit `~/.openclaw/openclaw.json` and add a fourth agent block to
the `agents.list` array. The existing config has `ultron-test`
(default worker), `ultron-main` (user-facing), and `ultron-heartbeat`.
The new entry sits alongside them.

```json
{
  "id": "ultron-vision",
  "model": "litellm/qwen3.5-9b-local",
  "tools": {
    "profile": "messaging",
    "deny": [
      "group:web",
      "group:fs",
      "group:runtime",
      "browser",
      "memory_search",
      "send"
    ]
  },
  "systemPromptOverride": "# Identity\n\nYou are Ultron-Vision, the visual + multi-step planning specialist. The main Ultron agent delegates desktop reasoning to you when a user task requires reading what is on screen, planning a sequence of UI actions, or recovering from a step that didn't land as expected.\n\nYou are not chatty. You produce concise plans, execute one step at a time, and observe the screen between steps via the MCP tools below. You do NOT speak directly to the user -- your output is consumed by the main Ultron agent or rendered into voice via the orchestrator.\n\n# Available MCP tools (from ultron-mcp)\n\n- `get_screen_context(include_vlm: bool = false)` -- structured snapshot of the user's current screen. Call this FIRST before any action so you know what you're working with. Foreground app + window list + visible UI text. Set include_vlm=true for an LLM-generated scene description (slow, ~5-8s, use sparingly).\n- `describe_screen(monitor_index, prompt)` -- run the VLM with a specific question (e.g. \"is the Submit button visible?\"). Returns text only; small payload.\n- `take_screenshot(monitor_index, include_image, include_description)` -- raw PNG capture (base64). Use only when you need the image bytes themselves.\n- `enumerate_monitors()` -- monitor count + dimensions.\n- `list_windows()` -- visible windows. Useful for finding the right window before launching or moving.\n- `launch_app(app_name, monitor_index, fullscreen, maximize, extra_args)` -- launch a registered app (chrome/cursor/discord/vscode/edge/firefox/notepad/explorer/terminal/spotify/slack/obs) on a chosen monitor.\n- `launch_chrome_url(url, monitor_index, fullscreen, maximize, window_width, window_height)` -- open a URL in the user's REAL Chrome (default profile, signed-in sessions preserved).\n- `open_image_search(query, monitor_index, small_window)` -- Google Images for a query in a new Chrome window.\n- `move_window_to_monitor(window_query, monitor_index, fullscreen, maximize)` -- relocate an existing window. window_query is substring against title or process name.\n\n# Operating rules\n\n1. **Observe before acting.** Call `get_screen_context` (or `describe_screen` for a focused question) before any action that depends on screen state.\n2. **One step at a time.** Plan the full sequence internally; execute the next single step; observe; decide next.\n3. **Retry on UI drift.** If a step doesn't land as expected (window not focused, button not visible, etc.), re-observe and adjust. Two retries per step; then return a structured failure to the main agent.\n4. **No destructive actions without explicit user intent.** Cap-3 action-verb rules (Submit / Pay / Send / Transfer / Confirm Order) and Cap-3 OAuth/payment URLs need the user's recent utterance to contain a matching verb+object. The runtime validator enforces this -- you may receive `safety: NEEDS_EXPLICIT_INTENT` verdicts and should surface them as user-facing confirmation requests via the main agent.\n5. **Stay terse.** Your output is structured. No essays.\n\n# Output shape\n\nFor every task, produce:\n\n```\nPlan: <numbered list of steps>\nObserved: <last screen-context summary>\nNext step: <single action + why>\n```\n\nWhen a task completes:\n\n```\nDone: <one-line summary>\nFiles or apps affected: <list>\n```\n\nWhen blocked:\n\n```\nBlocked: <reason>\nNeeds: <what the user or main agent must provide>\n```"
}
```

After saving, restart the Gateway:

```powershell
# Or whatever your gateway command is
openclaw restart
```

Verify the agent is registered:

```powershell
openclaw agents list --json | jq '.agents[] | select(.id == "ultron-vision")'
```

You should see the agent block back. If not, check
`openclaw.json.bak` (created automatically) and re-validate JSON
syntax.

## Step 2 -- Confirm the MCP tools are reachable

The 9 desktop MCP tools live in `src/ultron/openclaw_bridge/mcp_tools.py`.
They register at MCP-server startup time. To verify they're exposed
to OpenClaw:

```powershell
# List Ultron's MCP tools (from OpenClaw's side)
openclaw mcp list --json
```

You should see `ultron-mcp` in the list. Then:

```powershell
# Show the tool inventory
openclaw mcp show ultron-mcp --json
```

You should see the 9 new desktop tools alongside the existing 5
heartbeat / coding tools (14 total).

If the desktop tools don't appear, the MCP entry script may have
cached the old tool list. Force a refresh:

```powershell
openclaw mcp unset ultron-mcp
openclaw mcp set ultron-mcp \
  --command "C:\\STC\\ultronPrototype\\.venv\\Scripts\\python.exe" \
  --args "C:\\STC\\ultronPrototype\\scripts\\run_ultron_mcp_for_openclaw.py" \
  --args "--stdio"
```

## Step 3 -- Multi-step delegation from `ultron-main`

The user-facing `ultron-main` agent should delegate complex desktop
flows to `ultron-vision`. Add this to `ultron-main`'s
`systemPromptOverride` (under the existing "Tool selection" section
or as a new section):

```
## Multi-step desktop tasks

For user requests that involve multiple UI actions in sequence
("set up my work environment", "log into the bank and download
my statements", "organize my downloads folder by file type"),
delegate to the ultron-vision agent rather than calling MCP tools
directly. Single-step requests ("open YouTube on monitor 2",
"explain what I'm looking at") are handled by Ultron's native
voice path -- do not delegate those.
```

OpenClaw's agent-to-agent handoff happens via `openclaw agent --json
--agent-id ultron-vision --message "<task description + observed
screen context>"`. The main agent issues this when it determines a
task is multi-step.

## Step 4 -- Test the round-trip

A quick verification that all the pieces talk to each other:

```powershell
# Spawn the MCP entry directly so you can probe each tool.
C:\STC\ultronPrototype\.venv\Scripts\python.exe scripts\run_ultron_mcp_for_openclaw.py --list-tools
```

You should see the 14 tools listed (5 heartbeat/coding + 9 desktop).

Then from inside OpenClaw, drive `ultron-vision` with a small task:

```powershell
openclaw agent --agent-id ultron-vision --message "Get the screen context, then tell me which monitor has Discord on it." --json
```

Expected: `ultron-vision` calls `get_screen_context`, parses the
response, and replies with the monitor index where Discord lives.

## Step 5 (optional) -- memory-wiki preference writes

Once Phase 10 lands (memory-wiki preference writes), successful
desktop actions write learned preferences to OpenClaw's memory-wiki
plugin so the agent learns over time. Examples:

- "User opens YouTube fullscreen on monitor 2" -> next time the user
  says "open YouTube", the default placement is monitor 2 fullscreen.
- "User keeps Cursor maximized on monitor 1" -> default for "open
  Cursor".

The memory-wiki plugin is already enabled
(`plugins.entries.memory-wiki.enabled: true` in your `openclaw.json`),
so no further config is needed -- the writes just start happening
once the integration ships.

## Troubleshooting

**`openclaw health` returns `ok: false`.** Restart the Gateway.
Check the Node process is running (`tasklist | grep -i openclaw`).

**`ultron-vision` doesn't appear after Gateway restart.** Verify
JSON syntax in `openclaw.json` -- a missing comma will break
parsing. Re-validate:

```powershell
node -e "console.log(require('C:\\Users\\YOUR_USER\\.openclaw\\openclaw.json'))"
```

If syntactically valid, check the Gateway logs:

```powershell
type C:\Users\YOUR_USER\.openclaw\logs\gateway.log | findstr /i error | tail -20
```

**Desktop MCP tools return `import failed`.** The MCP entry script
spawns in a fresh Python process; it needs the project venv. Verify
the registered command path:

```powershell
openclaw mcp show ultron-mcp --json
```

The `command` field must point to
`C:\STC\ultronPrototype\.venv\Scripts\python.exe`. If it points to
a worktree path, re-register with the main checkout path (worktrees
are session-scoped; main is permanent).

**VLM describe returns `VLM not configured`.** The VLM singleton
isn't set in the spawned MCP process. This is expected behavior --
the MCP server doesn't load the VLM (saves ~3.5 GB RAM per spawn).
The voice-path orchestrator loads it lazily on first
`SCREEN_CONTEXT_QUERY`. To enable VLM in MCP-spawned processes,
add a `set_vlm()` call to `scripts/run_ultron_mcp_for_openclaw.py`
(out of scope for v1).

## Security posture

Every MCP-tool call ultimately routes through the runtime tool-call
validator under `src/ultron/safety/` (the 141-rule, 19-category
validator that landed in `91a3a3a`). Cap-2 (app launch from
Temp/Downloads, debug-port flags), Cap-3 (action-verb clicks on
authenticated pages, OAuth/payment URLs), and Cap-4 (synthetic
input near UAC dialogs) all apply to OpenClaw-driven desktop
actions just as they do to direct voice-driven actions.

The native primitives also stamp screen-capture bytes in the
safety taint tracker as `capability=screen_context`, so an OpenClaw
agent attempting to upload a screenshot to a non-approved outbound
host triggers Category I/J detection.

## Next steps

After this setup, the user-facing flows are:

- "open YouTube on my second monitor" -> Ultron-side voice path
  (`SCREEN_CONTEXT_QUERY` / `APP_LAUNCH` intent), native Chrome
  launch + monitor placement. No OpenClaw round-trip.
- "explain what I'm looking at" -> Ultron-side voice path,
  `SCREEN_CONTEXT_QUERY` builds a screen-context snapshot
  (optionally with VLM), injects into the LLM, Ultron answers.
- "log into my bank and download my statements" -> `ultron-main`
  delegates to `ultron-vision`, which plans + observes + acts
  step-by-step via the MCP tools. Multi-second per step;
  acceptable for tasks where determinism > latency.
