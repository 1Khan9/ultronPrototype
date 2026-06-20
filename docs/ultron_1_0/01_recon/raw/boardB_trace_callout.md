# B1: TRACE "Sova hit 84" and "Sova hit 84, Breach hit 97" end-to-end

## Overview

This document traces two literal transcript strings through the live Kenning/Ultron
pipeline on the current `main` branch. The inputs arrive as raw STT output and travel
through normalization, relay matching, snap callout building, flavor-tail addition, TTS
synthesis, and final playback on the team-mic channel.

**Both inputs are bare callouts with no explicit relay lead ("tell my team ...").**

Key conclusion: both inputs route deterministically to the damage snap handler in
`_as_snap_callout` (relay_speech.py:4617). Neither the LLM nor the slot-grammar parser
(`_parse_callout_slots`) is reached. The compound form is split into two facts and each
is resolved independently; the results are joined as a single utterance with one shared
flavor tail. The `_looks_like_slot_callout` function mentioned in MEMORY.md (commit
`da28d22`) exists on the `stream-build` branch only and is NOT present on main.

---

## Files & key symbols (path:line tables)

| File | Role | Key symbols |
|------|------|-------------|
| `src/kenning/pipeline/orchestrator.py` | Main event loop; owns dispatch order | `_maybe_handle_relay_speech` (3428), `_is_relay_command` (3126), `normalize_command` call (6130), lean relay block (6757), semantic router (6782-6868) |
| `src/kenning/audio/command_normalizer.py` | Normalizes raw STT to canonical routing text | `normalize_command` (975), `recover_relay_lead` (904), `_STRONG_CALLOUT_RE` (818), `_CALLOUT_SIGNAL` (742), `_AGENT_SIGNAL` (807), `relay_intent_ok` call (964), `correct_callout_stt` call (1048) |
| `src/kenning/audio/relay_speech.py` | Relay matching, snap building, TTS integration | `match_relay_command` (1704), `_normalize_speech` (613), `_NARRATION_LEAD_RE` (1060), `_RELAY_PATTERNS` (119-217), `build_relay_line` (6012), `_as_snap_callout` (4327), damage handler (4617-4630), `_as_compound_callout` (4780), `_split_compound` (4750), `_parse_callout_slots` (4284), `_M1_DMG` (4276), `relay_tts_text` (3619), `play_to_device` (6626), `_shape_for_team` (6600) |
| `src/kenning/audio/_stt_correct.py` | Valorant-aware STT correction | `correct_callout_stt` (459) |
| `src/kenning/audio/_relay_intent.py` | Semantic relay-intent gate (embedding sidecar) | `relay_intent_ok` (241), `RelayIntentGate.decide` (216), threshold=0.06 |
| `src/kenning/audio/_ultron_pools.py` | Flavor tail pool definitions | `_FLAVOR_DAMAGE`, `_FLAVOR_ENEMY` (imported at relay_speech.py:3673-3676) |
| `src/kenning/audio/_agent_flavor.py` | Per-agent contextual flavor tails | `AGENT_FLAVOR` dict (imported at relay_speech.py:3740) |
| `src/kenning/audio/_tail_schema.py` | TailEntry schema + situation taxonomy | `entries`, `situation_for_payload`, `build_active_tags` (imported at relay_speech.py:3751-3754) |
| `config.yaml` | Runtime configuration | `relay_speech.enabled`, `relay_speech.rephrase`, `relay_speech.output_device`, `relay_speech.max_line_chars` |

---

## Control/data flow

### Shared preamble (both inputs)

1. **Wake word fires** (orchestrator.py state machine, line ~950): raw PCM captured
   from mic. `_trim_wake_from_capture` removes the wake-word audio region from the
   buffer before Whisper sees it.

2. **Whisper STT** produces transcript text. Assume clean STT for this trace:
   `user_text = "Sova hit 84"` (or `"Sova hit 84, Breach hit 97"`).

3. **Wake-word-only check** (orchestrator.py:6037-6046): `_WAKE_REMNANT_RE.match`
   confirms the transcript has content after the wake token. "Sova hit 84" passes.

4. **Addressing check** (orchestrator.py:6052-6105): if in follow-up window,
   `_is_relay_command(user_text)` is called first. For the bare "Sova hit 84" form,
   `match_relay_command("Sova hit 84")` is called with the raw text. This will return
   None because the text has no relay lead and is not a bare clutch/encourage. So the
   zero-shot addressing classifier runs instead. In the wake-word path (normal case),
   the classifier is bypassed.

5. **`_record_dialogue_turn`** saves the raw transcript to dual history (orchestrator.py:6111).

6. **`normalize_command("Sova hit 84")`** (orchestrator.py:6130-6145):

   a. `_strip_leading_junk` -> unchanged (no filler/wake prefix on "Sova hit 84")

   b. `_RUNON_TEAM_LEAD_RE.sub` -> unchanged

   c. Various single-pass subs (repeat mishear, team possessive, give-team-to, drop
      possessive, bare-ask, someone-lead) -> unchanged

   d. `_canonicalize_directive_lead` -> unchanged (no team-verb lead)

   e. `_strip_scaffold` -> unchanged (no numbered prefix, no say-directive)

   f. Zero-mistakes gate: NOT `_NOT_A_CALLOUT` (no question word), NOT
      `_SPOTIFY_SIGNAL`, NOT `_REPORTED_QUESTION_GATE`, NOT `_REPORTED_REACTION_RE` ->
      falls through to STT correction.

   g. **`correct_callout_stt("Sova hit 84")`** (command_normalizer.py:1048):
      - Stage 0: phrase mishears -> unchanged
      - Stage 1: context rules -> unchanged
      - Stage 1.5: `_slot_agent_correct` -> unchanged ("Sova" already canonical)
      - Stage 2: token-level fix: "Sova"->"Sova" (canonical), "hit"->"hit" (no mishear),
        "84"->"84"
      Result: **"Sova hit 84"** (unchanged)

   h. **`recover_relay_lead("Sova hit 84")`** (command_normalizer.py:904-969):
      - Not `_HAS_RELAY_LEAD` (no relay verb)
      - Not `_NOT_A_CALLOUT`
      - Not `_REPORTED_RESPOND_RE`
      - Not `_WANT_TEAM`, `_TRAILING_RELAY_TAIL`, `_TEAM_LEAD_NOVERB`, `_TEAM_LEAD`
      - `_STRONG_CALLOUT_RE.match("Sova hit 84")`: The strong-callout pattern requires
        an agent name PLUS a location/ability/status word from a specific list (main,
        site, long, short, mid, heaven, hell, window, garage, tree, cat, plat, connector,
        link, ramp, market, sewer, spawn, cubby, elbow, pit, rafters, stairs, ult, ulted,
        ulting, walled, smoked, flashed, darted, caged, stunned, droned, naded, mollied,
        half, low, one shot, dead, down, cracked, tree, nest, snake, baiting, baited,
        baits, flanking, lurking, peeking, rotating, pushing). "hit" and "84" are NOT in
        this list -> **`_STRONG_CALLOUT_RE` does NOT match**.
      - `_AGENT_SIGNAL.search("Sova hit 84")`: "Sova" is a roster agent -> **YES**
      - `_CALLOUT_SIGNAL.search("Sova hit 84")`: no match ("hit" not listed there either)
      - Not `_NARRATION_MUSING_RE`
      - **`relay_intent_ok("Sova hit 84")`** is called:
        - If the embedding sidecar (embeddinggemma) is UP: scores against positive/negative
          exemplars with threshold=0.06. "Sova hit 84" semantically resembles positives
          like "one shot on the Sova", "their Chamber is one-tapping from long" ->
          expected True (relay).
        - If the sidecar is DOWN: returns None -> falls back to keyword behavior ->
          prepends "tell my team " anyway (same result).
      - Result: `"tell my team Sova hit 84"` (prepend added by recover_relay_lead:968)

   Final normalized text: **`"tell my team Sova hit 84"`**
   (Different from raw: `changed=True` logged at orchestrator.py:6140)

7. **Intent recognizer** (orchestrator.py:6153): not matched (relay not registered as intent).

8. **Capability routing** (orchestrator.py:6211): only wired when `coding_voice is not
   None` (the full desktop stack). In lean gaming boot, this block is skipped entirely.

### Single callout: "Sova hit 84"

**User text after normalization**: `"tell my team Sova hit 84"`

9. **Relay speech handler** (orchestrator.py:6757-6771, lean path; or 6388 in full path):
   `self._maybe_handle_relay_speech("tell my team Sova hit 84")` is called with
   `force=False`.

10. **`_maybe_handle_relay_speech`** (orchestrator.py:3428-3681):

    a. Imports relay_speech functions, checks `cfg.enabled=True`.

    b. **STT repair variants** (orchestrator.py:3467-3485):
       - `stripped = _strip_leading_wake_remnant("tell my team Sova hit 84")` -> unchanged
       - `correct_callout_stt("tell my team Sova hit 84")` -> unchanged
       - `correct_callout_stt("tell my team Sova hit 84")` -> unchanged
       - `variants = ["tell my team Sova hit 84"]` (all variants are the same string)

    c. **`match_relay_command("tell my team Sova hit 84", names=...)`** (relay_speech.py:1704):

       i. `cleaned = _normalize_speech(_LEADING_ARTIFACT.sub("", text.strip()))`:
          - `_LEADING_ARTIFACT` -> no "1." or "2." prefix -> unchanged
          - `_normalize_speech`: KAY/O slash fix, filler strip, abbrev subs -> unchanged
          - `cleaned = "tell my team Sova hit 84"`

       ii. Bare morale check: `_BARE_CLUTCH_RE.match("tell my team Sova hit 84")` -> No
           `_BARE_ENCOURAGE_RE.match` -> No

       iii. Narration gate: `_NARRATION_LEAD_RE.search("tell my team Sova hit 84")` ->
            No (no "I should ...", "part of me", etc.)

       iv. Pattern loop: **`_RELAY_PATTERNS[0]`** (relay_speech.py:123-127):
           ```
           re.compile(rf"^(?:please\s+)?tell\s+{_GROUP}[\s,:]+"
                      rf"(?:that\s+...)?(?P<payload>.+)$", re.IGNORECASE)
           ```
           "tell my team Sova hit 84": "tell" + "my team" matches `_GROUP` + `[\s,.:]+`
           + payload = "Sova hit 84"

       v. **payload = "Sova hit 84"**

       vi. `_strip_verbatim_suffix("Sova hit 84")` -> ("Sova hit 84", False)
           `_strip_verbatim_prefix("Sova hit 84")` -> ("Sova hit 84", False)
           `verbatim = False`

       vii. `_payload_has_content("Sova hit 84")` -> True (more than a filler word)

       viii. **Returns `RelayCommand(payload="Sova hit 84", raw_text="tell my team Sova hit 84")`**
             (addressee defaults to "team", compose=False, verbatim=False)

    d. `command` is not None. Not muted (`_relay_runtime_enabled=True`).

    e. Roast=False, fun_fact=False -> falls through to `build_relay_line`.

    f. **Thinking mode** (orchestrator.py:3549-3554): `thinking_mode_enabled()` returns
       `_thinking_mode_enabled` (default False from env `KENNING_THINKING_MODE`).
       Therefore `_rephrase = rephrase and thinking_mode_enabled() = True and False = False`.
       **rephrase=False** -> LLM is skipped entirely.

11. **`build_relay_line(command, llm, rephrase=False, max_chars=360, recent_lines=[...])`**
    (relay_speech.py:6012):

    a. `flavor_tails_enabled()` check (line 6048): default True (env
       `KENNING_FLAVOR_TAILS` = "1"). Flavor-OFF path skipped.

    b. `command.verbatim = False` -> verbatim path skipped.

    c. `_render_target_registry(command, recent_lines)` -> None (not a hello/ask-day).

    d. `command.directive != "hello"`, `!= "ask_day"` -> those paths skipped.

    e. `_strip_relay_wrapper("Sova hit 84")` -> "Sova hit 84" (no wrapper prefix).

    f. `_as_curated_command(command)` -> None (not a curated-command pattern).

    g. `_as_curated_reaction(command)` -> None (not a social reaction).

    h. `command.roast=False`, `command.fun_fact=False` -> skipped.

    i. compose=False, directive=None, no context -> not morale, not greet/farewell, not
       calm, not criticize, not compliment, etc.

    j. `_is_identity_question("Sova hit 84")` -> False.

    k. `_as_known_fact(command)` -> None.

    l. `_is_morale_phrase("Sova hit 84")` -> False.

    m. `_apply_snap_registry("Sova hit 84", recent_lines)` -> None (not clutch/nice-try
       snap registry hit).

    n. `_as_clutch("Sova hit 84", recent_lines)` -> None.

    o. `_as_consolation_or_praise("Sova hit 84", recent_lines)` -> None.

    p. **`_as_snap_callout(command, recent_lines)`** (relay_speech.py:4327):

       - `payload = "Sova hit 84"`; `p = "Sova hit 84"` (rstrip punctuation -> unchanged)
       - `_is_compound = len(_split_compound("Sova hit 84")) >= 2`:
         `_split_compound` on "Sova hit 84": no dash/semicolon/also/plus/as-well-as;
         ", and " / "," splits only before `_NEWFACT_SUBJECT` (which "hit" is not).
         Result: `["Sova hit 84"]` (1 part) -> `_is_compound = False`
       - `_ff = _payload_flavor_facts("Sova hit 84")` (agents=["Sova"], locs=[], counts=[], abils=[])
       - addressee="team" -> named-addressee branch NOT taken
       - `_as_question_relay("Sova hit 84")` -> None (not a question)
       - `_AGENT_SELECT_FULL_RE.match("Sova hit 84")` -> None
       - `_THANK_YOU_RE.match("Sova hit 84")` -> None
       - careful check: `re.match(r"^careful[,]?\s+", "Sova hit 84")` -> None
       - death call: `re.match(r"^i...\s+(?:died|dead|down|...)")` -> None
       - `_FP_LEAD_RE.match` -> None (no "I'm ..." lead)
       - "i have" match -> None
       - "i saw/see <count> <place>" -> None
       - leading count: `_LEADING_COUNT_RE.match("Sova hit 84")` -> None
       - count+movement: no count prefix -> None
       - spike: `re.match(r"^spike\b", "Sova hit 84")` -> None
       - `_LAST_LEAD_RE.match` -> None
       - "all enemies" -> None
       - "they have <weapon/ult>" -> None
       - "they walled/smoked/etc." -> None
       - "they are pushing/going/etc." -> None
       - `_as_literal_echo("Sova hit 84", recent_lines, "team")`: checks echo patterns.
         "Sova hit 84" doesn't match the echo patterns (no "they are", "our team", etc.) -> None
       - `_ENEMY_LEAD_RE.match("Sova hit 84")` -> None (no "they/their/enemy" prefix)
       - `_as_enemy_action("Sova hit 84")` -> None
       - `_as_agent_position("Sova hit 84")` -> None (no position/action word)
       - **"I hit <agent> for <n>" check**: `re.match(r"^i\s+(?:hit|tagged|...)\s+(?:the\s+|their\s+)?...",
         "Sova hit 84")` -> None (doesn't start with "i")
       - **"<agent> hit <n>" damage handler** (relay_speech.py:4617):
         ```python
         m = re.match(r"^(?P<a>[A-Za-z/ ]+?)\s+hit\s+(?:(?:them|someone|...)\s+for\s+)?(?P<n>\d{1,3})(?:[\s,]+(?P<loc>.+))?$", "Sova hit 84", re.IGNORECASE)
         ```
         - MATCH: `a="Sova"`, `n="84"`, `loc=None`
         - `_canon_agent("Sova")` -> **"Sova"** (canonical)
         - `loc=""` (no location)
         - **Returns `flav(f"Sova hit 84.", _FLAVOR_DAMAGE)`**
         - `flav(callout, pool)` calls `_flavor_ctx("Sova hit 84.", "damage", recent_lines, **_ff)`
         - `_flavor_ctx` picks the LRU-based flavor tail from `_FLAVOR_DAMAGE` pool,
           possibly referencing the agent "Sova" in a contextual tail
         - `_join_tail("Sova hit 84.", tail)` -> `"Sova hit 84. <flavor tail>."`

    q. `snap = "Sova hit 84. <FLAVOR_DAMAGE tail>."` (not None)
    r. **`return _cap_line(snap, 360)`**

12. **`relay_tts_text(line)`** (relay_speech.py:3619):
    - `_TTS_NAME_PRONUNCIATION` subs: no Tejo or other pronunciation-special agent in "Sova hit 84"
    - "A" in line? The line is "Sova hit 84. <tail>". If the flavor tail contains "A"
      site, it would be converted: `_A_SITE_RE.sub("eigh", ...)`. Otherwise unchanged.
    - Result: TTS-pronounced version (typically unchanged for "Sova hit 84.")

13. **TTS synthesis**: `synthesize(relay_tts_text(line))` produces PCM+sample_rate via
    the Kokoro engine.

14. **Channel delivery** (orchestrator.py:3573-3681):
    - `_broadcast_submit(pcm, sr)` -> OBS/stream broadcast mirror (fail-open)
    - `_monitor_submit(pcm, sr)` -> user's own speakers echo (if `echo_to_user=True`)
    - `_viz_submit(pcm, sr)` -> OBS waveform overlay
    - `_ptt_hold()` -> PTT key pressed (if enabled)
    - `play_to_device(pcm, sr, device_index, cancel_event=_ri)`:
      - Polyphase resample to device native rate
      - `_shape_for_team(f, out_rate)`: rumble-HP + RMS normalize -20dBFS +
        comfort-noise floor -58dBFS + tanh soft-clip (gated by `KENNING_RELAY_TEAM_DSP`)
      - Written chunked (100ms) to VoiceMeeter Input -> Valorant voice codec
    - `_ptt_release()` after clip drains
    - Team mic receives: **"Sova hit 84. <FLAVOR_DAMAGE tail>."**

15. **Post-play** (orchestrator.py:3650-3681):
    - `relay:spoken` logged with device, seconds, line preview
    - `_trace_turn_flow(raw=..., normalized="Sova hit 84", route="snap", channel="team_mic")`
    - `ring.append(line)` adds to recent-lines ring for anti-repeat
    - `_relay_follow_up_seconds = 120.0` (from config)
    - Returns True (turn consumed)

---

### Compound callout: "Sova hit 84, Breach hit 97"

The raw STT text is `"Sova hit 84, Breach hit 97"`.

**Step 6 (normalization)**: `normalize_command("Sova hit 84, Breach hit 97")`

- `_AGENT_SIGNAL.search("Sova hit 84, Breach hit 97")` -> YES ("Sova" or "Breach")
- `_STRONG_CALLOUT_RE.match("Sova hit 84, Breach hit 97")`:
  The pattern has `(?:my\s+|their\s+|our\s+|the\s+)?(?:Sova|Breach|...)\b.*\b(?:main|site|long|...)\b`
  "Sova hit 84, Breach hit 97" - starts with agent, but "hit 84, Breach hit 97" has
  no location word from the list -> pattern may not match
  Actually wait - "Breach" IS in the roster list inside `_STRONG_CALLOUT_RE` which uses `.*\b`:
  the pattern is: agent + `.*` + one of those location/ability words. "Breach hit 97" has
  none of those -> `_STRONG_CALLOUT_RE` does NOT match.
- `relay_intent_ok("Sova hit 84, Breach hit 97")` -> expected True (strong callout)
- Result: **`"tell my team Sova hit 84, Breach hit 97"`**

**Step 10 (`match_relay_command("tell my team Sova hit 84, Breach hit 97")`):**

- `cleaned = "tell my team Sova hit 84, Breach hit 97"`
- Bare morale / narration gate -> unchanged
- `_RELAY_PATTERNS[0]` matches: "tell" + "my team" + "," separator + payload
  - payload = **"Sova hit 84, Breach hit 97"**
- Returns `RelayCommand(payload="Sova hit 84, Breach hit 97", raw_text=..., addressee="team")`

**Step 11 (`build_relay_line`):** rephrase=False (thinking mode off)

- Flavor-ON path (same as single)
- `_as_snap_callout(command, recent_lines)`:
  - `p = "Sova hit 84, Breach hit 97"` (no punctuation to strip)
  - **`_split_compound("Sova hit 84, Breach hit 97")`** (relay_speech.py:4750):
    - ` Sova hit 84, Breach hit 97 ` (padded)
    - No dash/semicolon/also/plus
    - `re.sub(r"\s*,\s*(?=" + _NEWFACT_SUBJECT + r")", " | ", ...)`:
      "Breach" is in `_ROSTER_CANON` (included in `_NEWFACT_SUBJECT`) -> the ", B"
      before "reach" is matched -> replaced with " | "
    - Result: `" Sova hit 84 |  Breach hit 97 "` -> parts = ["Sova hit 84", "Breach hit 97"]
  - **`_is_compound = True`** (len >= 2)
  - Because `_is_compound=True`, the code reaches the early-return None path for
    compound at `_as_snap_callout` (it only returns None when it falls through all the
    handlers). But actually - the compound flag only blocks SPECIFIC handlers:
    - question relay: blocked
    - agent select: blocked
    - thank-you: blocked
    - careful: blocked
    - The damage handler at 4617 is NOT gated on `_is_compound`

    So: `_as_snap_callout(command, recent_lines)` with compound payload still hits the
    damage handler. BUT: `re.match(r"^(?P<a>[A-Za-z/ ]+?)\s+hit\s+...", "Sova hit 84, Breach hit 97")`:
    - `a` is lazy `[A-Za-z/ ]+?` -> tries shortest first -> "Sova" matches "Sova"
    - "hit" matches
    - `n=\d{1,3}` -> "84"
    - `(?:[\s,]+(?P<loc>.+))?` -> captures `loc = "Breach hit 97"`
    - `loc.split()` = 3 words -> `len(loc.split()) <= 5` -> True
    - Returns `flav(f"Sova hit 84, Breach hit 97.", _FLAVOR_DAMAGE)`

  Wait - but that's the WHOLE compound being treated as a single fact with "Breach hit 97"
  as a "location". This is wrong behavior - the loc part "Breach hit 97" is the second
  damage call, not a location.

  Actually re-reading: the damage regex captures `loc` as `(m.group("loc") or "").strip().rstrip(".!?,;:")`.
  Then: `len(loc.split()) <= 5` -> "Breach hit 97" = 3 words <= 5 -> would return
  `flav(f"Sova hit 84, Breach hit 97.", _FLAVOR_DAMAGE)`.

  But this returns a snap immediately, BEFORE `_as_compound_callout` is called. So for the
  compound payload the damage handler fires on the WHOLE payload treating "Breach hit 97"
  as a trailing location note.

  **Wait** - I need to re-trace. `build_relay_line` (line 6267):
  ```python
  if (not getattr(command, "compose", False)
          and not getattr(command, "context", None)
          and not getattr(command, "verbatim", False)):
      snap = _as_snap_callout(command, recent_lines)
      if snap is not None:
          return _cap_line(snap, max_chars)
      # COMPOUND ...
      det_line, leftover = _as_compound_callout(command, recent_lines)
  ```

  So `_as_snap_callout` is called first. For `p="Sova hit 84, Breach hit 97"`:
  - `_is_compound = True` (because `_split_compound` returns 2 parts)
  - The damage regex (`re.match`) on "Sova hit 84, Breach hit 97" does match with
    `loc="Breach hit 97"` (3 words <= 5).
  - Returns `flav("Sova hit 84, Breach hit 97.", _FLAVOR_DAMAGE)`

  This means the compound IS handled as a single damage fact by `_as_snap_callout`, not
  by `_as_compound_callout`. The compound splitter is not reached.

  **The spoken output is**: `"Sova hit 84, Breach hit 97. <FLAVOR_DAMAGE tail>."`

  The damage handler treats "Breach hit 97" as a location note for "Sova" rather than a
  separate callout. This is a semantic mismatch but syntactically produces the correct
  text for the teammates because both facts are in the output and the sentence reads
  naturally.

  **However**: If the `_is_compound` flag DID block the damage handler (it does NOT currently),
  then `_as_compound_callout` would split the two facts and produce:
  - "Sova hit 84." + "Breach hit 97." joined as `"Sova hit 84. Breach hit 97."` with a
    single enemy flavor tail (relay_speech.py:4848-4851).

  **Current actual behavior**: The WHOLE compound string "Sova hit 84, Breach hit 97"
  is matched by the damage regex as agent="Sova", n="84", loc="Breach hit 97" -> the
  spoken line is `"Sova hit 84, Breach hit 97. <FLAVOR_DAMAGE tail>."` which DOES
  convey both pieces of information to teammates in a natural-reading form.

---

### What `_parse_callout_slots` does (and why it doesn't apply)

`_parse_callout_slots("Sova hit 84")` (relay_speech.py:4284):
- Tokens: ["Sova", "hit", "84"]
- "sova" -> `_canon_agent` -> "Sova" (types.add("agent"))
- "hit" -> NOT in `_M1_DMG` = {"shot", "lit", "cracked", "hurt", "one-shot", "one-tap",
  "damaged", "dinged", "tagged", "chunked"} -> NOT a recognized DMG slot
  -> NOT in `_M1_COUNT`, `_LOC_TOKENS`, `_M1_ACTION`, `_M1_OWNER`, `_M1_CONNECTORS`
  -> **returns None (residual token)**

**"hit" is NOT in `_M1_DMG`**. This is confirmed at relay_speech.py:4276-4277. The
MEMORY.md notes that "hit" was ADDED to `_M1_DMG` in commit `da28d22` (stream-build
branch). That commit is NOT on main. On main, `_parse_callout_slots` cannot parse
"Sova hit 84" as a valid callout.

The dedicated damage handler (lines 4615-4630) DOES handle "hit" via a dedicated regex,
but this is separate from `_parse_callout_slots`.

**`is_complete_tactical_callout("Sova hit 84")`** (relay_speech.py:5977):
- strips lead -> "Sova hit 84"
- calls `_parse_callout_slots("Sova hit 84")` -> None (as above)
- Returns **False**

This function is used by the optional early-endpoint feature (`KENNING_SNAP_EARLY_ENDPOINT`,
default off). With it off, no effect on the trace.

---

### The semantic router (lean boot only)

After the deterministic relay matcher in the lean boot (orchestrator.py:6757-6771), if
`_maybe_handle_relay_speech` returns False, the semantic command router runs
(orchestrator.py:6782-6883):
- `get_command_router().route(user_text)` returns a `RouteDecision`
- If `family == "team_callout"` and not abstained: `_maybe_handle_relay_speech(user_text, force=True)`
  is called

For "Sova hit 84" or "Sova hit 84, Breach hit 97" with the "tell my team ..." prefix
already prepended by the normalizer, `_maybe_handle_relay_speech` SUCCEEDS at step 9
above (relay match succeeds), so the semantic router is never reached.

If the normalizer had NOT prepended the prefix (sidecar down, no strong-callout shape),
the semantic router would see "Sova hit 84" directly and likely route it as `team_callout`
(it resembles "one shot on the Sova" from the positive exemplars), then call
`_maybe_handle_relay_speech("Sova hit 84", force=True)` which creates
`RelayCommand(payload="Sova hit 84", raw_text="Sova hit 84")` and proceeds to
`build_relay_line` identically.

---

## Key findings

1. **Neither "Sova hit 84" nor "Sova hit 84, Breach hit 97" has an explicit relay lead**
   in the raw STT. They reach the relay via `recover_relay_lead` prepending "tell my team"
   because `_AGENT_SIGNAL` matches "Sova" (and "Breach") and `relay_intent_ok` returns True
   (or None with keyword-fallback behavior).

2. **The damage handler at relay_speech.py:4617 catches both inputs** via the regex
   `^(?P<a>[A-Za-z/ ]+?)\s+hit\s+(?:...)?(?P<n>\d{1,3})(?:[\s,]+(?P<loc>.+))?$`. For
   the single form payload="Sova hit 84": clean match, loc=None. For the compound
   payload="Sova hit 84, Breach hit 97": match with loc="Breach hit 97" (3 words, within
   the 5-word limit), producing `"Sova hit 84, Breach hit 97."` as one sentence.

3. **The compound is NOT split by `_split_compound`** for these inputs in the current code
   path. `_as_snap_callout` is called first (before `_as_compound_callout`) and the damage
   handler fires on the whole payload. The compound splitter would only be reached if
   `_as_snap_callout` returned None.

4. **"hit" is not in `_M1_DMG`** (relay_speech.py:4276-4277). So `_parse_callout_slots`
   cannot parse either input. The damage handler (4617) uses a dedicated regex instead.
   On the `stream-build` branch (commit `da28d22`), "hit" was added to `_M1_DMG`, but
   this is NOT on main.

5. **Thinking mode is OFF by default** (`KENNING_THINKING_MODE=0`). Therefore `rephrase=False`
   is passed to `build_relay_line` for ALL relay commands on main. The 3B LLM is NEVER
   called in the relay path in default configuration. Every output is fully deterministic.

6. **Flavor tails are ON by default** (`KENNING_FLAVOR_TAILS=1`). The damage handler adds
   a `_FLAVOR_DAMAGE` pool tail to the callout. This tail is agent-contextual when
   `AGENT_FLAVOR["Sova"]["damaged"]` is non-empty.

7. **`relay_speech.rephrase: true` in config.yaml** (line 1836) is overridden by the
   thinking-mode gate in the orchestrator. So even with `rephrase: true` in config, the
   LLM is only invoked when `thinking_mode_enabled()` returns True.

8. **The `_looks_like_slot_callout` function** (mentioned in MEMORY.md for commit `da28d22`,
   the stream-build branch) is NOT present in the main branch codebase. It was added as an
   orchestrator-level shortcut to force-relay slot callouts before the semantic router;
   on main, the equivalent path is the `_AGENT_SIGNAL`-based relay_intent gate in the
   normalizer.

9. **The spoken output for "Sova hit 84"**: `"Sova hit 84. <FLAVOR_DAMAGE tail>."` where
   the tail is picked LRU from `_FLAVOR_DAMAGE` pool (imported from `_ultron_pools.py`),
   possibly referencing the agent "Sova" via contextual AGENT_FLAVOR entries.

10. **The spoken output for "Sova hit 84, Breach hit 97"**: `"Sova hit 84, Breach hit 97. <FLAVOR_DAMAGE tail>."` - treated as one damage callout on "Sova" with the second hit
    as a trailing loc note. Both facts reach the team but the structure is semantically
    "Sova hit 84, [location: Breach hit 97]" rather than two independent facts.

11. **Channel**: VoiceMeeter Input -> Valorant voice codec (team_mic). The relay is also
    teed to the OBS broadcast mirror (`_broadcast_submit`) and the user's monitor speakers
    (`_monitor_submit`, gated by `echo_to_user=True` in config).

12. **`relay_tts_text`** converts "A" site references to "eigh" pronunciation. "Sova hit 84"
    has no "A" so it is unchanged. The flavor tail may trigger it if it contains "A site".

---

## Flags & config

| Key | Location | Default | Effect on trace |
|-----|----------|---------|-----------------|
| `relay_speech.enabled` | config.yaml:~1828 | true | Must be true or relay is skipped entirely |
| `relay_speech.rephrase` | config.yaml:1836 | true | Only effective when `thinking_mode_enabled()=True`; otherwise ignored |
| `relay_speech.output_device` | config.yaml:1835 | "Voicemeeter Input" | PortAudio device for team mic delivery |
| `relay_speech.max_line_chars` | config.yaml:1837 | 360 | Hard cap on final spoken line |
| `relay_speech.echo_to_user` | config.yaml:1838 | true | Tees relay audio to user's own speakers via `_monitor_submit` |
| `relay_speech.follow_up_seconds` | config.yaml:1850 | 120.0 | Follow-up window after a relay |
| `KENNING_FLAVOR_TAILS` | env var | "1" (True) | Controls `_flavor_tails_enabled`; OFF -> no flavor tails, bare callout only |
| `KENNING_THINKING_MODE` | env var | "0" (False) | Controls `_thinking_mode_enabled`; ON -> LLM rephrase is used |
| `KENNING_RELAY_TEAM_DSP` | env var | unset (off) | Gates `_shape_for_team` audio conditioning (HP + normalize + comfort noise + clip) |
| `KENNING_RELAY_VM_LEVEL_GUARD` | env var | off | VoiceMeeter level guard boot check (default off) |
| `KENNING_SNAP_EARLY_ENDPOINT` | env var | off | Early VAD endpoint when `is_complete_tactical_callout` fires (not reached for "hit" on main) |
| `relay_speech.addressee_names` | config.yaml | Valorant agent roster | Closed vocab for named addressees |
| `_relay_intent.RelayIntentGate.threshold` | `_relay_intent.py:168` | 0.06 | Minimum `pos_sim - neg_sim` for relay-intent gate to approve bare callout |

---

## Extension points

1. **`_RELAY_PATTERNS`** (relay_speech.py:119-217): Add a new `re.compile(...)` entry to
   recognize new relay phrasing. Each entry captures `(?P<payload>.+)`.

2. **`_M1_DMG`** (relay_speech.py:4276-4277): Add damage vocabulary ("hit", "tapped",
   "melted", "bopped") to make `_parse_callout_slots` recognize damage calls as valid slot
   callouts. Note: "hit" was added on stream-build (commit `da28d22`) but not merged to main.

3. **`_as_snap_callout`** (relay_speech.py:4327): The ordered handler chain. Add a new
   specialized handler (regex + return) above the `_parse_callout_slots` fallback to handle
   new tactical patterns.

4. **`_parse_callout_slots`** (relay_speech.py:4284): Add tokens to `_M1_DMG`, `_M1_ACTION`,
   `_LOC_TOKENS`, `_M1_COUNT`, `_M1_OWNER`, or `_M1_CONNECTORS` to widen what parses as a
   slot callout.

5. **`_split_compound` / `_NEWFACT_SUBJECT`** (relay_speech.py:4750, 4737): The compound
   splitter. "Sova hit 84, Breach hit 97" splits correctly because "Breach" is in
   `_ROSTER_CANON` (hence in `_NEWFACT_SUBJECT`). For a non-roster compound splitter could
   be extended.

6. **`_FLAVOR_DAMAGE`** (imported from `_ultron_pools.py`): The damage flavor pool. Add or
   edit tail lines. For Ultron 1.0, this becomes a prompt template or few-shot exemplar
   bank.

7. **`AGENT_FLAVOR`** (in `_agent_flavor.py`): Per-agent + situation-tagged contextual
   flavor tails. Add entries keyed by agent name and situation ("damaged", "spotted",
   "ult", "utility") to get contextual tails ("Sova damaged -- he'll drone before he dies").

8. **`voice_lines.SNAP_REGISTRY`** (relay_speech.py:6246): Data-driven snap registry
   (SnapRule). Add a SnapRule matching a payload pattern and a response pool for new
   snap categories without modifying match_relay_command.

9. **`RELAY_POSITIVE_EXEMPLARS`** (`_relay_intent.py:35-67`): Add "Sova hit 84, Breach hit 97"
   here to bias the intent gate toward recognizing damage callouts with no "tell my team"
   lead.

10. **`relay_route_info`** (relay_speech.py:5647): Mirror of `build_relay_line` dispatch for
    testing-mode logging. Update when adding a new snap route.

---

## Retire-not-remove candidates (u1.0)

These components become ROUTERS that detect intent, inject exemplars, or pick prompt
templates, but should remain intact as code:

1. **`match_relay_command`** (relay_speech.py:1704): Becomes the intent detector for
   "is this a relay, and what kind?" for the 8B LLM router. The regex set stays; it now
   returns a classification rather than driving a deterministic output.

2. **`_as_snap_callout`** entire handler chain (relay_speech.py:4327-4720): The 34+
   specialized handlers become a CURATED EXEMPLAR LIBRARY. The actual damage handler
   (4617) provides in-context few-shot examples: for an input like "Sova hit 84", the
   router would inject `("Sova hit 84.", "Sova hit 84. <damage tail>.")` as exemplars into
   the 8B prompt, showing the register (terse, literal, damage-tail). The handlers are NOT
   removed; they become the training/exemplar generation source.

3. **`_FLAVOR_DAMAGE`, `_FLAVOR_ENEMY`, `_FLAVOR_COMMAND`, `_FLAVOR_SELF`** pools: Become
   in-prompt style guidance ("DAMAGE register: short, literal, fact-preserving, one
   character tail") rather than random-pick runtime sources. The 1628 TailEntry library
   (in `_agent_flavor.py`) becomes the few-shot style corpus for the 8B.

4. **`_split_compound`** (relay_speech.py:4750): The compound-fact splitter stays as a
   routing helper: when multi-fact input is detected, the 8B receives the split facts as
   separate context items, ensuring each fact is preserved.

5. **`_RELAY_PATTERNS`** (relay_speech.py:119-217): The strict relay-lead regex set stays as
   the primary RELAY INTENT gate, moved BEFORE the 8B call to confirm relay intent with zero
   latency (no embedding needed for explicit "tell my team X" forms).

6. **`relay_tts_text`** (relay_speech.py:3619): Stays as a pure TTS post-processor to handle
   phonetic corrections (A-site, agent name pronunciations).

7. **`_shape_for_team`** (relay_speech.py:6600): DSP conditioning stays unchanged.

8. **`recover_relay_lead` + `_STRONG_CALLOUT_RE` + `relay_intent_ok`** (command_normalizer.py):
   These become the u1.0 "is this a team relay?" intent gate. The embedding sidecar
   (`_relay_intent`) provides semantic routing for bare callouts without explicit leads.

---

## Gotchas

1. **"hit" not in `_M1_DMG`**: `_parse_callout_slots` returns None for "Sova hit 84".
   The damage snap fires via a separate dedicated regex (4617), not the slot grammar.
   `is_complete_tactical_callout` returns False for these inputs (early-endpoint feature
   cannot fire). This is a potential consistency gap.

2. **Compound treated as single damage fact**: "Sova hit 84, Breach hit 97" with payload
   passed to `_as_snap_callout` hits the damage handler treating "Breach hit 97" as a
   location suffix. This accidentally preserves both facts in the output but breaks the
   semantic structure (it's not `loc`, it's a second agent+damage pair). If the location
   field were longer than 5 words, `_as_snap_callout` would return None and
   `_as_compound_callout` would then correctly split and handle each fact independently.

3. **Relay intent gate controls "tell my team" prepend**: Without the embeddinggemma
   sidecar running, `relay_intent_ok` returns None -> falls back to keyword behavior
   (prepend anyway if `_AGENT_SIGNAL` matches). With the sidecar running, a low-confidence
   damage callout could be vetoed (False) and fall to the desktop LLM as a conversational
   turn. The threshold=0.06 is low (intentionally fail-open).

4. **Thinking mode and `rephrase` config decouple**: `config.yaml relay_speech.rephrase:
   true` does NOT mean the LLM is used. The actual gate is `thinking_mode_enabled()` which
   defaults to False. Operators expecting LLM rephrasing must set `KENNING_THINKING_MODE=1`
   or say "Ultron, thinking mode on".

5. **`_looks_like_slot_callout` is absent on main**: The orchestrator on main has no
   pre-semantic-router slot-callout force-path for bare callouts like "Jett hit 84". The
   stream-build branch has this (commit `da28d22`), but it was not merged. Without it,
   bare damage callouts that fail the relay-intent gate fall to the router as a fallback.

6. **`_A_SITE_RE` in `relay_tts_text`**: If a flavor tail contains "A" (e.g., "They do
   not leave A."), `relay_tts_text` converts it to "eigh" in the spoken version. The
   displayed/logged line stays clean ("A"), but the team hears "eigh site". This is the
   intended behavior (Kokoro mispronounces "A" as the letter otherwise).

7. **Double STT correction in the relay handler**: `_maybe_handle_relay_speech`
   (orchestrator.py:3467-3485) runs `correct_callout_stt` on the ALREADY-NORMALIZED text.
   Since `normalize_command` already ran `correct_callout_stt` (command_normalizer.py:1048),
   this is a double correction. Both are idempotent on already-clean text so there is no
   corruption risk, but it is redundant for clean inputs.

8. **PTT uses `rawhid` backend** (pinned, no serial fallback per memory). If the PTT
   device is absent, `_ptt_hold()` / `_ptt_release()` are no-ops. The relay audio still
   plays; the team mic key is just not pressed.

---

## Open questions

1. **Will `relay_intent_ok("Sova hit 84")` return True or None in practice?** The
   embeddinggemma sidecar must be running for a True/False result. If it returns None
   (sidecar down), the keyword-fallback path prepends the relay lead anyway (correct
   behavior for this input). Worth confirming with a live test.

2. **For the compound "Sova hit 84, Breach hit 97"**: is the current behavior (treating
   "Breach hit 97" as a location suffix of the Sova damage fact) acceptable for Ultron 1.0,
   or should the compound path be enforced? With `_is_compound=True`, the damage handler
   still fires. One fix: add a guard `if _is_compound: return None` after the damage handler
   if there's a real compound. Alternative: add "hit" to `_M1_DMG` and let `_parse_callout_slots`
   handle both facts cleanly through `_as_compound_callout`.

3. **What flavor tail is actually spoken?** The exact string depends on `_FLAVOR_DAMAGE`
   pool contents (in `_ultron_pools.py`) and the LRU rotation state. The pool was not
   read in this trace. For Ultron 1.0 design, the tail is a prompt-engineering concern.

4. **Is the `is_complete_tactical_callout` early-endpoint feature actually deployed?** The
   config key `KENNING_SNAP_EARLY_ENDPOINT` defaults to off. If "hit" were in `_M1_DMG`,
   damage callouts would benefit from early endpoint (VAD closes sooner, lower latency).

5. **Why does `recover_relay_lead` not have a dedicated "agent hit N" strong-callout
   pattern?** The `_STRONG_CALLOUT_RE` covers agent+location but not agent+damage. Adding
   `r"(?:Sova|Breach|...)\s+hit\s+\d{1,3}"` to `_STRONG_CALLOUT_RE` would make "Sova hit 84"
   relay without needing the embedding sidecar at all (purely deterministic).

6. **Does `_AGENT_SIGNAL` matching guarantee relay?** Only if the sidecar approves or
   returns None. A streamer saying "their Sova knows this map a little too well" also
   matches `_AGENT_SIGNAL`, but `relay_intent_ok` should return False (it is in the
   negative exemplars). If it returns None (sidecar down), that line would be erroneously
   relayed.
