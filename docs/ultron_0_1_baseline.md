# Ultron 0.1 — Stable Baseline: restore & launch runbook

> **What this is.** `Ultron 0.1` is the designated **stable, restorable baseline** of
> the Valorant teammate-relay assistant in its **lean-boot, gaming-engaged,
> anticheat-default** state — the most stable and reliable Ultron has ever been.
> If development regresses or breaks, this is the known-good build to fall back to.
>
> **Pinned at commit `816df7c`** — git tag **`ultron-0.1`**, pinned branch
> **`release/ultron-0.1`**, GitHub release
> <https://github.com/1v9Khan/ultronPrototype/releases/tag/ultron-0.1>, and a
> standalone launchable backup at **`E:\Ultron-0.1\`**.
>
> **This is a hard, intentional checkpoint.** Treat the tag/branch/release/E: backup
> as immutable. Do not move or delete them.

---

## TL;DR (operator / agent quick reference)

- **"Restore us to Ultron 0.1" / "rewind to Ultron 0.1"** → rewind the dev tree
  (`C:\STC\ultronPrototype`) to the tag. See **§1**.
- **"Launch Ultron 0.1"** → boot the **standalone backup** at `E:\Ultron-0.1` via its
  launcher, **without touching the dev tree**. See **§2**. This is the rule: *launch
  Ultron 0.1 = launch from the E: backup, never the in-development version.*
- **"Launch Ultron 0.1.1"** → boot `E:\Ultron-0.1.1\launch_ultron_0_1_1.ps1` — the same
  stable baseline **plus a voice model-lab** to A/B abliterated Qwen LLMs (tag
  `ultron-0.1.1` @`6ead83f`, branch `release/ultron-0.1.1`). Lab voice cmds (a switch
  VERB is required): "switch to / load / try **heretic** (4B) / **josiefied 4B** /
  **huihui** (7B) / **josiefied 8B** / the **3B**", or "switch to **model two..five**";
  all default CPU; "switch the model to the GPU/CPU" moves the current one. All model
  GGUFs live in the shared `E:\UltronModels\`. Restore the dev tree to it:
  `git checkout ultron-0.1.1`.
- Only **one** Ultron runs at a time (shared embedder port 8772 / wake word / audio
  devices / PTT HID). Stop any running Ultron before launching another.

> **C: model relocation (pending):** all model GGUFs were COPIED to `E:\UltronModels\`
> on 2026-06-19 (non-destructive — the live 0.1 stream kept reading `C:\…\models`). To
> free ~25 GB on C: once 0.1 is stopped: replace `C:\STC\ultronPrototype\models` with a
> directory junction → `E:\UltronModels` (so dev + 0.1 + 0.1.1 all share the E: store).
> Do NOT do this while any Ultron is running from C:.

---

## 1. Restore the development tree to Ultron 0.1

Use this to **rewind active development** back to the baseline (e.g. a change regressed
Ultron and you want main back to known-good).

```powershell
cd C:\STC\ultronPrototype
git fetch --all --tags

# OPTION A — inspect/run the baseline without moving main (detached):
git checkout ultron-0.1

# OPTION B — hard-rewind main to the baseline (DISCARDS newer main commits;
#            they remain reachable via reflog / other branches):
git checkout main
git reset --hard ultron-0.1
# then, to publish the rewind:  git push --force-with-lease origin main
```

Models, the venv, and voice assets are **gitignored and stable**, so restoring the
**code** to the tag fully restores Ultron 0.1's runtime behavior — no model re-download
needed. After restoring, launch normally: `python -m kenning`.

> Safety: if you have uncommitted dev work to keep, `git stash` first (or create a
> branch at the current tip: `git branch wip/<name>`), so Option B doesn't lose it.

---

## 2. Launch the standalone Ultron 0.1 backup (E: drive)

Use this to **stream a known-good Ultron** while the dev version is mid-maintenance —
it runs entirely from `E:\Ultron-0.1` and never touches `C:\STC\ultronPrototype`.

```powershell
E:\Ultron-0.1\launch_ultron_0_1.ps1
```

What it does: runs the backup's code (`E:\Ultron-0.1\src`, `PYTHONPATH`-shadowed so it
loads instead of the dev tree's editable install) using the main checkout's shared venv
and the stable model weights (shared via the `models\` + `ultronVoiceAudio\` directory
junctions), loads the backup's `.env`, and boots `python -m kenning` hidden/detached,
logging to `E:\Ultron-0.1\logs\`. A healthy boot reaches
`anticheat posture OK → gaming engaged → waiting_for_wake_word`.

> **Stop the dev instance first.** Two Ultrons can't co-exist (port 8772 / wake / audio
> / PTT). Kill only `python` processes whose command line contains `-m kenning` (tight
> filter — never `Stop-Process -Name python -Force`, which can hit Claude's own shells).

> **First-run caveat.** The launcher was wired up during an automated checkpoint session
> that does not boot the voice stack unattended, so it was not boot-tested. Verify on
> first use. If anything is off, the **guaranteed** fallback is §1 (restore the tag into
> the dev tree and launch normally — that path reuses the exact same venv/models).

Backup contents and disaster-recovery notes: `E:\Ultron-0.1\README_ULTRON_0_1.md`.

---

## 3. What "Ultron 0.1" captures (posture at `816df7c`)

- **Lean gaming boot** — desktop / coding / OpenClaw / memory / intent stacks are
  import-gated OFF; only the relay essentials load.
- **Anticheat firewall installed + enforcing** (fail-safe; refuse-to-start if it can't
  enforce while active). Deterministic-first relay (~85% of callouts resolve with no LLM).
- **Flavor tails default OFF** for the running app (crisp competitive callouts;
  `KENNING_FLAVOR_TAILS`, toggle by voice "flavor on/off").
- **Wake word required** (follow-up window OFF); **capture-stall watchdog** active.
- **PTT armed** via `.env` (`KENNING_PTT_ENABLED=true`, rawhid HID-only, VID 0x1209).
- **STT** faster-whisper large-v3-turbo (CUDA); **TTS** fine-tuned Kokoro Ultron voice
  (GPU); **LLM** llama-3.2-3b-abliterated on CPU; **embeddinggemma** sidecar (loopback 8772).
- Tests green at baseline; `docs/codebase_structure.md` validating-HEAD current to this line.

---

## 4. Re-creating the artifacts (if ever needed)

```powershell
# git tag + pinned branch (already exist; only if recreating)
git tag -a ultron-0.1 816df7c -m "Ultron 0.1 - stable lean-gaming/anticheat baseline"
git branch release/ultron-0.1 816df7c
git push origin ultron-0.1 release/ultron-0.1
gh release create ultron-0.1 --title "Ultron 0.1 - Stable Baseline" --notes-file <notes>

# E: standalone backup
git clone --no-local C:\STC\ultronPrototype E:\Ultron-0.1
cd E:\Ultron-0.1; git checkout ultron-0.1; git remote set-url origin https://github.com/1v9Khan/ultronPrototype.git
Copy-Item C:\STC\ultronPrototype\.env E:\Ultron-0.1\.env
New-Item -ItemType Junction -Path E:\Ultron-0.1\models -Target C:\STC\ultronPrototype\models
New-Item -ItemType Junction -Path E:\Ultron-0.1\ultronVoiceAudio -Target C:\STC\ultronVoiceAudio
C:\STC\ultronPrototype\.venv\Scripts\python.exe -m pip freeze > E:\Ultron-0.1\requirements-frozen-ultron-0.1.txt
# (launcher + README are committed in the E: backup)
```

---

*Companion: the post-0.1 latency/quality roadmap lives in
[`docs/latency_optimizations_V1.md`](latency_optimizations_V1.md).*
