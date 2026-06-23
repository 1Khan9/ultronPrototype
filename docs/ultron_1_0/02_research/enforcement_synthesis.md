# Enforcement bundle — synthesized design of record (Option 1)

> Source: the 40-agent frontier+adversarial board (`enforcement_board_digest.md` full / `enforcement_board_compact.md`
> decision-grade). 20 research facets (sonnet) + 20 adversarial lenses (opus); 37/40 returned (3 legacy-tooling
> critics throttled but covered by ≥6 adjacent lenses). Synthesis by the lead (BR-15.4). This file is the design
> the canon `examples/` + `ENFORCEMENT.md` + the prose rules docs are updated FROM. Validating board run: `wf_7ea649a6-454`.

## 0. The governing principle the board converged on
**Teeth come from `PreToolUse` deny-rules + hooks + CI — never from removing a capability.** Hooks fire in *every*
permission mode (the hook input even carries `permission_mode:"bypassPermissions"`), so the hard blocks hold during a
full-autonomy run *without* disabling bypass/auto mode. Therefore: **maximum teeth AND zero capability loss are not in
tension** — they're achieved by the *kind* of control, not by restriction. Every control below is graded GO /
NEEDS-CHANGE / NO-GO against the mandate "zero loss of functionality, tools, or autonomy."

## 1. Board corrections that change the canon's current ENFORCEMENT.md (all verified vs official docs)
| # | Canon today (generic kit) | Verdict | Fix |
|---|---|---|---|
| C1 | `post-edit` hook runs `ruff format <file>` (WRITE) | **P0 churn** — reformats all 10.7k lines of `orchestrator.py` per edit, destroys surgical diff | `ruff format --check` + `ruff check --no-fix` on the single file → `additionalContext` only, NEVER write, NEVER block |
| C2 | `verify-quality-gate.sh` Stop hook, no `stop_hook_active` | **P0 self-deadlock** — loops until the 8-block cap | First line: read stdin, `if stop_hook_active → exit 0`; advisory by default; back with CI |
| C3 | deny `Edit(.claude/settings.json)`, `Edit(.claude/hooks/**)`, `Edit(BINDING_RULES.md)`, `Edit(CONSTRAINTS.md)` | **P0 false-block** of user-directed canon maintenance (deny>ask, no exceptions) | Drop the denies. `.claude/**`, `.mcp.json`, `.claude.json`, `.pre-commit-config.yaml`, `.git` are **built-in PROTECTED PATHS** (already prompt, never auto-approved except bypass) → no rule needed. For docs-resident canon use `ask`, not deny |
| C4 | hooks are `bash`+`jq` | **P0 on Windows** — jq not guaranteed; `pwsh -File` Stop hooks get EMPTY stdin (#46601) | Author hooks in **Node `.mjs`** (exec form `command:"node"`) OR Git-Bash+venv-Python; never jq; never `pwsh -File` for stdin. `.gitattributes`: `*.mjs *.sh *.py text eol=lf` |
| C5 | (research recommended) `disableBypassPermissionsMode:"disable"` + `disableAutoMode:"disable"` | **NO-GO** vs the mandate — would block the user's autonomous full-bypass runs | OMIT both. Keep bypass/auto available; teeth live in hooks (which fire in bypass) + CI |
| C6 | (research) author all hooks in Node "because Node is always present" | **REFUTED** — the native/WinGet installer ships a self-contained binary; Node only for the npm path | Don't assume any runtime. Fail-OPEN: every hook try/catch → exit 0 on parse-fail/missing-runtime. On Ultron, Git Bash + the `.venv` Python are the hard-guaranteed pair |

### Hallucinations the adversarial layer caught (do NOT propagate)
- **`delegate` is NOT a permission mode** (research invented it). Real modes: `default, acceptEdits, plan, auto, dontAsk, bypassPermissions`.
- **"PostToolUse `additionalContext` is broken (#3983)"** — REFUTED; it works per current docs. Use it as the default advisory channel.
- **`disableAllHooks` bypasses managed hooks (#26637)** — CONFLICT (one lens refuted it against current docs: managed hooks survive). Don't assert it; the CI-backstop conclusion stands regardless.
- **auto-mode "0.4%/8.5% two-stage" FP numbers, `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`, several CVE numbers** — version-uncertain / not on official pages. Cite behaviors, not numbers; mark `# UNVERIFIED`.

## 2. Confirmed mechanics (build on these — verified vs code.claude.com)
- Permissions: `deny > ask > allow`, first-match, **a deny cannot carry allow-exceptions**; rules **MERGE across all 5 scopes** (managed>CLI>local>project>user). A **bare** tool deny (`"Bash"`, `"WebFetch"`, `"Agent"`, `mcp__*`) removes the tool from context entirely — never in a shared bundle.
- `stop_hook_active` is REAL (hooks-GUIDE page; the reference page truncates it). 8-block cap exists. Stop input also carries `background_tasks` + `session_crons` → never `decision:block` while those are non-empty.
- `PostToolUse` cannot undo a write (advisory); `additionalContext` + `updatedToolOutput` (redaction) work. `PreToolUse` `permissionDecision: allow|deny|ask` (+`defer` only in `-p`), `updatedInput` rewrites args.
- **Protected paths** (built-in): `.claude`, `.mcp.json`, `.claude.json`, `.pre-commit-config.yaml`, `.git`, `.gitconfig`, shell rc — never auto-approved except in bypass; allow rules don't pre-approve them.
- `SessionStart` injects context via **stdout** (command hooks), matchers `startup|resume|clear|compact`; **PostCompact CANNOT inject context** (side-effects only) → do post-compaction reground in `SessionStart` (source `compact`), not PostCompact.
- Bash deny matching IS shell-operator aware (splits `&& || ; |`, strips `VAR=`, walks `$()`/backticks) but argument-constraining patterns are fragile vs interpreter-wrap (`python -c`) → deny is the hard gate for *direct* invocations; hooks are defense-in-depth, fail-open.
- `Bash(command:...)` param rules are IGNORED with a startup warning — always use specifier form `Bash(rm -rf *)`.
- Hooks: fail-open by default; same-matcher hooks run in parallel + dedup; merge `deny>ask>allow`; `async:true` for non-blocking; per-event timeouts (UserPromptSubmit 30s); production ceiling 3-5 → use DISPATCHERS.
- CI required-status-checks ("do not allow bypassing") = the one un-overrideable layer (local settings / `disableAllHooks` / `--dangerously-skip-permissions` can defeat in-session hooks).

## 3. The final bundle (maximum teeth / zero blocker) — shared shape, per-consumer split
**Two dispatchers + four advisory hooks (≤6, fail-open, Node/.mjs or bash+python; no jq):**
- `PreToolUse` dispatcher (`matcher:"Bash|Edit|Write|MultiEdit|WebFetch"`): (a) dangerous-git deny after quote-stripping (`--no-verify`, `push -f/--force`, `reset --hard`, `checkout -- .`, `clean -f`, `rm -rf /|~`); (b) secret-write scan on Edit/Write; (c) **Ultron**: anticheat-import scan on voice-path files + one-instance guard (`python -m kenning` while port 8772 held → `ask`) + curl/wget/Invoke-WebRequest block; (d) WebFetch SSRF guard (DNS-resolve → block RFC-1918/loopback/link-local/cloud-metadata/IPv6-mapped, fail-CLOSED for that one check). `permissionDecision:deny`, fail-open elsewhere.
- `PostToolUse` dispatcher (`Edit|Write|MultiEdit` → ruff `--check`/`check --no-fix` + stub-scan-on-changed-lines → `additionalContext`, capped; `Read|Bash|mcp__*` → secret-redact `updatedToolOutput`). **Never block.** `async` where possible.
- `SessionStart` (`startup|resume|clear|compact`) → stdout reground: CONSTRAINTS first line + anticheat stance + "reground from STATUS.md + CONSTRAINTS.md". The belt-and-suspenders for "every new session reads the canon."
- `PreCompact` (`manual|auto`, never block on auto) → snapshot `STATUS.md`+`docs/ultron_1_0/CONSTRAINTS.md` → `.claude/snapshots/` + jsonl.
- `Stop` → `stop_hook_active`→exit 0; if `background_tasks`/`session_crons` non-empty → advisory only; else ruff summary of changed .py via `additionalContext`. **Never `decision:block`** in v1 (advisory-first; CI is the gate).
- (optional) `SubagentStop` async audit JSONL.

**permissions:** `allow` = read-only + narrow safe commands (the test wrapper, `git status/diff/log`, ruff/mypy) — narrow so they survive auto-mode. `ask` = `Edit(docs/canon/**)`, `Edit(docs/ultron_1_0/CONSTRAINTS.md)`, `git push *`, dep installs. `deny` = secrets (`Read(**/.env*)`, `Read(**/*.pem|*.key)`, `Read(~/.ssh/**)`, `~/.kenning/spotify.json`) + dangerous-git specifiers + (Ultron) `Bash(curl *)/Bash(wget *)/PowerShell(Invoke-WebRequest *)`. **No** `Edit(.claude/**)` deny; **no** bare tool denies; **no** `disableBypassPermissionsMode`. `defaultMode:"default"`.

**CI backstop** (`.github/workflows`, required checks, no-bypass): no-test-deletion guard, stub-scan-on-diff, lockfile/hash-pin guard, secrets (gitleaks pinned), ruff/mypy on changed files. The override-proof layer.

**ruff/mypy** (pyproject): `ruff` "stop-the-bleeding" + `extend-per-file-ignores` grandfathering `orchestrator.py`; `mypy` ADVISORY/CI-only, full-project with `[[tool.mypy.overrides]] ignore_errors=true` for the legacy modules (mypy errors are transitive → never changed-files-only in a blocking hook), `disallow_untyped_defs=true` globally + relaxed on legacy ("stop the bleeding").

## 4. Consumer split
- **Ultron** (Windows, anticheat, solo): adds the 3 Ultron-only PreToolUse checks (anticheat-import, one-instance, curl/wget block); hooks WRAP the existing gates (pre-push hygiene, `validate_config`, golden digest, flavor-lint, import-firewall+canary, `test_anticheat`) — never duplicate. No managed tier (solo) → CI is the backstop. Sandbox unavailable on native Windows → the PreToolUse SSRF/DNS hook is the only egress boundary.
- **Kit** (cross-platform, web-heavy): keep WebSearch/WebFetch ALLOWED (deep research); SSRF guard + optional sandbox network allowlist on macOS/Linux; runtime DECISION PROCEDURE (not a single hardcoded runtime); ship a separate `managed-settings.json` template for orgs (`allowManagedPermissionRulesOnly`, `strictPluginOnlyCustomization`) — documented as managed-only.

## 5. Go / No-Go (the zero-loss gate)
- **GO (teeth, zero loss):** PreToolUse dangerous-git deny; secret deny + write-scan + output-redact; Ultron anticheat-import + one-instance + curl/wget block; SSRF guard; PostToolUse advisory ruff/stub; SessionStart reground; PreCompact snapshot; Stop advisory; CI backstop; ruff/mypy ratchet; ASK on docs-canon.
- **NO-GO (cut — would cost capability/autonomy or is cargo-cult):** `disableBypassPermissionsMode`/`disableAutoMode`; any bare `Bash`/`WebFetch`/`WebSearch`/`Agent`/`mcp__*` deny in the shared bundle; `Edit(.claude/**)` deny; write-mode auto-format; blocking Stop/PostToolUse in v1; `WorktreeCreate` hook (replaces git, non-zero exit breaks creation); CaMeL/MELON/spotlighting on Ultron (no untrusted-web leg while gaming) — keep for the Kit only; the hallucinated `delegate` mode.
- **NEEDS-CHANGE before ship:** every hook → fail-open + Windows-correct runtime + LF `.gitattributes`; cite no unverified CVE/percent numbers; test_map demoted to advisory hint (the 70% figure is one non-peer-reviewed preprint), built hybrid (coverage contexts seeded out-of-band + static AST), never gating the CI sweep.

## 6. Open items (verify on the installed CC version before activation; `# UNVERIFIED`)
8-block-cap default + `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`; `disableAllHooks` managed-bypass (#26637); cited CVE numbers; `defer`/`asyncRewake` exact semantics; whether `node` is on PATH in the hook env on this box (else use bash+venv-python). **Activation rule (P22 enforcement probe): run a throwaway action that SHOULD be blocked and confirm exit 2 / the advisory fires, for EACH hook, before trusting it.**
