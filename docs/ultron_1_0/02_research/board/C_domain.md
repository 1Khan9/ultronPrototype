# Adversarial Verification: Valorant Domain Accuracy (B_valorant_kits / B_valorant_comms / B_valorant_maps)

**Adversarial agent:** claude-sonnet-4-6  
**Verification date:** 2026-06-20  
**Target docs:** B_valorant_kits.md, B_valorant_comms.md, B_valorant_maps.md  
**Stance:** Refute or qualify every claim with independent web evidence. Default: skepticism.

---

## Claims Examined

1. Total agent count: 29 agents, Miks as Agent 30  
2. Miks release date and role  
3. Neon High Gear: slide recharges on 2 kills  
4. Iso Undercut: throws a molecular bolt applying Fragile (2 charges)  
5. Clove: Pick-Me-Up activates after kill/assist for overheal; Not Dead Yet costs 6 pts  
6. Gekko: only Mosh, Dizzy, Thrash can be recollected  
7. Veto: Evolution cost listed as "TBC"; Interceptor destroys physical utility  
8. Harbor rework (Patch 11.10): Cascade→Storm Surge, Cove now signature  
9. Corrode map release date and callout names  
10. Economy credit numbers (loss bonus 1,900/2,400/2,900)  
11. V26 Act 3 competitive map pool  
12. Icebox callout names (B Snowman, B Hut, B Kitchen, etc.)  
13. B_valorant_comms: "bomb" → "spike" normalization claim  
14. Verbosity model and callout formula

---

## Verdict Per Claim

### 1. Agent count and Miks numbering — QUALIFIED

**B_kits claim:** "29 agents as of June 2026. Newest: Miks (Agent 30 by some counts)."

**Verified:** Multiple sources confirm 29 total agents but disagree on Miks' number. Riot officially calls Miks "Agent 30" in marketing materials (egamersworld.com, games.gg, pley.gg). However, turbosmurfs.gg and pley.gg roster pages count 29 total agents — consistent with Miks being the 29th if one released agent is not counted (likely a retired/non-standard slot). The discrepancy stems from how pre-release/beta agents are counted.

**For Ultron 1.0:** Roster total is 29 active playable agents. Miks is the most recent. Do not rely on agent number ordinals — use agent names. The B_kits doc hedges correctly ("Agent 30 by some counts") but the body text also says "Agent 29: Veto" which makes the arithmetic consistent if Miks=30. The 29-agent count in the role distribution table (8+7+7+7=29) is internally consistent and correct for practical purposes.

**Evidence:** turbosmurfs.gg (29 agents total), games.gg (Miks Agent 30), pley.gg (29 agents overview).

---

### 2. Miks release date — CONFIRMED

**B_kits claim:** "March 18 2026, Act 2 Season 2026, Controller, team-healing."

**Verified:** All sources independently confirm March 18 2026, Season 2026 Act 2. Confirmed as first Controller with team healing. Revealed at VCT Masters Santiago Grand Finals on March 15. No discrepancies found.

**Evidence:** beebom.com, thespike.gg, tracker.gg, amber.gg.

---

### 3. Neon High Gear slide recharge — CONFIRMED WITH IMPORTANT POST-RESEARCH CAVEAT

**B_kits claim:** "Sliding recharges on 2 kills."

**Verified:** The 2-kill slide recharge is confirmed current as of Patch 12.09 (May 2026). HOWEVER, Patch 12.09 added a significant caveat the B_kits doc omits:

- **Fuel regeneration on kills now ONLY applies when Overdrive (X) is active.** Passive fuel regeneration still occurs, but the kill-based fuel refill no longer applies outside of ultimate.
- **Jumping with High Gear active no longer provides a speed bonus while airborne** (air speed matches melee speed).

The compact kit reference in B_kits says only "Sliding recharges on 2 kills" — this is accurate for the slide specifically. But the broader description "sprint faster than any other agent" is no longer entirely true for aerial mobility. The 12.09 nerf meaningfully changes how Neon plays (no bunny-hop speed) and the kit summary should note it.

**Ultron 1.0 impact:** If a teammate says "Neon used her sprint" or "Neon's fuel," the relay or PRIVATE_REPLY description is missing post-nerf context. Low risk for relay path; higher risk for PRIVATE_REPLY "what does Neon's E do?"

**Evidence:** playvalorant.com patch notes 12.09, x.com/ValorantUpdated, beebom.com patch 12.09 notes.

---

### 4. Iso Undercut — REFUTED (stale kit data)

**B_kits claim:** "Q – Undercut: Throw a molecular bolt that briefly applies Fragile (increased damage taken) to enemies it passes through." Compact format shows: "Q=Undercut(fragile)".

**Verified WRONG:** Patch 10.04 (February 2025) changed Undercut:
- Charges reduced from 2 → **1** (B_kits implies 2 charges or does not caveat)
- Cost increased from 200 → **300 credits**
- Now applies **Suppression alongside Fragile/Vulnerability for 4 seconds** — Suppression was not in the original kit

The B_kits description "applies Fragile" is now incomplete. It also applies Suppression (enemies cannot use abilities). This is a large mechanical difference — Undercut now hard-counters utility-dependent agents during the suppression window, similar to KAY/O's ZERO/point. Injecting the stale description will cause the LLM to describe Undercut incorrectly.

**Ultron 1.0 impact:** PRIVATE_REPLY "what does Iso's Q do?" will give the wrong answer. The relay path only uses ability names, so relay accuracy is unaffected. Update required for full-kit descriptions.

**Evidence:** x.com/ValorINTEL patch 10.04, x.com/ValorantUpdated patch 10.04, playvalorant.com patch notes 10.04.

---

### 5. Clove Pick-Me-Up cost and Not Dead Yet ult cost — REFUTED (stale)

**B_kits claim:** "C – Pick-Me-Up: Activate after getting a kill or assist to gain a burst of health (overheal) for a limited duration." No cost given. "X – Not Dead Yet (Ultimate, 6 pts)."

**Verified WRONG on both:**

(a) Pick-Me-Up cost: Patch 8.11 (June 2024) increased the cost from 100 → **200 credits** and reduced duration from 10s → **8s**, and activation time from 10s → **6s**. The doc doesn't list the ability cost at all (making it seem free/cheap), but for context injection purposes the relevant delta is the activation window (6s, not 10s).

(b) Not Dead Yet ult cost: B_kits says **6 pts**. The correct current cost is **8 ult points** (changed from 7→8 in Patch 8.11, June 2024 — confirmed by multiple sources including x.com/ValorINTEL). This is a significant error: injecting "6 pts" will make the LLM understate how expensive Clove's ult is by 25%.

**Ultron 1.0 impact:** The ult cost (6 vs 8) is the most concrete error — any PRIVATE_REPLY about "how many points does Clove ult cost" will be wrong. Fix the compact kit to show "X=Not Dead Yet(self-revive ult, 8pts)."

**Evidence:** x.com/ValorINTEL patch 8.11, x.com/ValorantUpdated patch 8.11, x.com/ValorLeaks patch 8.11, dexerto.com patch 8.11.

---

### 6. Gekko recollect mechanic — REFUTED (stale)

**B_kits claim:** "Unique mechanic: Mosh, Dizzy, and Thrash can be recollected after use."

**Verified WRONG:** As of Patch 12.03 (February 17 2026), **Mosh Pit is now also reclaimable.** Prior to Patch 12.03, Mosh was the ONLY Gekko creature that could NOT be reclaimed — it was a one-use expendable. Patch 12.03 added Mosh to the reclaim system.

The B_kits statement that "Mosh, Dizzy, and Thrash can be recollected" actually happens to be accidentally correct post-12.03 (Mosh is now reclaimable), BUT the framing "after use" is misleading — previously Mosh could not be, and the doc does not note this was a recent change. The doc is accidentally accurate but for the wrong reasons; it needs a note.

**Corrected:** All three creatures (Mosh, Dizzy, Thrash) can be reclaimed post-Patch 12.03. This is current.

**Evidence:** talkesport.com Patch 12.03 Gekko buff, dexerto.com Patch 12.03.

---

### 7. Veto Evolution ult cost — PARTIALLY REFUTED (cost was "TBC" in doc, now confirmed)

**B_kits claim:** "X – Evolution (Ultimate, cost TBC)"

**Verified:** Evolution costs **7 ultimate points.** Multiple sources confirm (pley.gg, esports.gg guide, dotesports.com Veto abilities, and the search summary from metabot.gg). The "TBC" label in B_kits is outdated — the cost is known and confirmed.

The kit description in B_kits is otherwise accurate: combat stim + health regeneration + full debuff immunity. The description "cannot be flashed, stunned, slowed, decayed, or damaged by explosions" is consistent with sources. One nuance: Evolution lasts until Veto is killed or the round ends (not a timed duration per some sources), so it is indefinite in the round.

**Ultron 1.0 impact:** Update compact kit from "X=Evolution(debuff immunity+regen ult)" to "X=Evolution(debuff immunity+regen ult, 7pts)."

**Evidence:** pley.gg Veto guide, esports.gg Veto guide, search result summary from multiple sources.

---

### 8. Harbor rework (Patch 11.10) — CONFIRMED

**B_kits claim:** "Cascade was replaced by Storm Surge and Cove moved to signature. High Tide now purchasable. Storm Surge creates a whirlpool. Reckoning now more directional."

**Verified:** All aspects confirmed by independent sources (dotesports.com, strafe.com, dexerto.com 11.10 patch notes, official playvalorant.com patch notes):
- Cascade removed, replaced by Storm Surge (whirlpool: nearsights + slows after brief delay)
- Cove is now the signature (free per round, remotely placed water smoke, can be made bulletproof)
- High Tide is now a basic purchasable ability (no longer free/signature)
- Reckoning now surges forward in a cone (nearsights + slows)

One nuance: the doc says Reckoning is "significantly more directional than the previous geyser version" — this is accurate per dexerto.com.

**Evidence:** dotesports.com Harbor changes 11.10, strafe.com patch 11.10, dexerto.com 11.10 patch notes, playvalorant.com patch notes 11.10.

---

### 9. Corrode map release date — QUALIFIED

**B_kits/B_maps claim:** B_maps says "Corrode (released October 2025, patch 11.00)."

**Verified WRONG on date:** Corrode was released with **Patch 11.00 on June 25, 2025** — not October 2025. October 2025 was when Veto released. The B_maps doc has the Corrode release date wrong by approximately 4 months.

The callout structure in B_maps (A: Lobby, Main, Yard, Link, Elbow, Site / B: Lobby, Main, Link, Elbow, Site, Tower/Arch / Mid: Bottom, Stairs, Top, Window) is **confirmed accurate** by Liquipedia's Corrode page (which lists: A=Lobby/Main/Yard/Pocket/Link/Site/Elbow/Crane; B=Lobby/Main/Site/Link/Elbow/Tower/Arch; Mid=Window/Top/Stairs/Bottom). The B_maps callouts omit "Pocket" and "Crane" from A site but are otherwise correct.

**Ultron 1.0 impact:** The release date error in B_maps ("October 2025") does not affect relay accuracy — the callout vocabulary is what matters. The callout list is substantially correct but missing 2 named A-site positions (Pocket, Crane). Low risk given these are rare callouts.

**Evidence:** sportskeeda.com patch 11.00, tracker.gg Corrode preview, liquipedia.net/valorant/Corrode.

---

### 10. Economy credit numbers — CONFIRMED

**B_comms claim:** "Loss bonus (streak): 1,900 / 2,400 / 2,900 cr (1 / 2 / 3+ consecutive losses). Win round: 3,000 cr. Kill: 200 cr. Spike plant: 300 cr. Cap: 9,000 cr."

**Verified:** All numbers confirmed by multiple 2026 economy guides (valohub.co, boosteria.org, blix.gg). Weapon prices (Vandal/Phantom 2,900 cr, Operator 4,700 cr) are standard and unchanged. Loss bonus tier values are stable.

**Evidence:** valohub.co economy guide 2026, boosteria.org economy guide, blix.gg economy explainer.

---

### 11. V26 Act 3 competitive map pool — CONFIRMED

**B_maps claim:** "Ascent · Breeze · Fracture · Haven · Lotus · Pearl · Split (Patch 12.08, April 29 2026)."

**Verified:** Confirmed by tracker.gg, pley.gg, thespike.gg, playvalorant.com patch notes 12.08. Bind removed, Ascent returned. Correct as of research date.

**Evidence:** tracker.gg Act 3 map pool article, pley.gg S26A3 rotation, playvalorant.com patch notes 12.08.

---

### 12. Icebox callout names — CONFIRMED WITH ADDITIONS

**B_maps claim:** Icebox callouts include "B Green, B Yellow, B Hall, B Snowman, B Hut, B Kitchen, Back B, B Tube, B Orange, A Belt, A Pipes, A Nest, A Screen, A Rafters."

**Verified:** Confirmed by multiple Icebox callout guides (mobalytics.gg, dotesports.com, dexerto.com). Additional callouts sources confirm: A Site also includes A Site itself; B site also includes B Fence, B Cubby, B Snow Pile, B Back (in addition to what B_maps listed). The B_maps list is accurate but incomplete for B site (missing Fence, Cubby, Snow Pile). Low risk since those are supplemental positions.

**Evidence:** mobalytics.gg Icebox callout map, valorfeed.gg Icebox guide.

---

### 13. B_comms "bomb" → "spike" normalization — CONFIRMED

**B_comms claim:** "Players say 'bomb down' (CS:GO legacy), normalizer should map 'bomb' → 'Spike.'"

**Verified:** Accurate assessment. CS:GO crossover terminology is well-documented in Valorant communities. The normalization rule is correct.

---

### 14. Verbosity model and callout formula — CONFIRMED

**B_comms claim:** "[Count] [Location] [Action] [Condition]" formula; info-priority hierarchy; clutch = silent; over-communication as harmful as under-communication.

**Verified:** The formula, info-priority, and clutch-silence principle are confirmed by multiple coaching sources (BoostRoom, Boosteria, Gankster, Blix.gg). The "40 callouts" taxonomy is sourced from a real Boosteria playbook. No errors found.

---

## Summary Table

| # | Claim | Verdict | Severity |
|---|-------|---------|----------|
| 1 | 29 agents, Miks=Agent 30 | QUALIFIED | Low (cosmetic) |
| 2 | Miks release date/role | CONFIRMED | — |
| 3 | Neon slide 2-kill recharge | CONFIRMED + CAVEAT | Medium |
| 4 | Iso Undercut = Fragile only | **REFUTED** | High |
| 5 | Clove Not Dead Yet = 6 pts | **REFUTED** | High |
| 6 | Gekko recollect mechanic | CONFIRMED (post-12.03) | Low |
| 7 | Veto Evolution cost = TBC | PARTIALLY REFUTED | Medium |
| 8 | Harbor rework details | CONFIRMED | — |
| 9 | Corrode release = Oct 2025 | **REFUTED** (Jun 2025) | Low |
| 9b | Corrode callout names | CONFIRMED (minor gaps) | Low |
| 10 | Economy credit numbers | CONFIRMED | — |
| 11 | V26 Act 3 map pool | CONFIRMED | — |
| 12 | Icebox callout names | CONFIRMED (minor gaps) | Low |
| 13 | bomb→spike normalization | CONFIRMED | — |
| 14 | Verbosity formula | CONFIRMED | — |

---

## Corrected Recommendation for Ultron 1.0

### Critical fixes (inject the corrected values):

**Fix 1 — Iso Undercut (HIGH PRIORITY):**
Replace: `Q=Undercut(fragile)`
With: `Q=Undercut(fragile+suppress 4s, 1 charge, 300cr)`
The suppression effect makes Undercut functionally similar to KAY/O's ZERO/point for a 4-second window. The LLM must know this or it will incorrectly advise players that Undercut only applies Fragile.

**Fix 2 — Clove Not Dead Yet ult cost (HIGH PRIORITY):**
Replace: `X=Not Dead Yet(self-revive ult)` with cost shown as "6 pts"
With: `X=Not Dead Yet(self-revive ult, 8pts)`
Six points is 25% cheaper than the actual 8 — this will produce wrong answers about ultimate economy.

**Fix 3 — Veto Evolution ult cost (MEDIUM PRIORITY):**
Replace: `X=Evolution(debuff immunity+regen ult)` [TBC cost]
With: `X=Evolution(debuff immunity+regen+stim ult, 7pts, lasts until death)`

**Fix 4 — Neon High Gear description (MEDIUM PRIORITY):**
Add caveat to PRIVATE_REPLY descriptions: "Post-12.09: jumping during High Gear no longer grants air speed bonus; kill-based fuel refill only applies while Overdrive is active."
The compact relay kit format ("E=High Gear(sprint/sig)") is fine as-is — this only matters for detailed ability Q&A.

**Fix 5 — Corrode release date (LOW PRIORITY for relay, fix for accuracy):**
Replace "October 2025" with "June 25, 2025" in B_maps. Does not affect callout vocabulary.

**Fix 6 — Corrode callout additions (LOW PRIORITY):**
Add "A Pocket, A Crane" to Corrode A site callout list for completeness.

### Recommendations that stand as written:
- Harbor rework kit: inject as-is, correctly marked as post-rework
- Miks full kit: accurate, inject as-is
- Veto full kit: accurate except ult cost; fix cost and remove TBC
- Waylay full kit: confirmed accurate against multiple sources
- All economy numbers: confirmed, inject as-is
- Map pool (Act 3): confirmed, inject as-is
- Callout formula and verbosity model: confirmed, implement as designed
- Corrode callouts (structural): correct and safe to inject minus the 2 missing A-site names

---

## Residual Risks

### R1: Patch cadence staleness (~3 weeks per patch)
The kit reference will be stale within one patch cycle. Patch 12.10 (current as of research date) brought no agent changes, but Patch 12.09 (May 2026) introduced Neon nerfs that the B_kits doc does not reflect. Future patches regularly adjust ability mechanics, costs, and charges. The injected context must be version-stamped and treated as perishable.

**Mitigation:** Version-stamp the kit block as `# VALORANT KITS v2026-06-20 (Patch 12.10)`. Build a lightweight update path (scrape wiki or patch notes page) for re-validation each patch.

### R2: Qwen3-8B base weight contamination for recent agents
The Josiefied-Qwen3-8B model (training cutoff ~late 2024) has no clean knowledge of Waylay (March 2025), Veto (October 2025), or Miks (March 2026). More dangerously, it may have seen early Waylay/Veto pre-release leaks or speculation that differs from final shipped kits. These three agents MUST be injected — the base model cannot be trusted. Additionally, Iso's Undercut suppression change (Patch 10.04, February 2025) postdates the cutoff. The model's Iso knowledge may be the stale pre-suppression version even for the base weights.

**Mitigation:** Explicitly flag in the system prompt: "The following agents have had significant changes since your training data; use ONLY the information below." Enumerate Waylay, Veto, Miks, and Iso (Undercut).

### R3: Clove ult cost error propagation
The 6-pt claim in B_kits is wrong by 33% (actual: 8 pts). If the LLM is asked "does Clove have ult?" in a game context and uses its in-context data, it will say yes when the player actually needs 2 more points. This is the highest-confidence error found with the highest tactical consequence.

### R4: Corrode community callout divergence
No official Riot API for callout names exists. Community names diverge slightly (e.g., "A Yard" vs "A Courtyard" on some guides). The Corrode callout list in B_maps is based on Liquipedia and community sources — considered reliable but not authoritative. "Pocket" and "Crane" for A site are absent from B_maps and could cause misunderstanding if teammates call them.

### R5: Icebox/Bind/Abyss callout incompleteness
B_maps treats inactive maps at a high level only. Icebox B site is missing "Fence," "Cubby," "Snow Pile" from the list. For unranked/custom play these will be called. If Ultron tries to relay "B Fence" on Icebox the slot parser will not recognize it.

**Mitigation:** The relay path should pass-through unrecognized location tokens verbatim rather than normalizing or dropping them. This is already the design (B_comms: "preserve callout tokens verbatim") — verify the implementation honors unknown callouts.

### R6: Agent 31 vacuum
No Agent 31 has been revealed as of research date. Sources suggest one new agent per "winter-spring 2026" period; Miks fills that slot. If Act 4 (late July / early August 2026) introduces a new agent, the kit context will be immediately incomplete for that agent with no fallback. The LLM will hallucinate the kit.

**Mitigation:** Build the injection as a hot-swappable JSON/YAML file rather than hardcoding in the system prompt. When a new agent releases, update the file without retraining.

---

## Sources

1. **turbosmurfs.gg** — Valorant agent count confirmation (29 total): https://turbosmurfs.gg/article/how-many-agents-are-in-valorant
2. **games.gg** — Miks as Agent 30: https://games.gg/news/valorant-agent-30-miks-abilities/
3. **playvalorant.com** — Patch Notes 12.09 (Neon nerfs): https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-12-09/
4. **x.com/ValorantUpdated** — Neon 12.09 fuel/sprint changes confirmed: https://x.com/ValorantUpdated/status/2052445372782453104
5. **x.com/ValorINTEL** — Iso Patch 10.04 Undercut suppression: https://x.com/ValorINTEL/status/1896934533062443207
6. **x.com/ValorantUpdated** — Iso 10.04 full changes: https://x.com/ValorantUpdated/status/1896623884834886105
7. **playvalorant.com** — Patch Notes 10.04: https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-10-04/
8. **x.com/ValorINTEL** — Clove Patch 8.11 Not Dead Yet 7→8 pts: https://x.com/ValorINTEL/status/1798342681707319382
9. **x.com/ValorantUpdated** — Clove 8.11 changes: https://x.com/ValorantUpdated/status/1798344726942200193
10. **talkesport.com** — Gekko Mosh Pit reclaimable Patch 12.03: https://www.talkesport.com/news/gekko-valorant-buff-patch-12-03-reclaim-mosh-pit/
11. **pley.gg** — Veto Evolution 7 ult points: https://pley.gg/valorant/agent-veto-abilities-showcase/
12. **dotesports.com** — All Harbor changes Patch 11.10: https://dotesports.com/valorant/news/harbor-changes-valorant-patch-11-10
13. **playvalorant.com** — Patch Notes 11.10: https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-11-10/
14. **sportskeeda.com** — Corrode Patch 11.00 release June 25 2025: https://www.sportskeeda.com/valorant/valorant-11-00-patch-notes-new-map-corrode-agent-updates
15. **liquipedia.net** — Corrode map callouts (A: Lobby/Main/Yard/Pocket/Link/Site/Elbow/Crane; B: Lobby/Main/Site/Link/Elbow/Tower/Arch; Mid: Window/Top/Stairs/Bottom): https://liquipedia.net/valorant/Corrode
16. **tracker.gg** — V26 Act 3 map pool confirmation: https://tracker.gg/articles/valorant-v26-act-3-competitive-map-pool-all-you-need-to-know
17. **playvalorant.com** — Patch Notes 12.08 (Act 3 map pool): https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-12-08/
18. **valohub.co** — Economy credit numbers 2026: https://valohub.co/guides/valorant-economy-guide
19. **mobalytics.gg** — Icebox callout names: https://mobalytics.gg/valorant/map/icebox
20. **thespike.gg** — Miks full ability kit: https://www.thespike.gg/valorant/agents/miks
21. **amber.gg** — Miks Patch 12.05 live guide: https://amber.gg/blog/valorant/miks-valorant-abilities-guide
