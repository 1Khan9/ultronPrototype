# Anticheat-safe local AI for competitive games in 2026

**Research date:** 2026-06-20  
**Scope:** Riot Vanguard (Valorant), EasyAntiCheat (EAC), BattlEye — what process behaviors are safe vs flagged for a fully-local voice-first AI teammate relay (Ultron 1.0 architecture: in-process 8B LLM via llama-cpp-python, always-on mic capture, VoiceMeeter audio relay, EmbeddingGemma sidecar, Kokoro TTS, zero game-memory access).

---

## TL;DR recommendation for Ultron 1.0

**Ultron 1.0 as designed is anticheat-safe.** The decisive factor is the boundary it does not cross: it never touches game process memory, never injects code or DLLs into the game process, never sends synthetic input events (SendInput/NtUserSendInput), and never hooks game APIs. All compute is in a separate user-mode process (the Python orchestrator) that only reads from microphone audio and writes to a virtual audio device (VoiceMeeter) and speakers.

Safe (confirmed by research):

- In-process 8B LLM inference (llama-cpp-python / llama.cpp, CUDA, separate user-mode process)
- Always-on microphone capture (standard Windows audio APIs: MME / WASAPI)
- VoiceMeeter + VB-Cable virtual audio routing (user-mode WDM audio driver, no kernel exploits)
- Kokoro TTS → WASAPI output (pure audio output, no game process interaction)
- EmbeddingGemma sidecar (separate process, no game memory touch)
- Discord running alongside (Discord re-engineered its overlay to avoid game hooks)
- OBS via Display Capture (not Game Capture, which injects)

Risky / must avoid:

- Any call to `NtUserSendInput` / `SendInput` for simulated keystrokes or mouse movement into the game (Vanguard hooks this syscall; PTT must go via physical USB HID — hardware Leonardo)
- Process injection / DLL injection into Valorant (instant flag)
- Reading Valorant process memory (ObRegisterCallbacks strips PROCESS_VM_READ)
- Screen capture via game capture hook / DirectX hook (flagged; use display capture)
- Running from `\Desktop\`, `\Temp\`, `\Downloads\` paths (BattlEye path heuristic)
- Unsigned kernel drivers alongside a protected game
- Macros that output to the game via software (periodic/frame-aligned timing is detected)

---

## Findings (detailed)

### 1. What anticheat systems actually monitor

All three major kernel-level anticheats (Vanguard, EAC, BattlEye) share a common detection surface but differ in aggressiveness and timing.

**Shared detection surface across all three:**

| Detection vector | Mechanism | All three? |
|---|---|---|
| Process creation monitoring | `PsSetCreateProcessNotifyRoutineEx` kernel callback — fires on every new process | Yes |
| Loaded DLL / driver monitoring | `PsSetLoadImageNotifyRoutine` — flags injection of unlisted DLLs | Yes |
| Game memory scanning | Walk VAD tree or `NtQueryVirtualMemory` — detect executable private memory outside known modules | Yes |
| Inline hook detection | Compare function prologues in memory vs on-disk PE; look for `0xE9` (JMP) opcode | Yes |
| Import Address Table (IAT) hook detection | Compare import table entries vs expected DLL exports | Yes |
| Process handle restrictions | `ObRegisterCallbacks` strips `PROCESS_VM_READ`, `PROCESS_VM_WRITE`, `PROCESS_DUP_HANDLE` from any handle to the game | Vanguard + EAC |
| Driver blocklist | Block known vulnerable signed drivers at boot | Vanguard (boot-time), EAC (game launch) |

Sources: [Adrian's Security Research — How Kernel Anti-Cheats Work](https://s4dbrd.github.io/posts/how-kernel-anti-cheats-work/), [Arxiv 2408.00500 (ACM MATE 2024)](https://arxiv.org/html/2408.00500v1)

**Vanguard-specific (most aggressive):**

Vanguard (`vgk.sys`) loads at Windows boot via a service, not at game launch. This gives it visibility over every driver loaded after Windows starts. Key Vanguard-specific behaviors (sourced from April 2025 reverse-engineering: [archie-osu.github.io](https://archie-osu.github.io/2025/04/11/vanguard-research.html)):

- Hooks `HalPrivateDispatchTable` (context switch monitoring via `KiClearLastBranchRecordStack`)
- Hooks `HalCollectPmcCounters` to intercept syscalls (PatchGuard-compliant technique)
- Intercepts specific syscalls at the Win32k layer:
  - **`NtUserSendInput`** — software input injection (THIS IS THE CRITICAL ONE FOR PTT)
  - `NtGdiBitBlt` — pixel-level game screen reading
  - `NtGdiGetPixel` — pixel reading
  - `NtGdiDdDDIPresent` — monitor frame presentation
  - `NtGdiDdDDIOutputDuplGetFrameInfo` — DXGI output duplication (screen capture)
  - `NtUserGetWindowDisplayAffinity` — window capture protection queries
  - `NtAllocateVirtualMemory`, `NtFreeVirtualMemory`, `NtMapViewOfSection` — memory operations
  - `NtSuspendThread`, `NtSuspendProcess` — execution control
- Explicitly targets "input device drivers for macro or injection patterns" [VMX blog 2026]

**EAC-specific:**

- Loaded as a DLL injected into the game process (`EasyAntiCheat.dll`) — can see all game-internal changes
- Kernel driver loads at game launch, unloads at game exit (not boot-persistent like Vanguard)
- Behavioral ML models updated continuously; cloud-based analytics
- Process hollowing detection
- Hardware ID (HWID) bans — ban encompasses the hardware, not just the account
- Module scanning every ~30–60 seconds

**BattlEye-specific (sourced from 2019 reverse-engineering article, still architecturally valid):**

- `BEClient.dll` mapped into game process; `BEDaisy.sys` kernel driver
- Process enumeration via snapshot: checks running processes against a named blocklist
  - Blocklisted parent processes: `steam.exe`, `explorer.exe`, `lsass.exe`, `cmd.exe`
  - Path heuristics: processes running from `\Desktop\`, `\Temp\`, `\Downloads\` flagged
  - Named blacklist patterns: `"Loadlibr"`, `"RNG "`, `"TempFile.exe"` in image name
- Window title enumeration via `GetTopWindow`/`GetWindow` — blacklisted strings include known cheat tool window titles
- Scans `lsass.exe` for executable memory outside modules
- Pattern scanning for strings: `"PlayerESPColor"`, `"NameESP"`, `"AimBot"`, etc.
- Module blocklist: `nvToolsExt64_1.dll` (Nsight profiling), `ws2detour_x96.dll`, `nxdetours_64.dll`, `nvcompiler.dll`
- Heartbeat integrity check on BEClient itself
- Network connection monitoring (specific cheat provider IPs)
- Runtime memory scan every 30–60 seconds

Source: [secret.club BattlEye analysis](https://secret.club/2019/02/10/battleye-anticheat.html)

### 2. What anticheat systems do NOT monitor (confirmed or strongly implied)

Based on the research, the following behaviors are NOT in the detection surface:

**Audio I/O (strong negative evidence):**

No research source found any documentation of Vanguard, EAC, or BattlEye scanning, blocking, or flagging:
- WASAPI audio capture/output APIs
- Virtual audio devices (VB-Cable, VoiceMeeter, NVIDIA Broadcast)
- Audio driver enumeration beyond blocking specifically exploitable signed drivers
- Microphone capture processes

The academic survey of kernel anticheat rootkit behavior ([Arxiv 2408.00500v1]) notes that audio APIs are not relevant to the core cheat-prevention surface. An older antimalware analysis paper (Arxiv 1906.10625) explicitly noted that antivirus sandboxes "omit audio device enumeration APIs from implementation since audio APIs are not relevant to malware execution" — the same logic applies to anticheats whose threat model is aimbot/wallhack, not audio capture.

**VoiceMeeter / VB-Cable status:** No ban reports found linking these tools to Valorant, EAC, or BattlEye bans. VB-Cable operates as a standard WDM audio driver (supports MME/KS/DX/WASAPI). It installs via the standard Windows audio driver model, not via a vulnerable kernel driver exploit. Multiple years of community usage across Valorant with no documented bans from VoiceMeeter.

**In-process compute (LLM inference):**

A process running llama-cpp-python / llama.cpp:
- Does not inject into the game process
- Does not hook any game API
- Does not read game process memory
- Uses standard CUDA compute (indistinguishable from any GPU-accelerated application)
- Uses the same memory allocation patterns as 3D engines, ML frameworks, video editors

Anticheat process enumeration would see this process but has no basis to flag it: its name/path is user-controlled (avoids the path heuristics), it has no known cheat signatures, and it does not exhibit injection behavior.

**Behavioral compute on separate process:** EmbeddingGemma sidecar is a subprocess launched by the orchestrator. Same analysis applies — separate process, no game memory access, no hooks.

**Microphone capture (faster-whisper, PortAudio):**

PortAudio/WASAPI/MME microphone capture: standard Windows audio API usage. Not in any anticheat detection surface found in research. Thousands of streaming/recording applications do exactly this while games with kernel anticheats run.

### 3. The critical risk: input injection vs audio output

The sharpest safe/unsafe boundary in anticheat is between:

**OUTPUT PATH (AUDIO) — safe:**
```
orchestrator → Kokoro TTS → WASAPI audio output → VoiceMeeter B-bus → Valorant mic input
```
This path never touches the game process. It is 100% audio I/O. Vanguard has no hook on WASAPI audio output APIs. The relay message is delivered as audio arriving at Vivox (Valorant's VOIP) from an external "physical" audio device as far as Vanguard is concerned.

**INPUT PATH (PTT KEY) — the risk:**

If Ultron needs to press a push-to-talk key programmatically (e.g., hold VOIP hotkey while speaking), there are two approaches:
- **Safe:** Hardware USB HID device (Leonardo/Arduino HID keyboard) — sends USB HID reports that are physically indistinguishable from genuine keyboard hardware. Vanguard's `NtUserSendInput` hook is at the Win32k layer, below which hardware HID reports originate from the kernel USB driver stack. The signal path bypasses the hook.
- **UNSAFE:** `SendInput()`, `keybd_event()`, or any user-mode API that goes through `NtUserSendInput` — Vanguard hooks this exact syscall. Would be detectable.

Vanguard confirmed hooks `NtUserSendInput` ([archie-osu research, April 2025](https://archie-osu.github.io/2025/04/11/vanguard-research.html)). The Ultron codebase already uses a physical Leonardo HID device for PTT with `rawhid` backend — **this is the correct anticheat-safe approach and must be maintained.**

Vanguard's Hall Effect keyboard research ([attackshark.com]) confirms the key detection principle: "Vanguard's primary detection focus is not the speed of the reset, but the periodicity of the signal" — software macros produce frame-aligned periodic intervals; real HID hardware produces humanlike variance. The Leonardo with `release_jitter_ms 60` provides this variance.

### 4. Vanguard 2026 updates: IOMMU enforcement and planned user-mode migration

**IOMMU enforcement (May 2026, active now):**

Vanguard's most aggressive 2026 update targets Direct Memory Access (DMA) cheat hardware — PCIe devices that read game memory from a second computer. Vanguard now enforces IOMMU, triggering BSOD and firmware corruption on DMA cheat devices that masquerade as SATA/NVMe controllers.

**Impact on Ultron:** None. Ultron has no PCIe DMA hardware component. IOMMU enforcement requires the feature be enabled in BIOS (required to play Riot games going forward) but has no effect on legitimate PCIe devices like the RTX 4070 Ti.

**User-mode migration (planned 2026):**

Vanguard's kernel stub is being shrunk to <50 KB ("loads only for forensic snapshots"). Heavy ML-based detection moves to user-mode processes. Timeline: Phase I hybrid Q3 2025, Phase II full user-mode Q1 2026 [klizosolutions Medium].

**Impact on Ultron:** Potentially positive. A user-mode Vanguard process is less capable of arbitrary process scanning than a ring-0 driver. The planned architecture uses transformer-based anomaly detectors, gradient boosting models, and GNNs for behavioral biometrics — these analyze gameplay input patterns (mouse entropy, recoil heatmaps), not background audio/compute processes.

**AI-based behavioral detection (server-side):**

Vanguard correlates client-side data with server-side ML models in real time. GPU-accelerated ensembles spot "sub-pixel aimbot behavior in under 50ms." These models analyze:
- Mouse entropy and recoil heatmaps
- Input pattern timing and consistency
- Gameplay statistics vs. population baselines

**Impact on Ultron:** Zero. Ultron generates zero game inputs (no mouse, no aim assistance, no keyboard macros into game). Server-side behavioral models have nothing unusual to flag because Ultron's human player's in-game behavior is unchanged.

### 5. What overlays and third-party apps are doing correctly (model for Ultron)

**Discord overlay:** Discord re-engineered its overlay in 2025 to avoid "hooking" into game processes, which had caused prior conflicts with anticheat systems. Approach: external window composition rather than in-process injection.

**Overwolf:** Works with Riot to ensure official Appstore apps comply with ToS. Technically, Overwolf moved away from traditional code injection to inject "only when a window is visible" rather than constant process hooks. Apps that use Riot's official API (spectator, replay, LCU) are explicitly allowed; apps that "read memory" are explicitly blocked per Riot's Vanguard FAQ.

**The key principle:** Any app that operates entirely outside the game process — using only public APIs (audio, display, network) without reading game memory — is structurally safe. Ultron fits this profile exactly.

### 6. Known risks and edge cases

**Vanguard audio driver interference (2025 bug reports):**

There are reported cases of Vanguard causing audio cutouts in Discord and other applications during Valorant sessions, persisting until reboot. This is an unintended side effect of Vanguard's kernel driver affecting audio subsystems, NOT Vanguard detecting or banning audio software. VoiceMeeter users may experience audio routing issues that require a system restart — this is a stability concern, not a ban risk.

**BattlEye Focusrite conflict (late 2025/early 2026):**

BattlEye's kernel driver conflicts with Focusrite USB audio interface drivers in certain Windows 11 versions, causing kernel stop errors (0x139). This is a driver compatibility bug, not an anticheat detection action. VoiceMeeter/VB-Cable use different driver architecture (virtual WDM, not USB audio class) and are not known to trigger this specific issue.

**Vanguard blocking input device drivers:**

When Vanguard launched for League of Legends, it blocked a signed keyboard driver (used for per-key lighting + macros) because cheaters were exploiting signed drivers as injection vectors. Riot released a hotfix when legitimate users were affected. Virtual audio drivers (VB-Cable) are not in this threat category — they are not used as injection vectors and not reported to be blocked.

**Process path heuristics (BattlEye):**

BattlEye flags processes with paths containing `\Desktop\`, `\Temp\`, `\Downloads\`. Ultron must be installed in a stable path (e.g., `C:\STC\ultronPrototype\`) — which it is. This heuristic specifically targets temporarily placed cheat tools, not permanent software installations.

**Import firewall and pytesseract (pre-existing Ultron issue, resolved):**

Ultron's own internal firewall (`_firewall.py`) was previously configured to hard-block `pytesseract` and other desktop imports, and a `find_spec()` probe from transformers' import-time code triggered the firewall raise — causing a cascade failure. This is an Ultron-internal issue (resolved in `0b5da79`) and unrelated to anticheat, but illustrates the importance of keeping the import firewall probe-safe.

---

## Concrete techniques/params we should adopt

### Anticheat architecture checklist for Ultron 1.0

1. **Process isolation: MAINTAIN**
   - Keep the entire Ultron orchestrator, LLM, STT, TTS stack in a separate Python process. Zero game process interaction.
   - No DLL injection, no process-handle opening to Valorant, no memory reads.

2. **PTT: HARDWARE HID ONLY**
   - The Leonardo USB HID keyboard device for PTT is the correct approach. `PttConfig.backend = 'rawhid'` pinned (per memory).
   - `release_jitter_ms = 60` provides human-like variance defeating periodicity detection.
   - NEVER add a software PTT fallback using `SendInput`, `keybd_event`, `win32api.keybd_event`, or any similar API.
   - If Leonardo is disconnected, log a warning and disable PTT entirely — do not fall back to software injection.

3. **Audio I/O: WASAPI output path is safe**
   - Current Ultron audio path (Kokoro → WASAPI → VoiceMeeter B-bus) is anticheat-safe.
   - Use standard Windows audio APIs (WASAPI low-latency as implemented in `audio_output.py`).
   - Keep the import firewall excluding desktop audio monitoring libraries.

4. **VoiceMeeter relay: SAFE as designed**
   - VoiceMeeter VirtualAMPMixer acts as a virtual audio endpoint. No game process interaction.
   - Keep `KENNING_RELAY_VM_LEVEL_GUARD` default OFF (VoiceMeeter Remote API is anticheat-clean but optional).
   - Known stability risk: Vanguard may cause audio subsystem disruptions requiring restart — not a ban risk.

5. **Screen/pixel reading: DO NOT ADD**
   - Vanguard hooks `NtGdiBitBlt`, `NtGdiGetPixel`, `NtGdiDdDDIOutputDuplGetFrameInfo`.
   - Never add any game screen reading (pixel color, map state, HUD parsing) to Ultron.
   - If a future feature needs game-state context, use game audio (team voice) or public spectator API, not screen capture.

6. **LLM inference: SAFE as designed**
   - llama-cpp-python in-process inference via CUDA (RTX 4070 Ti) is structurally identical to any GPU-accelerated user application.
   - Keep the model file in `C:\STC\ultronPrototype\models\` or the shared `E:\UltronModels\` store — NOT `\Desktop\`, `\Temp\`, `\Downloads\`.
   - Keep the orchestrator main entry at a stable path — the Python `__main__` call is safe.

7. **EmbeddingGemma sidecar: SAFE as designed**
   - Separate subprocess launched by orchestrator with `KENNING_EMBEDDER_PARENT_PID` for orphan prevention.
   - No game memory access; standard Python subprocess with IPC.

8. **Import firewall: KEEP STRICT**
   - Never import `pyautogui`, `pydirectinput`, `win32api` (input injection), `pytesseract`, `pygetwindow` (game window enumeration for screen reading), or similar in the relay/intent path.
   - These are the kinds of libraries that, if present in the process's loaded modules, could attract scrutiny in a BattlEye module scan.

9. **Process name / path hygiene**
   - Main process: `python.exe` (or `pythonw.exe`) from a stable Python installation. Not suspicious.
   - Do not rename executables to anything resembling known cheat tool names.
   - Ensure production builds don't live in temp directories.

10. **Overlay/GUI: AVOID in-game injection**
    - Current Ultron GUI (STOP window, config overlay) is a separate window, not a game-injected overlay. Keep it this way.
    - The EPHEMERAL config overlay must not use any DirectX hook or game window attachment.

---

## Risks/caveats for our constraints

### Risk 1: Vanguard audio subsystem side-effects (LOW ban risk, MEDIUM stability risk)
- Vanguard's kernel driver has caused audio cutouts in Discord and audio applications during Valorant play (2025 user reports).
- VoiceMeeter may be affected. If the audio route drops mid-match, Ultron becomes deaf/mute but is NOT banned.
- Mitigation: implement watchdog restart for VoiceMeeter connectivity; document restart-after-game procedure.

### Risk 2: PTT software fallback (HIGH ban risk if added)
- If someone adds a software PTT fallback using Windows APIs for key simulation, Vanguard will detect the `NtUserSendInput` call.
- The existing codebase correctly pins to `rawhid` backend. Any refactor that adds `SendInput` would be a ban-risk regression.

### Risk 3: BattlEye module scanning of process (LOW risk)
- BattlEye scans the game process's loaded modules, not external Python processes.
- However, BattlEye does process enumeration. Ultron appears as `python.exe` with a path in `C:\STC\...` — no red flags.
- The import firewall keeps suspicious libraries (detouring, injection, screen-reading) out of Ultron's loaded modules.

### Risk 4: Future screen-reading features (HIGH ban risk if implemented naively)
- Any future feature that reads game screen pixels would hit Vanguard's Win32k hooks (`NtGdiBitBlt`, `NtGdiGetPixel`, `NtGdiDdDDIOutputDuplGetFrameInfo`).
- Safe alternative for game state: game audio transcription (already the core Ultron approach), or Riot's official spectator/replay API.

### Risk 5: Vanguard user-mode migration may increase process monitoring breadth (UNKNOWN)
- As Vanguard moves its detection to user-mode processes, those processes may scan a wider range of external apps.
- Current ML models focus on gameplay behavioral biometrics (mouse, aim), not audio software.
- Watch Riot's changelogs for any new third-party process scanning post-migration.

### Risk 6: Hardware compatibility (VoiceMeeter driver conflicts)
- BattlEye had driver compatibility issues with Focusrite USB audio in late 2025. VB-Cable uses a different driver model and is not reported to conflict, but monitor Windows Update interactions with VoiceMeeter's virtual drivers.

### Risk 7: Policy risk (not technical ban risk)
- Riot's third-party app policy focuses on unfair advantages — game-state information processing, auto-actions.
- Ultron processes game AUDIO (team voice) to relay tactical callouts. This is within the same category as a human teammate relaying info verbally.
- Ultron does not access game memory, game API, or spectator feed for unfair information extraction.
- The IGNORE intent class (Ultron deliberately ignores teammate speech addressed to others) shows design intent toward fair-use.
- If Riot audited Ultron, the key question would be "does this process game state data?" — the answer must be "no, only audio of what any human teammate already hears."

---

## Sources (full URLs)

1. **Adrian's Security Research — How Kernel Anti-Cheats Work (deep technical)**  
   https://s4dbrd.github.io/posts/how-kernel-anti-cheats-work/

2. **arXiv 2408.00500v1 — "If It Looks Like a Rootkit" (ACM MATE 2024, peer-reviewed)**  
   https://arxiv.org/html/2408.00500v1

3. **archie-osu — Inside Riot Vanguard's Dispatch Table Hooks (April 2025, primary reverse-engineering)**  
   https://archie-osu.github.io/2025/04/11/vanguard-research.html

4. **secret.club — BattlEye Anti-Cheat Analysis (2019, architectural reference)**  
   https://secret.club/2019/02/10/battleye-anticheat.html

5. **Tweaktown — Vanguard IOMMU DMA firmware destruction (May 2026)**  
   https://www.tweaktown.com/news/111774/valorants-vanguard-anti-cheat-now-destroys-dma-cheat-firmware/index.html

6. **klizosolutions Medium — Vanguard User-Mode AI Protection Migration Plan**  
   https://klizosolutions.medium.com/user-mode-ai-protectionbeyond-the-kernel-vanguards-planned-shift-to-user-mode-ai-protection-d074139333ad

7. **Riot Games Official — Vanguard FAQ for Third Party Applications**  
   https://www.riotgames.com/en/DevRel/vanguard-faq

8. **Riot Games Official — Vanguard Motherboard Pre-Boot Gap Update**  
   https://www.riotgames.com/en/news/vanguard-security-update-motherboard

9. **Overwolf Compliance — Riot Games third-party app requirements**  
   https://dev.overwolf.com/ow-native/guides/game-compliance/riot-games/

10. **tateware.com — EAC vs BattlEye vs Vanguard vs RICOCHET comparison 2026**  
    https://tateware.com/blog/anti-cheat-comparison-2026

11. **VMX Cheats Blog — Anti-Cheat Systems Explained 2026**  
    https://store.vmx.gg/blog/anti-cheat-systems-explained-2026

12. **jaxon.gg — Voice changers and Valorant ban risk**  
    https://www.jaxon.gg/can-using-a-voice-changer-get-you-banned-in-valorant/

13. **PCGamingWiki — Anti-cheat middleware reference**  
    https://www.pcgamingwiki.com/wiki/Anti-cheat_middleware

14. **Esports News — Vanguard IOMMU BSOD update (May 2026)**  
    https://esports-news.co.uk/2026/05/22/riots-vanguard-update-has-bsod-cheater-hardware-after-nuking-dma-cheat-systems/

15. **Tom's Hardware — Vanguard DMA paperweight update (May 2026)**  
    https://www.tomshardware.com/software/valorant-dev-bans-players-who-spent-usd6-000-on-cheats-then-trolls-them-on-social-media-studio-tweets-congrats-to-the-owners-of-a-brand-new-usd6k-paperweight

16. **VB-Audio VB-Cable official site**  
    https://vb-audio.com/Cable/

17. **Gaijin community — BattlEye Focusrite driver conflict**  
    https://community.gaijin.net/issues/p/warthunder/i/oKQgjZP54pmF

18. **attackshark.com — Rapid Trigger & Vanguard Hall Effect analysis (input detection)**  
    https://attackshark.com/blogs/knowledges/rapid-trigger-vanguard-hall-effect-valorant

19. **GuidedHacking — Low-level mouse input methods anticheat bypass**  
    https://guidedhacking.com/threads/low-level-methods-of-sending-mouse-input-that-bypass-anticheat.14555/

20. **ACM 2025 — Battling The Eye: BattlEye Anti-Cheat Techniques (2025 workshop)**  
    https://dl.acm.org/doi/10.1145/3733817.3762701

21. **WJARR 2025 — AI-powered anti-cheat engines behavioral analysis**  
    https://wjarr.com/sites/default/files/fulltext_pdf/WJARR-2025-1747.pdf

22. **Overwolf Safety Statement**  
    https://support.overwolf.com/support/solutions/articles/9000182312-overwolf-won-t-get-you-banned
