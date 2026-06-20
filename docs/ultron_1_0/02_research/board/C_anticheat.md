# Anticheat Safety — Adversarial Verification for Ultron 1.0

**Layer:** C (Adversarial)  
**Adversary:** claude-sonnet-4-6  
**Date:** 2026-06-20  
**Goal:** Refute or qualify the B_anticheat_2026.md findings for our exact constraints (local 10 GB single RTX 4070 Ti, llama-cpp-python 0.3.22, abliterated Qwen3-8B, Vanguard/EAC/BattlEye, Valorant relay, always-listening mic capture, VoiceMeeter audio relay, EmbeddingGemma sidecar).

---

## Claims Examined

The B layer makes eight structurally important claims this review targets:

1. In-process 8B LLM inference (llama-cpp-python / CUDA) is anticheat-safe.
2. Always-on microphone capture via WASAPI/PortAudio is not in any anticheat detection surface.
3. VoiceMeeter + VB-Cable virtual audio routing will not cause a ban.
4. The EmbeddingGemma sidecar subprocess is safe.
5. Vanguard's user-mode migration (planned Q1 2026) reduces monitoring breadth for external processes.
6. PTT via hardware Leonardo HID is definitively safe; `NtUserSendInput` is the only risk vector.
7. Vanguard's "incompatible software" blocking is limited to kernel drivers, not user-mode processes.
8. Riot's policy threat is low because Ultron does not read game memory.

---

## Verdict Per Claim

### Claim 1 — In-process 8B LLM / CUDA is safe
**CONFIRMED WITH QUALIFICATION**

No evidence found of Vanguard, EAC, or BattlEye flagging llama-cpp-python, GGUF inference, or CUDA ML workloads in any user report, forum thread, or technical analysis. The January 2026 340,000-account ban wave trigger list (HWID spoofers, aim-assist tools, wallhacks, bot-leveled accounts) does not include AI inference software. GPU-accelerated ML is indistinguishable to the anticheat kernel driver from any other CUDA consumer application (game engine, video encoder, Stable Diffusion).

**Qualification — GPU contention is a stability risk, not a ban risk.** Running an 8B Q5_K_M model on the RTX 4070 Ti while playing Valorant will compete for VRAM and CUDA compute. Vanguard itself does not care. The GPU scheduler (Windows WDDM) preempts Ultron's inference for Valorant's render frames, which may cause visible LLM latency spikes during combat. This is not an anticheat issue but must be tested empirically on the 10 GB design cap.

**Qualification — Process name hygiene.** Vanguard's process-creation callback (`PsSetCreateProcessNotifyRoutineEx`) fires on every new process. Ultron appears as `python.exe` under `C:\STC\ultronPrototype\` — no documented flag pattern. However, Vanguard documentation confirms it logs process names for telemetry review. If Riot ever pattern-matched `python.exe` launching GPU compute alongside Valorant, a policy-level review could follow. No evidence this has happened, but it is not zero probability at scale.

---

### Claim 2 — Always-on WASAPI/PortAudio mic capture is not monitored
**CONFIRMED**

No anticheat source — including the primary reverse-engineering of Vanguard's Win32k hooks (archie-osu, April 2025), the ACM MATE 2024 peer-reviewed survey, and the secret.club BattlEye analysis — documents any hook, callback, or enumeration targeting audio capture APIs. The hooked Win32k functions are unambiguously input/display/memory operations:  `NtUserSendInput`, `NtGdiBitBlt`, `NtGdiGetPixel`, `NtGdiDdDDIOutputDuplGetFrameInfo`. WASAPI capture (`IAudioCaptureClient::GetBuffer`) does not appear.

Vanguard's voice-chat recording feature (2021 privacy update, confirmed active) records **in-game Vivox VOIP**, not microphone capture APIs at the OS level. This is Riot's own Vivox SDK behavior, not Vanguard kernel scanning. Ultron's mic capture is WASAPI input to the orchestrator process — entirely outside Vivox and invisible to Vanguard's recording system.

**One confirmed instability vector:** Multiple 2025 user reports describe Vanguard's `vgk.sys` driver causing audio subsystem disruptions — cutouts lasting 30 seconds or more affecting Discord and other audio apps, persisting until reboot. This is a kernel driver side-effect, not an anticheat detection action, and not a ban risk. VoiceMeeter operates in this same ecosystem and is susceptible to the same disruption. Runtime consequence: Ultron may go deaf or mute mid-match without any ban. Mitigation is a watchdog restart (already planned in the codebase).

---

### Claim 3 — VoiceMeeter + VB-Cable will not cause a ban
**CONFIRMED WITH QUALIFICATION**

No ban reports linking VoiceMeeter or VB-Cable to Vanguard, EAC, or BattlEye enforcement were found in any indexed source. VoiceMeeter's December 2025 release notes show active maintenance. The VB-Cable driver is a standard WDM virtual audio endpoint — not a vulnerable signed kernel driver of the type Vanguard blocks (the blocklist targets drivers exploitable for privilege escalation via arbitrary memory writes, a category WDM audio endpoints do not belong to).

**Qualification — Vanguard's "incompatible software" detection is driver-hash based, not named-list based.** Riot's FAQ states: "We don't block software packages specifically, only the drivers they distribute." Vanguard's "Incompatible Software" error message displays the full `.sys` path. VoiceMeeter's driver (`VBAudioVoicemeeter64.sys`) does not appear in any documented blocklist. However, Riot does not publish the blocklist. A future Vanguard update could add VoiceMeeter's driver hash if Riot determined it was being abused as an injection vector — unlikely given that virtual audio drivers have no privilege-escalation surface, but not formally ruled out.

**Qualification — The Valorant Chinese server precedent.** One source notes an "official list of banned programs" on Valorant's Chinese servers, with the suggestion global enforcement may follow. No details on whether audio tools appear on that list were available. The risk is low but is a real unknown.

---

### Claim 4 — EmbeddingGemma sidecar subprocess is safe
**CONFIRMED**

The sidecar is a standard Python subprocess with no game memory access, no hooks, no DLL injection, and IPC only via a named pipe or socket to the orchestrator. Process-creation callbacks see a `python.exe` process with an innocent path. No evidence of anticheats flagging external ML sidecar processes. The same analysis as Claim 1 applies. The orphan-prevention `KENNING_EMBEDDER_PARENT_PID` deadman mechanism is architecturally sound and produces no anticheat-visible behavior.

---

### Claim 5 — Vanguard user-mode migration reduces external process monitoring breadth
**REFUTED — MIGRATION STATUS UNCONFIRMED; RISK DIRECTION MAY BE REVERSED**

The B layer cites the Klizo Solutions Medium article describing Phase I (Q3 2025 hybrid) and Phase II (Q1 2026 full user-mode). Direct fetch of that article as of 2026-06-20 reveals these are **planned timelines, not confirmed deployments**. The article is prospective, not a deployment announcement. No Riot official changelog, blog post, or transparency report was found confirming Phase II went live in Q1 2026.

Independent corroborating evidence: A YouTube video titled "How to Fix Vanguard User Mode Service High CPU Usage in Valorant (Quick Guide! 2026)" and a Linus Tech Tips thread from late 2025 discuss a `vgturboservice.exe` or similar user-mode Vanguard service consuming 30-50% CPU during Valorant sessions. This is consistent with a hybrid deployment where user-mode ML is running alongside the kernel stub — but it is not confirmation of Phase II completion.

**Risk direction concern.** The B layer claims user-mode migration is "potentially positive" because user-mode processes are less capable than ring-0 drivers. This is partially backwards for Ultron's threat model. A ring-0 driver that focuses on the game process boundary is actually less likely to scan arbitrary background Python processes than a user-mode ML pipeline doing behavioral anomaly detection across all system activity. User-mode Vanguard processes run as a normal Windows service and can call `EnumProcesses`, `CreateToolhelp32Snapshot`, read any non-protected process's memory, and build behavioral models from system-wide telemetry. If Vanguard's user-mode tier expands its behavioral analysis beyond mouse/aim metrics to include GPU utilization patterns or process co-occurrence graphs, running a 12 GB CUDA workload alongside Valorant could become statistically anomalous in its model. No evidence this has happened, but the B layer's "potentially positive" framing understates this unknown.

**Corrected assessment:** Migration status is unconfirmed. Risk direction from migration is UNKNOWN, not positive.

---

### Claim 6 — Hardware Leonardo HID is definitively safe; NtUserSendInput is the only PTT risk
**CONFIRMED WITH CRITICAL QUALIFICATION**

The NtUserSendInput hook is confirmed (archie-osu reverse-engineering, April 2025). Hardware USB HID reports bypass this at the USB kernel stack level — the hook is in Win32k, below which physical HID input is handled by the `HidUsb.sys` / `kbdhid.sys` chain without passing through `NtUserSendInput`.

**Critical qualification — Vanguard VID/PID enumeration is a known anti-cheat technique.** The SerialKeyboardMouseController GitHub project notes that "some protection software checks USB VID and PID to avoid detection." Vanguard's 2026 IOMMU enforcement demonstrates it queries PCIe device enumeration aggressively. The Arduino Leonardo has a well-known VID `0x2341`, PID `0x8036` (HID keyboard mode). The codebase memory notes the device was confirmed as `VID 0x1209` (pid.codes open VID) in HID-keyboard mode — this is the correct configuration (open/community VID rather than Arduino's vendor VID, less fingerprint-able).

However: cheat hardware using Arduino-class devices (including the GitHub `Valorant-aimbot` project using Arduino to bypass software restrictions, confirmed active in 2026 searches) means Vanguard's telemetry has significant exposure to Arduino-class HID devices used for cheating. If Vanguard's ML behavioral models correlate `VID 0x1209` devices with key-press timing patterns during Valorant sessions, a false-positive risk exists for Ultron's PTT. Current mitigation (`release_jitter_ms = 60`) provides human-like jitter, which is the correct countermeasure for periodicity detection. This risk is LOW but is not zero, and the B layer does not acknowledge it.

---

### Claim 7 — Vanguard's "incompatible software" blocking is limited to kernel drivers
**CONFIRMED WITH QUALIFICATION**

Vanguard's displayed "Incompatible Software" error cites `.sys` driver paths, confirming the detection mechanism targets kernel drivers, not user-mode processes. Python processes, llama-cpp-python, PortAudio, and VoiceMeeter's user-mode mixer are not in this path. The confirmed blocked driver categories are: drivers with known privilege-escalation vulnerabilities (RTCore64.sys from MSI Afterburner's low-level IO mode is the canonical example), DMA-capable PCIe device drivers, and known injection vector drivers.

**Qualification — Process-level monitoring is a separate, less-documented layer.** Riot's third-party app policy bans that caused false positives for tracker apps ("permanently banned for third party software" reports on Tracker Network forums, 2025) appear to be triggered not by Vanguard's driver blocklist but by a separate process-monitoring layer that flagged apps accessing the LCU API or revealing stream-mode player names. The mechanism is not fully documented. Ultron does not touch LCU, game API, or player data — but these tracker ban reports demonstrate that Vanguard/Riot's detection system has a user-mode layer capable of flagging external processes that have no kernel-driver component and no game-memory access. The exact criteria for flagging in this layer are opaque.

**Practical implication:** The import firewall (keeping `pyautogui`, `pydirectinput`, `pygetwindow`, `win32api` out of the relay path) is more important than the B layer acknowledges, not because Vanguard scans Python module lists, but because if Ultron is ever manually audited by Riot, those imports would be red flags. The firewall should be maintained as a policy-integrity measure.

---

### Claim 8 — Policy risk is low because Ultron does not read game memory
**QUALIFIED — POLICY RISK IS REAL AND UNRESOLVED**

The B layer treats Riot's policy threat as residual. The research reveals it is more active than framed. Key findings:

- Riot's FAQ states: "There is absolutely no allowlist for Vanguard." This means Ultron has no avenue for formal pre-approval.
- Third-party tracker apps were banned for "unauthorized third-party apps that pull information hidden by the game client" — but also for revealing player names with stream mode active (a feature that doesn't read game memory). The policy trigger is broader than memory-reading.
- Riot's official stance (DevRel FAQ): "If a tool continues to function after Vanguard is live, it means they have restructured their tool to meet the new guidelines." This implies toleration-by-silence, not approval.
- The Valorant Chinese server precedent of an official banned program list with possible global expansion is an unresolved policy risk.

**The critical policy question for Ultron specifically:** Riot's anti-cheat FAQ says overlays and tools using "the API, game client, and in-game APIs" are allowed, while "external tools reading memory will no longer work." Ultron reads game AUDIO (team voice chat via Vivox, which passes through VoiceMeeter). This is structurally equivalent to a human teammate relaying callouts. However, if Riot's policy interpretation is that processing game audio to derive tactical information constitutes "pulling information from the game," Ultron could be classified as an unauthorized third-party tool regardless of the memory-vs-audio distinction.

No evidence was found that Riot has ever flagged a voice-processing relay tool. The risk is real but currently latent. Continuing to avoid game memory access, game API access, and in-game overlay injection is the correct posture.

---

## Corrected Recommendation for Ultron 1.0

The B layer's core conclusion is **correct but optimistic in framing**. Ultron 1.0 as designed is anticheat-safe by the technical criteria that matter most. The corrections are:

1. **Do not rely on the Vanguard user-mode migration being "positive."** Status is unconfirmed as of 2026-06-20. Treat user-mode Vanguard as a potential increase in external process visibility, not a reduction.

2. **The audio disruption risk (Vanguard destabilizing audio drivers) is MEDIUM severity, not LOW.** It produces mid-match deafness/muteness without a ban, but it is more likely than the B layer acknowledges given confirmed 2025 reports. Implement the capture-stall watchdog and VoiceMeeter connectivity watchdog before launch.

3. **PTT jitter is a real mitigation, not just a nice-to-have.** Arduino-class HID devices are actively used for cheating in 2026. The `release_jitter_ms = 60` parameter must be treated as a hard requirement. Any refactor that makes PTT timing periodic is a ban risk.

4. **Policy risk requires ongoing monitoring.** Riot's toleration-by-silence posture for tools that don't read memory is not equivalent to approval. If Riot ever expands its third-party app enforcement to audio-relay tools or if their policy interpretation of "pulling game information" broadens, Ultron would be in scope. Monitor Riot's DevRel announcements after each Vanguard update.

5. **The import firewall scope should include the always-listening intent path.** The B layer focuses the firewall on the relay/audio path. The always-listening orchestrator also runs continuously alongside Valorant and should be subject to the same import hygiene.

---

## Residual Risks (prioritized)

| # | Risk | Severity | Probability | Mitigation |
|---|------|----------|-------------|------------|
| R1 | Vanguard audio driver disruption mid-match (deafness/muteness, not ban) | Medium | Medium (confirmed 2025) | Capture-stall watchdog + VoiceMeeter connectivity watchdog; document restart procedure |
| R2 | Vanguard user-mode ML expansion monitors external GPU compute co-occurrence | Low-medium | Low (unconfirmed) | No change needed now; monitor Riot changelogs post each Vanguard update |
| R3 | Arduino/HID VID flagged by Vanguard behavioral ML due to cheat-tool prevalence | Low | Low | Maintain `release_jitter_ms=60`; confirm `VID 0x1209` (pid.codes) not in any Vanguard blocklist |
| R4 | Riot policy expansion: audio-relay classified as "unauthorized third-party app" | Low | Very low (no precedent) | Maintain zero game-memory / game-API access; document Ultron's audio-only architecture |
| R5 | VRAM contention: 8B model + Valorant exhausts 10 GB design cap, causing render stutter | Medium | Medium (empirical) | Profile under live gaming load; consider LRU eviction of KV cache between turns |
| R6 | Vanguard Chinese server banned-program list expanded globally | Low | Unknown | Monitor; no actionable change possible pre-facto |
| R7 | Software PTT fallback accidentally added in a future refactor | High (if triggered) | Low (currently pinned) | Code-level guard: `assert backend == 'rawhid'` at boot; never import `win32api`/`SendInput` in PTT path |
| R8 | Vanguard voice-chat recording captures Ultron relay audio sent through Vivox | Negligible (content risk only) | Medium (recording is active) | No change needed; Vivox recording is for behavioral moderation, not cheat detection |

---

## Sources

1. **Riot Games — Vanguard FAQ for Third Party Applications** (official policy; confirmed "no allowlist")  
   https://www.riotgames.com/en/DevRel/vanguard-faq

2. **archie-osu — Inside Riot Vanguard's Dispatch Table Hooks (April 2025)**  
   https://archie-osu.github.io/2025/04/11/vanguard-research.html  
   *Primary source for hooked syscall list; audio APIs absent; author acknowledges incomplete coverage.*

3. **Adrian's Security Research — How Kernel Anti-Cheats Work**  
   https://s4dbrd.github.io/posts/how-kernel-anti-cheats-work/  
   *Confirms PsSetCreateProcessNotifyRoutineEx scope (system-wide process events); focus is game-process threats, not external apps.*

4. **klizosolutions Medium — Vanguard User-Mode Migration Plan**  
   https://klizosolutions.medium.com/user-mode-ai-protectionbeyond-the-kernel-vanguards-planned-shift-to-user-mode-ai-protection-d074139333ad  
   *Fetched 2026-06-20: describes planned Phase I/II timelines, NOT confirmed deployments.*

5. **vpesports.com — Valorant tracker app bans (mechanism analysis)**  
   https://vpesports.com/valorants-anti-cheat-system-is-now-actively-preventing-users-who-utilize-tracker-applications  
   *Confirms policy bans for non-memory-reading apps; mechanism not fully disclosed.*

6. **Tracker Network feedback — Permanent ban for Valorant Tracker app**  
   https://feedback.tracker.gg/t/pernamently-banned-due-to-valorant-tracker/18839  
   *Community evidence of policy-layer ban for third-party apps not reading game memory.*

7. **itch.io devlog — Valorant Ban Waves in 2026 (community tracking)**  
   https://060121131.itch.io/valorant/devlog/1453049/valorant-ban-waves-in-2026-the-updated-list-every-banned-player-needs  
   *January 2026 ban triggers: HWID spoofers, aim-assist, wallhacks, bot accounts. No audio/AI/Python tools listed.*

8. **AnswerOverflow — Vanguard still messing with audio drivers in 2025**  
   https://www.answeroverflow.com/m/1360544787220140245  
   *Confirmed 2025 audio disruption reports; 403 at time of fetch but title/snippet sufficient.*

9. **Tweaktown — Vanguard IOMMU DMA firmware destruction (May 2026)**  
   https://www.tweaktown.com/news/111774/valorants-vanguard-anti-cheat-now-destroys-dma-cheat-firmware/index.html

10. **SerialKeyboardMouseController (GitHub)**  
    https://github.com/charlescao460/SerialKeyboardMouseController  
    *Notes that "some protection software checks USB VID and PID."*

11. **Valorant-aimbot Arduino project (GitHub, active 2026)**  
    https://github.com/Qwyua/Valorant-aimbot  
    *Confirms Arduino-class HID devices actively used for Valorant cheating in 2026; context for Vanguard ML exposure to Arduino VIDs.*

12. **esports.net — Valorant Incompatible Software error**  
    https://www.esports.net/wiki/guides/valorant-incompatible-software-error-fix/  
    *Confirms blocking is .sys driver-level, not user-mode process level.*

13. **ACM MATE 2024 — "If It Looks Like a Rootkit" (peer-reviewed)**  
    https://arxiv.org/html/2408.00500v1  
    *Audio APIs absent from anticheat detection surface survey.*

14. **secret.club — BattlEye Anti-Cheat Analysis**  
    https://secret.club/2019/02/10/battleye-anticheat.html  
    *BattlEye process enumeration: path heuristics (Desktop/Temp/Downloads), named blacklist patterns, module scan. Ultron path (C:\STC\...) and name (python.exe) are clean.*

15. **VoiceMeeter — December 2025 Update Notes**  
    https://voicemeeter.com/voicemeeter-updates-december-2025/  
    *Confirms active maintenance and no Valorant/Vanguard ban incidents reported in release notes.*
