# Valorant 2026 Competitive Map Pool and Location Callouts

> Research date: 2026-06-20. Authoritative sources: official Riot announcements, vlr.gg, pley.gg, tracker.gg, progameguides, valorfeed, oneesports. The pool rotates every ~8 weeks (once per Act).

---

## TL;DR Recommendation for Ultron 1.0

**Current pool (V26 Act 3, from Patch 12.08, April 29 2026):**
Ascent · Breeze · Fracture · Haven · Lotus · Pearl · Split

The relay's location-vocabulary layer must cover all 12 maps (7 active + 5 inactive but playable in Unrated/custom). Callouts from inactive maps (Abyss, Bind, Corrode, Icebox, Sunset) WILL appear in unranked voice; do not hardcode only the competitive 7.

For Ultron 1.0 the relay pipeline should:
1. **Embed a callout gazetteer** (all ~200 named positions) into the 8B system prompt as injected exemplars — small enough to fit in the 10 GB VRAM budget with Q5_K_M at typical context (≤2048 tokens overhead).
2. **Preserve callout tokens verbatim in TTS/relay** — never paraphrase "A Ramps" to "the ramp on A", never expand "B Main" to "B main site". The relay must output the callout exactly as spoken.
3. **Use the gazetteer for ASR biasing** — feed to faster-whisper `initial_prompt` / `hotwords` to fix "Eight-main" → "A Main", "B-site" → "B Site", etc.
4. **Route by map context** — if the user calls a map explicitly ("we're on Fracture", "this is Lotus"), the 8B's map context injection can prioritize that map's vocabulary for the rest of the match session.

---

## Findings

### 1. Map Pool Rotation Timeline (2026)

Riot keeps **exactly 7 maps** in competitive at all times. Rotation happens once per Act (roughly every 8 weeks). Unrated/casual allows all 12 maps.

| Act | Pool | Change | Patch / Date |
|-----|------|--------|--------------|
| V26 Act 1 | Abyss · Bind · Breeze · Corrode · Haven · Pearl · Split | Sunset removed, Breeze + Corrode added | Patch 12.00, Jan 6 2026 |
| V26 Act 2 | Bind · Breeze · Fracture · Haven · Lotus · Pearl · Split | Abyss + Corrode out; Fracture + Lotus in | Patch 12.05, ~Mar 17 2026 |
| V26 Act 3 | **Ascent · Breeze · Fracture · Haven · Lotus · Pearl · Split** | Bind out; Ascent in | Patch 12.08, Apr 29 2026 |

Source: Official Riot tweet (x.com/VALORANT, April 21 2026) confirmed by pley.gg, thespike.gg.

**V26 Act 3 is the CURRENT pool as of this research date (June 20 2026).**

VCT 2026 Masters London (Copper Box Arena, June 6–21 2026) uses this pool. The relay must be fluent in all 7 maps for pro callouts that players emulate.

### 2. All 12 Maps — Status and Callout Index

---

#### ASCENT (Active — Act 3)

Italian rooftop city. Two bombsites. Mechanical mid doors (buy-round gate). Classic CS-inspired layout.

**A Site:**
- A Lobby / A Spawn — attacker spawn entry
- A Wine / Wine — side room off A Lobby
- A Garden — passage to A site from spawn side
- A Main — primary corridor to A site
- A Short / A Choke — shorter approach from mid
- A Link — passage connecting mid bottom to A site
- A Window — defender window looking into A Main
- A Switch — door-control button area
- A Site — bomb plant area
- A Rafters / A Heaven — elevated platform above site
- Hell / Under Heaven — ground below Rafters
- Generator — box near site used for plant cover
- Green Boxes — cover on site

**B Site:**
- B Lobby / B Spawn — attacker spawn
- B Main — primary corridor to B
- B Lane — side lane off B main
- B Market / Market — enclosed room flanking B
- B Market Door / B Door — market entrance
- B Switch — door-control area
- B Site — bomb plant area
- B Shed / Boathouse / Back B — rear of B site
- Pizza / Pizza Corner — corner angle near CT

**Mid:**
- Mid Courtyard / Courtyard — central open area
- Mid Catwalk / Catwalk — elevated mid path
- Mid Cubby — indent in mid wall
- Mid Tiles — tiled section of mid
- Mid Link / Mid Bottom — passage to A Link
- Top Mid / Arch — archway entry to mid from defender side
- CT Alley / CT Corridor — defender-side mid passage

---

#### BREEZE (Active — Act 3)

Large open Caribbean island. Long sightlines. Mid control critical. Operator-favored.

**A Site:**
- A Lobby / A Spawn — attacker entry
- A Cave — approach hallway to A Main
- A Main — primary entry to A
- A Shop — side room near A Main
- A Rope — rope climb near A Hall
- A Hall — secondary passage from mid to A
- A Metal Doors / A Doors — entrance from mid to A Hall
- A Bridge — connects A Hall to CT area
- A Pyramids — large pyramid structures on site (Left Pyramid / Right Pyramid)
- A Cubby — hiding spot near site entrance
- BackSite A — rear of A site
- Default Plant A — standard plant spot

**B Site:**
- B Main — primary attacker entry
- B Elbow — curve connecting B Main to tunnel
- B Tunnel / Tunnel — secondary attacker entry
- B Arches / Arches — connector near tunnel from defender side
- B Pillar — central landmark (Behind Pillar, Left Pillar, Right Pillar)
- B Windows — elevated vantage
- B Lane / Lane — side lurk path
- Lane Stairs — elevated lane access
- B BackSite / BackSite B — rear of B
- B Wall — off-angle defender position

**Mid:**
- Mid Top / Top Mid — upper mid area
- Mid Nest / Nest — sniper nest elevated position
- Mid Pillar — central reference pillar
- Mid Chute / Chute — small drop connecting mid to A
- Mid Doors / Wood Doors — central mid gate (buyable)
- Mid Bottom / Bottom Mid — lower mid toward spawn

---

#### FRACTURE (Active — Act 3)

H-shaped map. Unique attacker spawn split: attackers can enter from BOTH sides of the map. Defender spawn in middle. Ropes used by attackers to cross.

**A Site:**
- A Lobby — attacker entry (east side)
- A Main — primary east entry
- A Rope — rope used to cross from west spawn to east A
- A Gate — gate controlling rope access
- A Link — connector from mid to A
- A Drop — drop-down into A site
- A Dish / Dish — elevated platform/dish structure near A
- A Site — plant zone
- A Heaven — elevated position above A
- A Hell — below A Heaven

**B Site:**
- B Lobby — attacker entry (west side)
- B Main — primary west entry
- B Tower / Tower — elevated position near B
- B Arcade / Arcade — attacker-side area with arcade machines; connects west spawn
- Canteen — central area between arcade and B connector
- B Generator / Generator — near B site, between canteen and B link
- B Link / B Connector — connector into B from mid
- B Heaven — elevated position above B
- B Hell — below B Heaven
- B Bench — cover spot on B
- B Tree — tree cover on/near B

**Mid/Connector:**
- Mid / Central — H-shaped center
- Arcade Pass — path from Arcade to mid
- Dish Connection — path from dish to mid area

---

#### HAVEN (Active — Act 3)

Unique 3-site map. Defender spawn advantages compressed. Garage rotation route.

**A Site:**
- A Lobby — attacker approach
- A Long / A Long Hallway — long corridor approach to A
- A Short — shorter/direct approach to A
- A Tower / A Heaven — elevated position above A site
- A Stairs — access to A Heaven
- A Bottom Haven — ground below A Heaven
- A Boxes — cover on site
- A Tunnel — connector from A to mid
- A Link — connects A to mid

**B Site (center site):**
- T Mid Doors / Mid Doors — central gate from attacker side
- Mid Courtyard / Courtyard — open center area
- Mid Windows / Window — window angle from mid into B approach
- B Site — plant zone (center of map)
- B Back / Back B — rear of B site
- B Boxes — cover on B
- Garage — side room flanking B and connecting to C; key rotation point

**C Site:**
- C Lobby — attacker approach
- C Long — long corridor from attacker spawn toward C
- C Window — window into C long from defender side
- C Logs / C Cubby — cover near C Long
- C Link — connects C area to mid/Garage
- C Site — plant zone
- C Back / Back C — rear of C site

---

#### LOTUS (Active — Act 3)

3-site map. Features rotating stone doors (mechanical; buyable to open), a breakable wall on B, and a silent drop on A.

**A Site:**
- A Lobby — attacker approach
- A Main — primary path to A
- A Root — small area next to A Main
- A Rubble — area at entrance to A site, provides cover
- A Door — rotating door into A site (key mechanic)
- A Tree — position near A used for covert sight lines
- A Stairs — stairs near A
- A Drop — silent drop from A Top to A site
- A Top — elevated area above A drop
- A Link — passage connecting A to B
- A Hut — small building adjacent to A site
- A Site — plant zone

**B Site:**
- B Main — primary path to B
- B Upper — upper area above B site
- B Platform — area outside B door (distinct from B Upper)
- B Pillars — pillar cover on site
- B Site — plant zone (with breakable wall)

**C Site:**
- C Lobby — attacker approach
- C Main — primary path to C
- C Waterfall — waterfall feature near C (landmark)
- C Mound — raised area near C
- C Door — rotating door at C
- C Gravel — gravel area leading to C
- C Hall — hallway connecting to C
- C Bend — curved section near C
- C Link — passage connecting C to B/Mid
- C Site — plant zone

**Mid:**
- Mid Tiles / Tiles — tiled section of mid
- Mid Top — upper center area

---

#### PEARL (Active — Act 3)

Underwater city. No mechanical interactables. Longest engagement distances on A. Mid control through connector is critical.

**A Site:**
- A Lobby / A Spawn — attacker entry
- A Main — primary attacker path
- A Art / Art — art-corridor approach; risky for attackers
- A Link — connector between Art and A site entry
- A Flowers / Flowers — small nook near A Link
- A Secret / Secret — hidden angle near A
- A Dugout / Dugout — recessed hiding spot near A
- A Restaurant / Restaurant — room adjacent to A main
- A Crane / Crane — checkpoint on attacker approach
- Default Plant A — common plant spot

**B Site:**
- B Lobby / B Spawn — attacker entry
- B Ramp — long open lane from B spawn
- B Screen / Screen — elevated sniper angle position
- B Hall / B Halls — secondary sniper/hold position
- B Tower / Tower — tall position near B
- B Tunnel / Tunnel — lower B connector
- B Club / Club — room approach to B
- B Cubby / Cubby — hiding spot near B entry
- Double Doors — entry to B from mid connector

**Mid:**
- Mid Shops / Shops — shops flanking mid
- Mid Top / U-Hall / Top Mid — upper mid passage
- Mid Connector / Connector — central hallway
- Mid Carpet / Carpet / Bottom Mid — lower mid
- Mid Stairs / Stairs — stairs in mid
- Gutter — accessible from mid connector toward A
- Museum — large open mid space near center

---

#### SPLIT (Active — Act 3)

Vertical map. Heaven/Hell structure on both sites. Ropes provide elevated rotation. High defender advantage historically.

**A Site:**
- A Lobby — attacker entry
- A Sewer — long narrow corridor connecting A Lobby to mid bottom
- A Main — primary approach to A
- A Ramp / Ramps — incline leading from A Main up to A Tower
- A Tower / Tower — elevated position at A
- A Rafters / A Heaven — high platform above A site
- A Hell / Hell — ground level below Rafters
- A Screens / Screens — room next to A site with screens
- A Terminal / Terminal — corner area on A site
- A Site — plant zone

**B Site:**
- B Lobby — attacker entry
- B Link — connector to B
- B Main — primary approach
- B Heaven / Heaven — elevated position above B
- B Rafters — high platform
- B Hell / Hell — below B elevated positions
- B Garage / Garage — garage area near B
- B Stairs — stairs in B approach
- B Alley / Alley — side angle
- Back B / B Back — rear of B site
- B Default — common plant location

**Mid:**
- Mid Top / Top Mid — upper center
- Mid Vents / Vent / Mail — ventilation duct / mail area mid
- Mid Elbow — bend in mid
- Mid Bottom / Bottom Mid — lower mid passage

---

### 3. Inactive Maps (Still Appear in Unrated / Custom)

These maps were rotated out but WILL be encountered in unrated queues:

#### ABYSS (Out since Act 2)
Unique map: no walls on edges, players can fall off the map. Edge/Void/Cliff calls refer to the drop zones.
- A: A Main, A Link, A Site, A Tower, A Bridge, Security, Secret, Vent
- B: B Main, B Link, B Site, B Tower, B Danger, B Nest
- Mid: Top, Library, Catwalk, Bend, Bottom

#### BIND (Out since Act 3)
Two-site teleporter map. No traditional mid — teleporters (TP) create rotation tool.
- A: A Lobby, A Short, A Bath/Showers, A Lamps (U-Hall), A Heaven, A Cubby, A Port (TP exit)
- B: B Lobby, B Long, B Hookah, B Garden/Elbow, B Window, B Hall, B Site, B Port (TP exit)

#### CORRODE (Out since Act 2)
Two-site three-lane. Shallow water paths. Coastal/industrial setting (Ω-Normandy coast).
- A: A Lobby, A Main, A Yard, A Link, A Elbow, A Site
- B: B Lobby, B Main, B Link, B Elbow, B Site, B Tower/Arch
- Mid: Bottom, Stairs, Top, Window

#### ICEBOX (Inactive)
Arctic. Ziplines. Asymmetric layout. 
- A: A Belt, A Pipes, A Nest, A Screen, A Rafters
- B: B Garage, B Green, B Yellow, B Hall, B Snowman, B Hut, B Kitchen, Back B, B Tube, B Orange

#### SUNSET (Inactive)
Downtown LA setting. Three-lane.
- A: A Elbow, A Alley, A Link, A Lobby, A Main
- Mid: Mid Tiles, Mid Courtyard, Mid Top, Mid Bottom
- B: B Lobby, B Market, B Main, B Boba

---

### 4. Universal Cross-Map Callout Terms

These terms appear on MULTIPLE maps with consistent meaning:

| Term | Meaning |
|------|---------|
| Heaven | Any elevated platform/balcony with vertical sight line advantage |
| Hell | Ground-level area directly below Heaven |
| CT / CT Side | Defender spawn-side of map |
| Main | Primary attacker corridor to a site |
| Lobby | Attacker staging area before main corridors |
| Link | Connector passage between two areas |
| Short | Faster/shorter route to site |
| Long | Longer corridor approach to site |
| Back Site / Back B / Back A | Deepest defender position behind the site |
| Default | Standard/common bomb plant position on site |
| Heaven (per-site) | Rafters/elevated position above the site |

---

### 5. ASR Correction Pairs (Whisper-Specific Hazards)

Callouts that are phonetically ambiguous and likely to be misheared by Whisper:

| Spoken | Whisper Risk | Correction |
|--------|-------------|------------|
| "A Ramps" | "Eight Ramps", "A Rance" | → "A Ramps" |
| "A Rafters" | "A Rappers", "A Raftors" | → "A Rafters" |
| "B Heaven" | "Be Heaven", "B 7" | → "B Heaven" |
| "Hookah" (Bind) | "Hooker", "Huka" | → "Hookah" |
| "B Cubby" | "B Covey", "B Cuppy" | → "B Cubby" |
| "Mid Nest" | "Mid Next", "midnest" | → "Mid Nest" |
| "Catwalk" | "Cat Walk", "Catwalk" | → "Catwalk" |
| "A Wine" (Ascent) | "A Vine", "Eline" | → "A Wine" |
| "C Logs" (Haven) | "C Locks", "Sea Logs" | → "C Logs" |
| "A Dish" (Fracture) | "A Dis", "A Ditch" | → "A Dish" |
| "B Arcade" (Fracture) | "B Armacade", "Arcade" | → "B Arcade" |
| "Canteen" (Fracture) | "Can Teen", "Canteen" | → "Canteen" |
| "Mid Tiles" | "Mid Tails", "Midtiles" | → "Mid Tiles" |
| "B Boba" (Sunset) | "B Boba", "B Bova" | → "B Boba" |
| "C Waterfall" (Lotus) | "See Waterfall" | → "C Waterfall" |
| "A Rubble" (Lotus) | "A Rubble" (usually ok) | safe |

---

## Concrete Techniques / Params We Should Adopt

### 1. Callout Gazetteer as Injected Context

Size estimate: ~200 callouts × avg 15 chars = ~3000 chars = ~750 tokens. Acceptable overhead.

Structure for the 8B system prompt injection:
```
MAP CALLOUT VOCABULARY (relay verbatim):
ASCENT: A Lobby, A Wine, A Garden, A Main, A Short, A Link, A Window, A Switch, A Site, A Rafters, Hell, Generator, Green Boxes | B Lobby, B Main, B Lane, B Market, B Door, B Switch, B Site, B Shed, Pizza | Mid Courtyard, Catwalk, Cubby, Tiles, Mid Link, Top Mid, CT Alley
BREEZE: ...
```

This fits in the first-chunk prefill — cacheable with llama-cpp-python prefix caching (see B_prefix_cache_vram.md).

### 2. ASR Hotwords / Domain Prompt

Feed the gazetteer to faster-whisper's `initial_prompt` and/or `hotwords` parameter. Existing `_DOMAIN_PROMPT` in the codebase should include callout nouns. Fixes the "Franz/Prong" class of Whisper mishears on tactical terms.

Example domain prompt addition:
```
Valorant tactical callout: A Ramps, A Rafters, B Heaven, Hookah, Canteen, Catwalk, Mid Nest, A Dish, B Arcade, C Waterfall, A Rubble, Mid Tiles.
```

### 3. Callout Preservation in Relay Normalizer

The relay normalizer (`_normalize_relay_text` or equivalent) must:
- Preserve capitalized callout tokens: "A Ramps" not "a ramps"
- Not paraphrase: "B Main" → do not expand to "the main entrance to B"
- Treat site+callout pairs ("A Ramps", "B Heaven", "C Logs") as atomic tokens in the slot parser

### 4. Map Session State (Optional Enhancement)

If user says "we're on [Map]" or the match-start flow fires, store `current_map` in session state. Inject map-specific callout list as priority exemplars for that session. After the session ends or map changes, reset.

### 5. Inactive Map Coverage

Callouts from Bind, Abyss, Corrode, Icebox, Sunset appear in Unrated play. The gazetteer must cover all 12 maps. Do NOT prune to just the competitive 7.

---

## Risks / Caveats for Our Constraints

### Map Rotation Drift

The pool changes every ~8 weeks. Current (Act 3) pool expires roughly late June / early July 2026 when Act 4 begins. New maps may be added or return. The callout vocab is stable (callout names don't change when maps cycle), so the risk is mainly "new map released with new callout vocabulary".

**Corrode** (released October 2025, patch 11.00) introduced callouts that won't be in older training data. Whisper and the 8B's base weights may not have seen them. Include Corrode callouts explicitly in the domain prompt and system context even though it's currently inactive.

**Mitigation:** Store the gazetteer in `voice_lines.py` or a dedicated `callouts.py` constant file so it can be updated without touching model weights.

### No Official Callout API

Riot does not publish a machine-readable callout list. All data here is from community sources (esports guides, wiki contributors). The "official" names shown in-game (press M on minimap) are the ground truth, but we have no programmatic access to extract them. Some positions have community names that diverge from in-game labels.

**Notable divergences:**
- "Pizza" (Ascent B) — community name, not labeled in-game
- "Hookah" (Bind) — community name for the pipe-room
- "B Boba" (Sunset) — community name for tea shop area
- "Rafters" vs "Heaven" — used interchangeably on Split

Recommendation: Use community names since players use them in voice comms, not necessarily in-game labels.

### Whisper Domain Shift

Callouts are domain-specific proper nouns. Base Whisper (even large-v3 / Parakeet) was not trained on Valorant audio specifically. The domain prompt / hotwords approach is the correct antidote. This is anticheat-safe (no external service, runs on the existing faster-whisper pipeline).

### 8B Context Limit

Josiefied-Qwen3-8B Q5_K_M at 10GB VRAM cap. Full 12-map gazetteer (~750 tokens) + the standard system prompt must fit within the context budget. At a typical relay prompt of 512-1024 tokens total, this is feasible. Do not inject the full callout gazetteer on every turn — inject it once in the static system prefix (cacheable) and rely on prefix caching for zero-cost re-use.

### Anticheat Safety

Callout vocabulary is purely text-based and lives in relay_speech.py / voice_lines.py / prompt strings. No game memory reading, no screen capture, no pixel scanning. The entire callout vocab injection is safe for competitive play.

---

## Sources

- Official VALORANT tweet confirming V26 Act 3 map rotation (Ascent in, Bind out): https://x.com/VALORANT/status/2046574675321299393
- Official VALORANT tweet confirming V26 Act 2 map rotation (Fracture + Lotus in, Abyss + Corrode out): https://x.com/VALORANT/status/2031354389101936835
- pley.gg V26 Act 3 map rotation breakdown: https://pley.gg/valorant/s26a3-map-rotation/
- tracker.gg V26 Act 3 competitive map pool: https://tracker.gg/articles/valorant-v26-act-3-competitive-map-pool-all-you-need-to-know
- thespike.gg current map pool (patch 12.08): https://www.thespike.gg/valorant/maps/map-pool
- strafe.com Fracture + Lotus V26 Act 2 return: https://www.strafe.com/news/read/fracture-and-lotus-rejoin-valorant-map-pool-for-v26-act-2/
- talkesport.com V26 Act 2 map pool announcement: https://www.talkesport.com/news/valorant/valorant-season-2026-act-2-map-pool/
- progameguides.com comprehensive callout guide (all 12 maps): https://progameguides.com/valorant/all-valorant-callouts-for-each-map/
- valorfeed.gg Fracture callouts: https://valorfeed.gg/guides/fracture-valorant-map-guide-callouts
- valorfeed.gg Breeze callouts: https://valorfeed.gg/guides/breeze-valorant-map-guide-callouts
- valorfeed.gg Split callouts: https://valorfeed.gg/guides/split-valorant-map-guide-callouts
- oneesports.gg Lotus callouts: https://www.oneesports.gg/valorant/lotus-callouts-locations/
- jaxon.gg Pearl callouts: https://www.jaxon.gg/all-callouts-on-valorant-map-pearl-explained/
- boosteria.org map callout guide 2026 (active pool confirmed): https://boosteria.org/guides/valorant-map-callouts-guide-2026-terms-rotations
- valorant.fandom.com Corrode map wiki: https://valorant.fandom.com/wiki/Corrode
- esports.net Corrode map guide: https://www.esports.net/wiki/guides/valorant-corrode-map/
- 2026 Valorant Champions Tour — VCT London schedule context: https://liquipedia.net/valorant/VCT/2026
- egamersworld.com 2026 map pool overview: https://egamersworld.com/blog/valorant-competitive-map-pool-2026-what-you-need-t-LZB-3YiZho
