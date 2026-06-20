# A5: Semantic command router, embedder sidecar & relay-intent gate

Recon date: 2026-06-20. Branch: `claude/infallible-kepler-0a865d`. All line citations are stable to this commit.

---

## Overview

The semantic command router is the **additive fallback layer** that sits beneath all deterministic exact-matchers (relay speech parser, Spotify matcher, identity matcher). It is invoked only when every upstream matcher misses. Its job is to make a **coarse family decision** — `team_callout`, `spotify`, `identity`, `desktop_refuse`, or `conversational` — by scoring the normalized utterance for similarity to curated exemplars. A family wins only when it clears a per-family score threshold AND beats the runner-up by a margin AND is not the conversational anchor. Otherwise the router **ABSTAINS** and the utterance falls through to the LLM.

A parallel but separate component, the **relay-intent gate** (`_relay_intent.py`), is applied much earlier in the pipeline: inside `recover_relay_lead` (the command normalizer), it intercepts bare callouts — utterances that contain a callout keyword but no explicit "tell my team" lead — and decides whether they are live team callouts or stream narration/banter. The gate uses the same embedding sidecar but a different exemplar set (positive relay cloud vs. negative narration cloud).

The **embedding sidecar** (`scripts/embedder_server.py`) is a completely separate process in an isolated Python venv (`C:/STC/ultronVoiceAudio/.venv-embedder`). The main process communicates with it over a loopback HTTP socket (port 8772 by default) using only `urllib` and `numpy`. The embedding model (EmbeddingGemma-300M) is never loaded into the anticheat-pinned main process.

---

## Files & key symbols

### `src/kenning/audio/command_router.py`

| Symbol | Lines | Role |
|---|---|---|
| `RoutingDecision` dataclass | 57–68 | Return type: `family`, `abstained`, `confidence`, `margin`, `reason`, `scores` |
| `CommandRouter.__init__` | 74–95 | Builds; embeds/prepares ALL family exemplars ONCE via `backend.prepare` |
| `CommandRouter.family_scores` | 100–106 | Max-aggregated similarity per family |
| `CommandRouter.route` | 108–131 | Abstention gate: top must NOT be `ABSTAIN_FAMILIES`, must clear per-family threshold, must beat runner-up by `margin_delta`, must be in `DETERMINISTIC_FAMILIES` |
| `get_command_router()` | 142–183 | Lazy singleton; reads config; polls sidecar up to `sidecar_startup_timeout_seconds`; returns `None` (never retries) on any failure |
| `get_embedding_backend()` | 186–196 | Returns the `HybridBackend.emb` field; shared with relay flavor tail-selector |
| `reset_command_router()` | 199–208 | Drops singleton; used by orchestrator's respawn-and-rebuild path |
| `_DEFAULT_THRESHOLD` | imported from `routing_rules` | 0.50 |
| `_DEFAULT_MARGIN` | imported from `routing_rules` | 0.06 |
| `_FAMILY_THRESHOLDS` | imported from `routing_rules` | per-family overrides |

### `src/kenning/audio/_router_backends.py`

| Symbol | Lines | Role |
|---|---|---|
| `SimilarityBackend` ABC | 80–95 | `prepare(exemplars) -> Any`; `score(query, prepared) -> List[float]` |
| `LexicalBackend` | 98–124 | rapidfuzz `token_set_ratio` + `WRatio` (0.75 weight) + Metaphone phonetic ratio (0.25 weight); no model; deterministic |
| `EmbeddingBackend` | 127–217 | HTTP client to sidecar; `/healthz` ping; `/embed` POST; L2-normalizes vectors; 1-entry per-turn cache keyed on `(texts, kind)` |
| `EmbeddingBackend.__init__` | 136–149 | `timeout=0.5` (per-query); `prepare_timeout=25.0` (family embed at startup) |
| `EmbeddingBackend._embed` | 168–201 | Sends `{"texts": [...], "kind": "query"|"document"}`; L2-normalizes result; caches; on failure caches `_EMBED_FAILED` sentinel so remaining families in same turn short-circuit |
| `EmbeddingBackend.score` | 210–217 | Embeds query as "query" kind; computes dot product with pre-embedded exemplar matrix (= cosine after L2 norm); clips to [0,1] |
| `HybridBackend` | 220–321 | Fuses lexical (always) + embedding (when sidecar up); `emb_weight=0.6`; after 3 consecutive embedding failures latches to lexical-only; `try_recover()` re-enables if sidecar returns |
| `get_backend()` | 324–357 | Factory; polls for sidecar `wait_seconds`; builds `HybridBackend` (or degrades to `LexicalBackend`) |

### `src/kenning/audio/_relay_intent.py`

| Symbol | Lines | Role |
|---|---|---|
| `RELAY_POSITIVE_EXEMPLARS` | 35–67 | 46 bare callout phrases (no "tell my team" lead): spotting, self-status, orders, morale, economy |
| `RELAY_NEGATIVE_EXEMPLARS` | 69–142 | 53 non-relay phrases: narration-musing, banter/analysis AT Ultron, advice questions, Marvel/identity, out-of-roster named addressees, addressing Ultron about past calls |
| `RelayIntentGate.__init__` | 163–176 | `threshold=0.06`; binds to the shared `EmbeddingBackend` from the router singleton |
| `RelayIntentGate._ensure` | 179–200 | Lazy bind + prepare; does NOT latch failure (re-tries on next call if sidecar unavailable) |
| `RelayIntentGate.score` | 202–214 | Returns `(max_pos_cosine, max_neg_cosine)` |
| `RelayIntentGate.decide` | 216–221 | `True` if `(pos - neg) >= threshold (0.06)`; `False` if below; `None` if unavailable |
| `get_relay_intent_gate()` | 228–231 | Lazy singleton |
| `relay_intent_ok(text)` | 241–243 | Module-level convenience used by `command_normalizer.recover_relay_lead` |

### `src/kenning/audio/_command_exemplars.py`

| Symbol | Lines | Role |
|---|---|---|
| `_TEAM_CALLOUT` | 26–97 | ~60 exemplars: spotted, abilities, self-status, orders, morale, soundboard relay forms |
| `_SPOTIFY` | 99–150 | ~50 exemplars: play/pause/skip/volume/shuffle/repeat/like commands |
| `_IDENTITY` | 152–168 | 14 exemplars: "who are you", "introduce yourself", etc. |
| `_DESKTOP_REFUSE` | 170–186 | 14 exemplars: screenshot, click, open Discord, scroll, etc. |
| `_CONVERSATIONAL` | 191–221 | 27 exemplars: Marvel, meta, opinions, advice, existential — the abstention anchor |
| `FAMILIES` | 225–231 | Dict mapping family name -> exemplar list |
| `ABSTAIN_FAMILIES` | 235 | `frozenset({"conversational"})` |
| `DETERMINISTIC_FAMILIES` | 244–246 | `frozenset({"team_callout", "identity", "desktop_refuse"})` — note: `spotify` is intentionally excluded |

### `src/kenning/audio/routing_rules.py`

| Symbol | Lines | Role |
|---|---|---|
| `ROUTE_DEFAULT_THRESHOLD` | 268 | `0.50` — min top-family score |
| `ROUTE_DEFAULT_MARGIN` | 269 | `0.06` — min (top − runner_up) |
| `ROUTE_FAMILY_THRESHOLDS` | 270–275 | Per-family overrides: `identity=0.55`, `spotify=0.50`, `team_callout=0.48`, `desktop_refuse=0.50` |
| `NORM2_TEAM_NOUN`, `NORM2_MANGLED_TELL`, `NORM2_TELL_CLASS_VERB` | 211–227 | Editable word-list building blocks for relay-lead normalization regexes |
| `NORM2_MANGLED_TEAM_LEAD_RE`, `NORM2_TELL_TEAM_LEAD_RE` | 235–256 | Built from the above; consumed by `command_normalizer` |

### `scripts/embedder_server.py`

| Symbol | Lines | Role |
|---|---|---|
| `BACKEND` env | 50 | `KENNING_EMBEDDER_BACKEND` — `"sentence_transformers"` (default) or `"fastembed"` |
| `PORT` | 51–52 | `KENNING_EMBEDDER_PORT` or CLI arg 1; default `8772` |
| `MODEL` | 53–57 | `KENNING_EMBEDDER_MODEL` or CLI arg 2; default `google/embeddinggemma-300m` (sentence_transformers) or `BAAI/bge-small-en-v1.5` (fastembed) |
| `DEVICE` | 59 | `KENNING_EMBEDDER_DEVICE`; default `""` (auto); config sets `"cpu"` |
| `QUERY_PROMPT` / `DOC_PROMPT` | 61–62 | `KENNING_EMBEDDER_QUERY_PROMPT` / `_DOC_PROMPT`; enables asymmetric query/document prompting for EmbeddingGemma |
| `_load()` | 69–87 | Loads model at startup; blocks until ready; prints ready log |
| `_embed(texts, kind)` | 90–99 | Calls `encode` (sentence_transformers) or `embed` (fastembed); `kind` selects prompt |
| `_Handler.do_GET("/healthz")` | 111–114 | Returns `{"ok": true, "model": ..., "dim": N, "backend": ...}` |
| `_Handler.do_POST("/embed")` | 118–128 | Decodes `{"texts": [...], "kind": ...}`, returns `{"vectors": [[...]]}` |
| `_parent_watchdog()` | 170–193 | Polls parent PID every 3s; `os._exit(0)` if parent gone; reads `KENNING_EMBEDDER_PARENT_PID` |
| `main()` | 196–213 | `_load()` → start watchdog thread → `ThreadingHTTPServer("127.0.0.1", PORT)` |

### `src/kenning/audio/command_normalizer.py` (relay-intent integration)

| Symbol | Lines | Role |
|---|---|---|
| `_NARRATION_MUSING_RE` | 860–901 | Fast regex pre-filter: first-person musing/recount patterns that are NEVER live relays; zero-cost fallback when sidecar is down |
| `_CALLOUT_SIGNAL` | 742–804 | Positive callout keywords (enemy/spotting/abilities/locations/self-status/orders) |
| `_AGENT_SIGNAL` | 807–810 | Agent name match |
| `_STRONG_CALLOUT_RE` | 818–849 | Unambiguous callout shapes that bypass the semantic gate |
| `recover_relay_lead` | 904–969 | Where `relay_intent_ok` is called; applied to bare callouts after `_NARRATION_MUSING_RE` and `_STRONG_CALLOUT_RE` checks |

### `src/kenning/audio/_tail_selector.py`

| Symbol | Lines | Role |
|---|---|---|
| `select_tail` | 60–end | Uses the SAME shared EmbeddingBackend to re-rank flavor tails within an already-correct (agent, situation) cell; OFF by default unless `KENNING_ENABLE_TAIL_SELECTOR` is set |
| `_THRESHOLD` | 32 | Per-pool-kind abstain floors: `agent=0.30`, `multi=0.26`, `generic=0.20` |

### `src/kenning/config.py`

| Symbol | Lines | Role |
|---|---|---|
| `SemanticRouterConfig` | 3823–3865 | Pydantic config model; all router/sidecar settings with defaults |

---

## Control/data flow

### Boot sequence

1. `Orchestrator.__init__` calls `_start_embedder_sidecar()` (lines 1574–1674) early during boot.
2. The sidecar boots in `C:/STC/ultronVoiceAudio/.venv-embedder` python, loads `google/embeddinggemma-300m` on CPU, binds `127.0.0.1:8772`.
3. Orphan sweep (`sidecar_lock.sweep`) runs first; if an existing owned sidecar is healthy it is reused.
4. Parent-death watchdog thread starts in sidecar; polls orchestrator PID every 3s.
5. At boot-end, orchestrator builds the `CommandRouter` singleton via `get_command_router()`:
   - Reads `config.semantic_router` for `backend`, `sidecar_host`, `sidecar_port`, `embedding_weight`, `sidecar_startup_timeout_seconds`.
   - Polls the sidecar `/healthz` up to `sidecar_startup_timeout_seconds` (default 30s).
   - Builds `HybridBackend(EmbeddingBackend, LexicalBackend, emb_weight=0.6)`.
   - Calls `backend.prepare(exemplars)` for each of the 5 families — each is a batch `/embed` call (generous 25s timeout).
6. If the router built lexical-only (sidecar slow at boot): orchestrator kills and respawns the sidecar, polls up to 45s, calls `reset_command_router()` and rebuilds. (orchestrator.py:1541–1572)

### Per-utterance routing (main loop, orchestrator.py:6773–6883)

```
normalize_command(raw_stt)
    -> recover_relay_lead (command_normalizer.py)
          - if _NARRATION_MUSING_RE matches: leave verbatim (conversational)
          - if _STRONG_CALLOUT_RE matches: prepend "tell my team" (bypass gate)
          - if _CALLOUT_SIGNAL or _AGENT_SIGNAL matches:
              if _NARRATION_MUSING_RE: leave verbatim
              relay_intent_ok(s)  <-- relay-intent gate HERE
                  -> RelayIntentGate.decide(s)
                      -> backend.score(s, prep_pos) -> max cosine pos
                      -> backend.score(s, prep_neg) -> max cosine neg
                      -> (pos - neg) >= 0.06 -> True (relay), False (abstain), None (sidecar down)
              if False: leave verbatim; else: prepend "tell my team"

... upstream exact matchers (relay speech, Spotify, identity, etc.) ...
... all miss ...

CommandRouter.route(normalized_text)  <-- semantic router HERE
    family_scores:
        for each family: max(backend.score(text, prepared[family]))
    abstention gate:
        if top_family in ABSTAIN_FAMILIES: abstain
        if top_score < family_threshold[top_family]: abstain
        if top_score - runner_up < margin_delta (0.06): abstain
        if top_family not in DETERMINISTIC_FAMILIES: abstain
        else: route to family

if routed to "team_callout":
    orchestrator._maybe_handle_relay_speech(user_text, force=True)
elif routed to "identity":
    orchestrator tries identity pool answer on desktop channel
elif routed to "desktop_refuse" (and anticheat active):
    speaks refusal in-character
else (abstained):
    falls through to conversational LLM
```

### Sidecar HTTP protocol

- **Bind address**: `127.0.0.1` only (loopback, never network-accessible)
- **Port**: 8772 (default; `KENNING_EMBEDDER_PORT` or `sidecar_port` in config)
- **GET /healthz** → `{"ok": true, "model": "google/embeddinggemma-300m", "dim": 768, "backend": "sentence_transformers"}`
- **POST /embed** body: `{"texts": ["..."], "kind": "query"|"document"}` → `{"vectors": [[...float...]]}`
- **Transport**: plain JSON over HTTP/1.1. Main process uses ONLY `urllib.request` (no requests/httpx). Vectors returned as raw Python float lists.
- **Normalization**: the sidecar uses `sentence_transformers.encode(normalize_embeddings=True)`, so returned vectors are already L2-unit. The client (`EmbeddingBackend._embed`) L2-normalizes again as a belt-and-suspenders; dot product of two unit vectors = cosine similarity.
- **Asymmetric prompts**: EmbeddingGemma requires separate "query" and "document" prompts. Sidecar uses `prompt_name="query"` for query embeds and `prompt_name="document"` for exemplar embeds (passed via env `KENNING_EMBEDDER_QUERY_PROMPT`/`_DOC_PROMPT`).
- **Per-turn cache**: `EmbeddingBackend._cache_key = (tuple(texts), kind)`. The router scores the same utterance against 5 families in sequence; the cache means only one `/embed` call per turn (not one per family). The relay-intent gate also calls the same `EmbeddingBackend` instance (via `get_embedding_backend()`), so it reuses the same cached vector.

### HybridBackend scoring formula

```
final_score[i] = 0.6 * embedding_cosine[i] + 0.4 * lexical_score[i]
```

Where `lexical_score[i] = 0.75 * max(token_set_ratio, WRatio) / 100 + 0.25 * Metaphone_ratio / 100`.

If embedding is unavailable/latched-off: `final_score = lexical_score`.

### Failure modes and degradation

| Condition | Effect |
|---|---|
| Sidecar down at boot (sidecar_startup_timeout_seconds elapsed) | Orchestrator respawns sidecar, polls 45s, rebuilds router. If still down: lexical-only, logged ERROR |
| Sidecar dies mid-session | `HybridBackend._emb_fails` increments per failed turn; at 3 consecutive fails, latches to lexical-only for session |
| `_maybe_recover_embedding` (orchestrator, ~60s idle) | Pings `/healthz`; re-enables hybrid if sidecar returned |
| Relay-intent gate sidecar down | `decide()` returns `None`; `recover_relay_lead` treats `None` as "keep keyword behavior" (fail-open) |
| Router build exception | `_router_failed = True`; `get_command_router()` returns `None` forever; orchestrator swallows and falls through to LLM |
| `KENNING_ROUTER_WAIT_SECONDS=0` (env) | Build-time sidecar poll skips; uses lexical; tests/CI use this to avoid 30s hang |

---

## Key findings

1. **The semantic router is a pure additive fallback**: every deterministic matcher (relay speech, Spotify, identity, capability dispatch) runs first. The router is invoked only when ALL upstream matchers miss. A family "win" does NOT bypass the downstream handler's own matching — it re-dispatches the original text to that handler with `force=True`.

2. **The relay-intent gate (`_relay_intent.py`) is applied INSIDE the command normalizer** (`recover_relay_lead`), NOT in the semantic router block. It is invoked on bare callouts (no explicit relay lead) before the text even reaches the router. The gate scores against a separate positive/negative exemplar cloud (46 positive, 53 negative examples). Decision threshold is `pos - neg >= 0.06`.

3. **`_NARRATION_MUSING_RE` is the zero-cost pre-filter** before the gate. It fires on first-person self-narration/musing patterns that can be detected syntactically without embedding, avoiding any sidecar call for the most common false-relay sources.

4. **`_STRONG_CALLOUT_RE` bypasses the relay-intent gate**: unambiguous callout shapes (sound info, enemy comp counts, spike/defuse, site-letter callouts) relay unconditionally, because the gate was miscounting legitimate callouts ("I hear sewers", "they have three duelists").

5. **The embedding model is EmbeddingGemma-300M** (`google/embeddinggemma-300m`), an asymmetric query/document model. Query-side and document-side prompts are both named `"query"` and `"document"` via EmbeddingGemma's `SentenceTransformer.prompts` mechanism. This model runs on CPU (config `sidecar_device: "cpu"`).

6. **The sidecar and the relay-intent gate share the same `EmbeddingBackend` instance**. The per-turn 1-entry cache on `(texts, kind)` means a bare callout that passes through `recover_relay_lead` (gate) AND triggers the router later in the same turn uses at most 2 sidecar calls (one for the gate query, one for the router query — these are different texts).

7. **`spotify` is intentionally NOT in `DETERMINISTIC_FAMILIES`**: Spotify exemplars compete in scoring purely to prevent a music command from mis-routing to `team_callout`, but a `spotify` win causes abstain-to-LLM rather than dispatch. The exact Spotify matcher upstream handles all real Spotify commands.

8. **The orphan-prevention stack is multi-layered**: (a) `_parent_watchdog` in the sidecar self-exits 3s after detecting orchestrator dead; (b) `sidecar_lock.reap_stray_embedders` sweeps orphan embedder processes at boot; (c) `ZombieKiller` backstop with 1h hard timeout; (d) `_kill_embedder_sidecar` on clean shutdown tree-kills the process.

9. **Thresholds are described as starting points for calibration**. The code comments explicitly note that real values must be tuned on live transcripts. The current defaults have not been calibrated against a labeled corpus.

10. **`_tail_selector.py` reuses the same `EmbeddingBackend`** for semantic re-ranking of flavor tails within an already-correct (agent, situation) cell. It is OFF by default (`KENNING_ENABLE_TAIL_SELECTOR` unset) to avoid latency. Not part of the routing decision path.

---

## Flags & config

All live in `src/kenning/config.py:3823–3865` (`SemanticRouterConfig`) with the key `semantic_router:` in `config.yaml`.

| Key | Default | Effect |
|---|---|---|
| `semantic_router.enabled` | `True` | Master on/off for the router |
| `semantic_router.backend` | `"hybrid"` | `"hybrid"`, `"embedding"`, or `"lexical"` |
| `semantic_router.embedding_weight` | `0.6` | Weight of embedding score in hybrid fusion (lexical gets 1-w=0.4) |
| `semantic_router.sidecar_enabled` | `True` | Whether to spawn the sidecar at all |
| `semantic_router.sidecar_host` | `"127.0.0.1"` | Sidecar bind/connect address |
| `semantic_router.sidecar_port` | `8772` | Sidecar TCP port |
| `semantic_router.sidecar_python` | `"C:/STC/ultronVoiceAudio/.venv-embedder/Scripts/python.exe"` | Path to isolated venv python |
| `semantic_router.sidecar_script` | `"scripts/embedder_server.py"` | Embedder script path |
| `semantic_router.sidecar_backend` | `"sentence_transformers"` | `"sentence_transformers"` or `"fastembed"` |
| `semantic_router.sidecar_model` | `"google/embeddinggemma-300m"` | HuggingFace model id |
| `semantic_router.sidecar_query_prompt` | `"query"` | Named prompt for query embeddings (EmbeddingGemma) |
| `semantic_router.sidecar_doc_prompt` | `"document"` | Named prompt for document embeddings |
| `semantic_router.sidecar_device` | `"cpu"` | `"cpu"`, `"cuda"`, or `""` (auto) |
| `semantic_router.sidecar_hf_cache` | `"C:/Users/alecf/.cache/huggingface/hub"` | Override HF cache path |
| `semantic_router.sidecar_startup_timeout_seconds` | `30.0` | Poll timeout at boot for sidecar ready |
| `semantic_router.sidecar_orphan_sweep_enabled` | `True` | Boot-time orphan sweep of prior sidecar |
| `semantic_router.sidecar_pidfile_path` | `""` | Pidfile path; `""` → `~/.kenning/embedder_sidecar.json` |
| `ROUTE_DEFAULT_THRESHOLD` (routing_rules.py:268) | `0.50` | Min top-family cosine score to commit |
| `ROUTE_DEFAULT_MARGIN` (routing_rules.py:269) | `0.06` | Min top-vs-runner_up margin to commit |
| `ROUTE_FAMILY_THRESHOLDS` (routing_rules.py:270–275) | see below | Per-family overrides |
| — `identity` | `0.55` | Higher: identity is precise, avoid relaying to "who are you" |
| — `team_callout` | `0.48` | Slightly lower: err toward relay for callouts |
| — `spotify` | `0.50` | Same as default |
| — `desktop_refuse` | `0.50` | Same as default |
| **Env vars** | | |
| `KENNING_ROUTER_WAIT_SECONDS` | unset (uses config) | Override sidecar startup poll timeout; set to `0` in tests/CI |
| `KENNING_EMBEDDER_PORT` | `8772` | Sidecar port env override |
| `KENNING_EMBEDDER_MODEL` | see above | Model env override |
| `KENNING_EMBEDDER_BACKEND` | `"sentence_transformers"` | Backend env override |
| `KENNING_EMBEDDER_THREADS` | `2` | fastembed thread count |
| `KENNING_EMBEDDER_DEVICE` | `""` | Device env override |
| `KENNING_EMBEDDER_QUERY_PROMPT` | `""` | Query prompt name env override |
| `KENNING_EMBEDDER_DOC_PROMPT` | `""` | Doc prompt name env override |
| `KENNING_EMBEDDER_PARENT_PID` | set by orchestrator | PID for watchdog; falls back to `os.getppid()` |
| `KENNING_ENABLE_TAIL_SELECTOR` | unset | Enable semantic tail re-ranking (OFF by default) |
| `TRANSFORMERS_CACHE` / `HF_HUB_CACHE` | set from config if `sidecar_hf_cache` nonempty | HF cache override in sidecar env |

---

## Extension points

1. **Adding a new route family**: add exemplar list in `_command_exemplars.py`, add entry to `FAMILIES`, add to `DETERMINISTIC_FAMILIES` if it has a handler, add a threshold override in `routing_rules.ROUTE_FAMILY_THRESHOLDS`, add a dispatch branch in `orchestrator.py` around line 6796.

2. **Adding relay-intent exemplars** (positive or negative): append to `RELAY_POSITIVE_EXEMPLARS` or `RELAY_NEGATIVE_EXEMPLARS` in `_relay_intent.py`. The gate lazily re-prepares; on a live session it requires a restart (the backend prepare happens on first `_ensure()`).

3. **Tuning thresholds**: edit `ROUTE_DEFAULT_THRESHOLD`, `ROUTE_DEFAULT_MARGIN`, `ROUTE_FAMILY_THRESHOLDS` in `routing_rules.py`. These are the only places (post-relocation) — no code changes needed.

4. **Swap the embedding model**: change `sidecar_model` in config and (for asymmetric models) `sidecar_query_prompt` / `sidecar_doc_prompt`. The sidecar auto-detects prompt names from the `SentenceTransformer.prompts` attribute.

5. **Swap to fastembed backend** (for a no-GPU-driver scenario): set `sidecar_backend: "fastembed"` and `sidecar_model: "BAAI/bge-small-en-v1.5"`. Fastembed is in the main venv; symmetric embedding (no prompt distinction).

6. **`_NARRATION_MUSING_RE`** in `command_normalizer.py` is the editable syntactic fast-filter before the semantic gate. Adding new first-person musing patterns here saves sidecar calls.

7. **`_STRONG_CALLOUT_RE`** is the bypass for unambiguous callout shapes. Extend it for new shape classes that the gate consistently misses.

8. **Tail selector** (`_tail_selector.py`): set `KENNING_ENABLE_TAIL_SELECTOR=1` to activate semantic re-ranking of flavor tails. No code change needed.

---

## Retire-not-remove candidates (u1.0)

In the Ultron 1.0 pivot (all responses through 8B LLM; deterministic snaps become routers/exemplars):

1. **`CommandRouter` as a coarse router stays but its dispatch changes**: instead of re-dispatching to a deterministic handler (relay speech), a confident `team_callout` hit should select a curated **prompt template** for the 8B LLM (injecting the callout text as slot, adding snap exemplars as in-context shots). The `RoutingDecision` dataclass is reusable.

2. **`DETERMINISTIC_FAMILIES` shrinks**: under u1.0, LLM handles all response generation. `team_callout`, `identity`, `desktop_refuse` families become intent-routing hints rather than bypass routes. The existing dispatch branches in orchestrator can be replaced by template selection.

3. **`RelayIntentGate` stays**: the relay-intent gate solves a fundamental ambiguity problem (narration vs. live callout) that persists even with an LLM in the loop. It should be kept as the pre-classification step feeding intent to the LLM prompt builder.

4. **`_NARRATION_MUSING_RE` stays**: syntactic fast-filter is always valuable; cheaper than an embedding call.

5. **`_STRONG_CALLOUT_RE` stays**: these bypass the gate for unambiguous shapes; continue to mark them as relay intent.

6. **Exemplar sets become in-context examples**: `RELAY_POSITIVE_EXEMPLARS`, `RELAY_NEGATIVE_EXEMPLARS`, and the family exemplar lists (`_TEAM_CALLOUT`, `_CONVERSATIONAL`, etc.) are natural candidates for inclusion in the LLM prompt as few-shot examples, not just similarity targets.

7. **`_tail_selector.py` becomes more relevant in u1.0**: if the LLM generates the relay text and deterministic tails are appended, semantic re-ranking of tails is a cheap quality improvement. Enabling `KENNING_ENABLE_TAIL_SELECTOR` by default is reasonable.

8. **`_CONVERSATIONAL` exemplar family becomes the LLM-dispatch signal**: already acts as the abstention anchor; in u1.0, "closest to conversational" explicitly means "give this to the 8B LLM with the appropriate system prompt."

9. **The sidecar itself is reusable**: the loopback HTTP protocol and EmbeddingGemma-300M sidecar are sound as-is for u1.0. The only change needed is ensuring the sidecar is kept alive if the embedding is needed for intent classification at higher frequency (always-listening mode).

---

## Gotchas

1. **`spotify` win does NOT dispatch to Spotify handler**: it causes abstain-to-LLM. A Spotify command that somehow misses the upstream exact matcher AND scores highest as `spotify` will still go to the LLM. This is intentional but may surprise.

2. **Gate threshold `0.06` is very low**: the relay-intent margin of `pos - neg >= 0.06` is permissive. Because the exemplar clouds are curated to be discriminative, the empirical margins on correctly-classified texts are larger, but a miscalibration or a new OOD utterance class could cause false relays. No labeled calibration set exists.

3. **Per-turn cache is per-instance, not per-thread**: `EmbeddingBackend._cache_key` / `_cache_val` are instance variables with no lock. The router is a singleton, and the voice loop is single-threaded, so this is safe today. Any concurrency (e.g., parallel wake-word + relay processing) would cause a race.

4. **Relay-intent gate does NOT latch failure**: unlike `HybridBackend` (which latches to lexical after 3 fails), `RelayIntentGate._ensure()` re-attempts on every call when the sidecar is down, paying a TCP connection attempt per bare-callout utterance. On a dead sidecar, this adds a `0.5s timeout * N_bare_callouts_per_minute` overhead.

5. **Sidecar pidfile path default is `""`** which resolves to `~/.kenning/embedder_sidecar.json`. If `~/.kenning/` does not exist, `sidecar_lock.write` silently fails. Boot still works but a subsequent orphan sweep may not recognize the sidecar as owned.

6. **`recover_relay_lead` is called from `command_normalizer.normalize_command`**, which is called BEFORE the upstream exact matchers. So the relay-intent gate fires on a pre-normalized text that may still have disfluencies. The gate exemplars are phrased as natural speech (no leading junk stripped), so this is consistent, but be aware that the gate sees a pre-correction text.

7. **`DETERMINISTIC_FAMILIES` check is the LAST gate** in `CommandRouter.route`: a family can score high, clear threshold, clear margin, yet NOT be routed if it's not in `DETERMINISTIC_FAMILIES`. Currently `conversational` is excluded via `ABSTAIN_FAMILIES`; `spotify` is excluded via not being in `DETERMINISTIC_FAMILIES`. Both conditions must be checked when adding a new family.

8. **`HybridBackend._emb_fails` counter is per-turn, not per-call**: a `_SidecarUnavailable` (short-circuit from cache) does NOT increment the counter. Only a real exception in `score()` increments it. After the 3rd real failure in 3 different turns, the backend latches to lexical permanently for the session.

9. **`EmbeddingBackend.prepare_timeout=25.0`**: at router build time, each family's exemplars are embedded with a 25s timeout. With 5 families of ~15–60 exemplars each, a cold model load can take longer. The code retries once (2s sleep) before degrading to lexical-only. If the GPU is busy with game loading, this retry may still time out.

10. **The sidecar logs to `stderr=DEVNULL`**: sidecar subprocess stdout and stderr are both redirected to `DEVNULL` in `Popen`. The sidecar's startup "ready" message and any model load errors are silently discarded. Debugging sidecar issues requires running it manually.

---

## Open questions

1. **What are the real calibrated thresholds?** The code comments say these are "starting points" requiring calibration on real transcripts. Has any labeled calibration set been assembled? Are the current values (0.50 default, 0.06 margin) empirically validated?

2. **Always-listening mode (u1.0)**: the relay-intent gate currently fires only on bare callouts in `recover_relay_lead`. In always-listening mode (no explicit wake word), EVERY utterance needs intent classification (talk to Ultron / talk to someone else / relay to team). How does the relay-intent gate extend to this three-way classification? The current two-cloud design (positive relay vs. negative non-relay) does not distinguish "talking to Discord/teammates in voice" from "talking to Ultron."

3. **Addressing classification vs. relay-intent**: the addressing classifier (`kenning/audio/zero_shot.py`, `rules.py`, `classifier.py`) and the relay-intent gate are separate systems with overlapping concerns. In u1.0, should they be unified into a single pre-LLM intent classifier?

4. **Sidecar per-turn latency at always-listening frequency**: at 30 utterances/minute (always-listening), the sidecar may receive 30+ `/embed` calls/minute. At `timeout=0.5s` per call, and given CPU-mode EmbeddingGemma, what is the actual P99 latency? Has it been measured under load?

5. **EmbeddingGemma-300M vs. lighter options**: EmbeddingGemma-300M at CPU produces ~tens of ms per query. Would `BAAI/bge-small-en-v1.5` (fastembed, ~30M params) be sufficient for the 5-family coarse classification? Has any ablation been done?

6. **The `spotify` family is in `FAMILIES` but not `DETERMINISTIC_FAMILIES`**: this means a Spotify command that somehow reaches the router will be sent to the LLM, not Spotify. Under u1.0 (all responses through LLM), this becomes the correct behavior — but the Spotify exact matcher will need to survive as an upstream L0 layer, or the LLM will need to handle all Spotify API calls.

7. **`reset_command_router()` in tests**: test isolation calls this, but `_router_failed` is also cleared. If a test causes the sidecar to become unavailable, subsequent test code calling `get_command_router()` will attempt a full build (including 30s sidecar poll unless `KENNING_ROUTER_WAIT_SECONDS=0`). Is `KENNING_ROUTER_WAIT_SECONDS=0` documented as a required test-mode env var?

8. **`relay_intent_ok` is called in `recover_relay_lead` which is inside `normalize_command`**: this is extremely early in the pipeline — before STT vocab correction has been applied. Does the relay-intent gate's exemplar set account for STT noise / uncorrected agent name variants?

9. **Three-way command classification for u1.0**: the pivot requires distinguishing (A) Discord/party chat, (B) talking to stream, (C) talking to Ultron for ME-ONLY reply. The current system has no classification for (A) and (B) — it only distinguishes "relay to team" vs. "everything else." What signals/exemplars would distinguish these?

10. **Verbosity modes (no/low/high) and flavor tail on/off in u1.0**: these are prompt-driven in the new design. The `_tail_selector.py` and flavor tail gate (`flavor_tails_enabled()`) are the current opt-in mechanisms. Will they remain as config-driven flags feeding prompt construction, or be replaced by a verbosity parameter in the prompt?
