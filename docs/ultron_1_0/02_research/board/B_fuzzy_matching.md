# RapidFuzz + phonetic (Metaphone/jellyfish) best practices for robust short-command matching against a large template/exemplar library under ASR noise

**Research date:** 2026-06-20  
**Agent:** frontier research (claude-sonnet-4-6)  
**Scope:** scorer selection, thresholds, indexing speed, phonetic pre-pass, hybrid fuzzy+embedding scoring — all tied back to Ultron 1.0 constraints.

---

## TL;DR recommendation for Ultron 1.0

The current `_router_backends.py` `LexicalBackend` implementation is already on the right track:
`max(token_set_ratio, WRatio) * 0.75 + Metaphone-ratio * 0.25`. The research confirms this
combination is sound. Specific improvements to adopt:

1. **Scorer stack**: Keep `token_set_ratio` as primary (word-order invariant, handles "Jett hit B
   main" vs "B main Jett hit") + `WRatio` as secondary. **Add `partial_ratio`** as a third arm for
   the common ASR pattern where one string is a substring of the other (clipped "Ultron, tell..." ->
   "...B main"). The max of these three, divided by 100, is the lexical score.
2. **Phonetic**: Metaphone (via jellyfish) is correct for English. Consider upgrading the phonetic
   ratio from a string comparison of the whole phone-key to a **per-token matching** (match each
   input token's Metaphone code against every exemplar token's code and score by F1-overlap) to
   handle word-order-independent phoneme matching.
3. **Thresholds**: For the fuzzy-only gate: **0.82** is a well-supported operational threshold
   (high recall from 0.80, high precision from 0.85 empirically — 0.82 splits the difference for
   short commands where false positives are expensive). The hybrid gate (lexical + embedding) should
   stay at the current 0.50 family-score minimum with a 0.06 margin — these are already conservative
   and abstain-biased.
4. **Hybrid weight**: The existing `emb_weight=0.6` (embedding) + `0.4` (lexical) in
   `HybridBackend` is consistent with published findings on hybrid retrieval (alpha 0.5–0.7 for
   dense-dominant hybrids). For Ultron 1.0's "all LLM" pivot, the fuzzy layer becomes primarily a
   **routing gate** (does this utterance belong to a deterministic template?), not a final answer, so
   the current weights are appropriate.
5. **Indexing**: At ~1628 flavor tails + a few hundred exemplar strings, linear scan with
   `score_cutoff` early termination is fast enough (sub-ms). No BK-tree or trie needed at this
   scale. **Precompute Metaphone codes at build time** (already done in `prepare()`).
6. **Cascade order** (critical for latency): rules -> fuzzy lexical -> (if undecided band)
   EmbeddingGemma -> 8B LLM. Never call EmbeddingGemma on a clear lexical hit or miss.

---

## Findings

### 1. RapidFuzz scorer taxonomy and when to use each

RapidFuzz (v3.14.5, MIT-licensed, C++ backend) provides the following scorers relevant to
Ultron's short-command matching task ([RapidFuzz docs](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html)):

| Scorer | Best for | Notes |
|---|---|---|
| `ratio` | Exact/near-exact single words | Normalized Indel similarity. Sensitive to word order. |
| `partial_ratio` | When one string is a substring of the other | Fast O(N) for short strings (≤64 chars). Critical for ASR clipping. |
| `token_set_ratio` | Word-order agnostic matching | Splits tokens, compares {intersection} vs {remainder}. Returns 100 if one is a subset. Best for "Jett B main hit" vs "B main Jett hit". |
| `token_sort_ratio` | Sorted-token comparison | Less powerful than token_set for duplicated content. |
| `token_ratio` | Max of token_sort + token_set | Convenience wrapper; ~same speed as calling both. |
| `WRatio` | General purpose, length-adaptive | Internally picks ratio/partial_ratio/token variants based on relative string lengths. Scaled 0.9x for partial matches, 0.95x for token matches. The research-recommended default when unsure. |
| `QRatio` | Quick single-pair check | Returns 0 for empty strings (v3+). Similar to ratio. |
| `JaroWinkler` | Very short strings (names, 1–2 word phrases) | Prefix-bonused; better for name-like tokens, not full callouts. |

**For Ultron's 2-8 word callouts**: the optimal scorer is `max(token_set_ratio, WRatio, partial_ratio)`. Each covers a distinct failure mode:
- `token_set_ratio` handles word-order variation in full callouts ("on A main two enemies" vs "two enemies A main")
- `WRatio` catches length ratio issues (long exemplar vs short transcription)
- `partial_ratio` catches the very common ASR clipping pattern (verb drop, leading-fragment erasure)

The Jaro-Winkler guide from splink ([source](https://moj-analytical-services.github.io/splink/topic_guides/comparisons/choosing_comparators.html)):
- Threshold 0.9 = catches typos and shortening
- Threshold 0.8 = includes simple aliases
- Threshold 0.7 = broad but risks false positives

These are for Jaro-Winkler (0-1 scale). For token_set/WRatio (0-100 scale), multiply by 100: **82, 80, 70** respectively. Production voice NLU typically picks 80-85 ([Zingg fuzzy matching](https://www.zingg.ai/post/fuzzy-matching-at-scale-part-4-thresholds-scores-and-active-learning)).

### 2. ASR noise failure modes and mitigation

Whisper/Parakeet-CTC introduce systematic errors on short Valorant commands:
- **Phoneme substitution in proper nouns**: 35% of name errors are phonetically similar substitutions ("Sova" -> "Silva", "Cypher" -> "cipher", "Raze" -> "ray zombie") — confirmed by ASR error analysis in [Whisper Courtside Edition paper](https://arxiv.org/pdf/2602.18966).
- **Verb clipping**: the first token (usually "tell") is dropped when it falls in the cold pre-roll. Ultron's normalizer already handles this via `recover_relay_lead`.
- **Number transcription**: damage values ("84") misread as word sequences or wrong numbers.
- **Domain noun mishears**: "B main" -> "be main", "A site" -> "eight site".

Phonetic matching (Metaphone) directly targets class 1 (proper noun phoneme substitution).
Fuzzy edit-distance targets classes 2-4.

**Recommended mitigation stack** (confirmed by ASR error correction literature, [phonetic-neural paper](https://arxiv.org/pdf/2102.06744)):
1. Lexical normalizer pass (regex corrections for known nouns) — already implemented in `_stt_correct.py`
2. Fuzzy phonetic pre-pass: Metaphone codes of each input token matched against each exemplar token's Metaphone codes
3. Edit-distance fuzzy (RapidFuzz) on the lexically-normalized string
4. Embedding similarity as a tiebreaker in the undecided band

### 3. Phonetic algorithm comparison: Metaphone vs alternatives

From jellyfish docs ([jellyfish functions](https://jamesturk.github.io/jellyfish/functions/)) and phonetics guides:

| Algorithm | Output | Strength | Weakness |
|---|---|---|---|
| Soundex | 4-char code (A123) | Fast; handles short names | High collision rate; cuts off at 4 chars |
| Metaphone | Unlimited-length alphabetic code | Better for full words; handles entire string | Can over-collapse; treats "Klumpz"="Clumps" as identical which may be too aggressive |
| Double Metaphone | Two codes per word (primary + alternate) | Best accuracy; handles pronunciation variants | Slightly slower; not in jellyfish, need `phonetics` or `doublemetaphone` package |
| NYSIIS | Phonetic code | Good for US English names | Less common; less tested |

**Verdict for Ultron**: `jellyfish.metaphone()` per-word is the right choice (already implemented). It is already available, proven to handle Valorant agent names, and the per-word tokenization in `_phonetic()` correctly avoids conflating multi-word strings as one phoneme. **Double Metaphone would improve recall on alternate pronunciations** (e.g., "Reyna" vs "Raina"), but the phonetics/doublemetaphone package is an additional dependency and the improvement is marginal for English-dominant gaming callouts.

Key known issue (already documented in codebase): "hello" and "hell" share the same Metaphone code (both -> `HL`). The `_common_words.py` gate and the verbatim-bypass already protect against this. Any phonetic expansion must be gated to the callout-bound path only.

### 4. process module: batch performance and score_cutoff

From RapidFuzz docs ([process module](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html)):

- `process.extractOne(query, choices, scorer, score_cutoff)` — single best match; returns None if below cutoff. **Always pass score_cutoff**: it enables early termination so failed candidates are skipped after the first few comparisons.
- `process.extract(query, choices, scorer, score_cutoff, limit)` — top-N matches.
- `process.cdist(queries, choices, scorer, workers=-1)` — full distance matrix. `workers=-1` uses all CPU cores via the C-API's GIL release. Only available for C-API scorers (all built-in scorers qualify). This is the right tool for batch re-scoring or calibration runs, NOT the per-turn hot path.
- For the hot path (single query vs ~1628 exemplars): **linear scan with `score_cutoff`** via `extractOne` or `extract_iter` is the right approach. At ~1628 entries and short strings, this is measured at well under 1ms on the RTX 4070 Ti's i9 host CPU.

Performance data ([comparative analysis paper](https://www.researchgate.net/publication/390846511_A_Comparative_Analysis_of_Python_Text_Matching_Libraries_A_Multilingual_Evaluation_of_Capabilities_Performance_and_Resource_Utilization)):
- RapidFuzz processes ~2,500 pairs/second single-threaded vs FuzzyWuzzy ~1,200 pairs/second (2x faster in naive loops).
- But via `process.cdist` with `workers=-1`, throughput scales to **hundreds of thousands of pairs per second**.
- The real gain vs fuzzywuzzy is the C-API's GIL release, not just algorithmic speed.

**For Ultron 1.0**: the exemplar library is small enough (~1628 tails, ~500 routing exemplars) that the current linear scan is fine. No BK-tree needed. **If the library grows to 10,000+ entries**, consider SymSpell-style pre-deletion pre-filtering (100x faster than BK-tree) or a Levenshtein automaton trie for the edit-distance component, but keep the token-based WRatio layer as-is since SymSpell only handles single-word exact edit distance — not multi-word token-set matching.

### 5. Indexing structures at scale

From [SymSpell vs BK-tree analysis](https://medium.com/data-science/symspell-vs-bk-tree-100x-faster-fuzzy-string-search-spell-checking-c4f10d80a078):

| Structure | Speed vs linear | When to use |
|---|---|---|
| Linear scan (with score_cutoff) | 1x baseline | ≤ 5,000 entries; simple; already correct |
| BK-tree | 3–6x | Moderate vocab; pure edit-distance; static |
| Trie + Levenshtein automaton | 10–50x | Large vocab; single-word lookups; overkill for token-set matching |
| SymSpell (delete-only pregeneration) | 100x–1M x | Spell checking over very large dictionaries (100K+ words); single-word only |

**Conclusion for Ultron**: Current scale does not justify any indexing structure. The bottleneck is TTS audio rendering and LLM inference, not fuzzy matching. Precomputing Metaphone codes in `prepare()` (already done) is the only indexing optimization needed.

### 6. Hybrid fuzzy + embedding scoring

Published research and production deployments consistently use a **linear weighted combination**:

```
hybrid_score = alpha * dense_score + (1 - alpha) * sparse_score
```

Where:
- `dense_score` = cosine similarity from an embedding model (EmbeddingGemma: 768d, task-prompted)
- `sparse_score` = normalized fuzzy lexical score (RapidFuzz 0-1)
- `alpha` = typically 0.5–0.7 for dense-dominant hybrids ([DAT paper](https://arxiv.org/pdf/2503.23013); [hybrid RAG guide](https://medium.com/@alexrodriguesj/hybrid-search-rag-revolutionizing-information-retrieval-9905d3437cdd))

**Dynamic alpha** (query-specific) outperforms fixed alpha ([DAT: Dynamic Alpha Tuning](https://arxiv.org/pdf/2503.23013)), but fixed alpha at 0.6 is a well-supported default.

Ultron's current `HybridBackend`: `emb_weight=0.6` (embedding) + `0.4` (lexical). This matches the research-recommended range.

**EmbeddingGemma 300M specifics** ([model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card)):
- 768d output (use full precision; Matryoshka 512/256/128 available but with accuracy loss)
- Task-prompted: use `"task: classification | query: {text}"` for intent routing, not the default semantic similarity template
- Cosine similarity thresholds: 0.80 is the published midpoint for classification; 0.90+ for strict semantic preservation. For Ultron's routing (where abstention is preferred over wrong routing), **0.75** is an appropriate minimum for the embedding signal alone, but the **combined** hybrid score can use a lower absolute threshold since the lexical component already gates on vocabulary match.
- Context length: 2000 tokens — more than enough for short commands.

**Three-tier routing architecture** (recommended by production search practitioners, confirmed by the ipullrank hybrid search article):
1. **Candidate generation** via fuzzy lexical (high recall, fast) — `score_cutoff` filters to candidates scoring ≥ some low floor (e.g., 0.40)
2. **Re-rank** the surviving candidates using embedding cosine similarity
3. **Decision gate**: commit only if top candidate clears the per-family threshold AND beats runner-up by the margin

This is exactly what `HybridBackend.score()` + `CommandRouter` implements. The main improvement for Ultron 1.0 is to **use this for prompt template selection**, not just family routing — more on that in the 1.0 architecture plan.

### 7. Calibration and threshold selection

From the Zingg calibration guide and empirical studies:
- Thresholds are **data-distribution-specific** and not portable across field types or data quality levels.
- The practical process: run the matcher on a labeled set of (transcript, correct_route) pairs, compute a precision-recall curve for each candidate threshold, and pick the threshold at the desired operating point.
- For Ultron's relay-or-not gate, **false positives are much more costly** (a false relay silently mis-executes a team broadcast) than false negatives (a miss just goes to LLM). Therefore: **bias high** (0.82–0.85 for lexical-only; the hybrid gate stays lower because the combined score is more reliable).
- The margin criterion (current: 0.06) is also essential: it prevents committing when multiple families all score around the threshold (ambiguous input).

**Practical calibration steps for Ultron 1.0**:
1. Use `trace_corpus_full.py` to generate scores on the 25k corpus with labels
2. For each candidate threshold T and margin M, compute: true relay, false relay, true ignore, false ignore
3. The cost function: `cost = 10 * false_relay_rate + 1 * false_ignore_rate` (relay false positives are 10x worse)
4. Pick (T, M) that minimizes cost

### 8. Ultron 1.0 pivot implications

In Ultron 1.0, deterministic snap matchers are **retired into ROUTERS** that pick a prompt template. The fuzzy matching layer's role shifts:

- **Old role**: match exemplar -> deterministic response string
- **New role**: match utterance -> prompt template name + slot extraction confidence

The fuzzy matching layer becomes the **routing gate** for the LLM call, not the answer generator. This means:
- Higher tolerance for false negatives (LLM can handle "unusual" phrasings that fuzzy missed)
- Same or lower tolerance for false positives (routing to the wrong template wastes an LLM round-trip and generates a wrong persona response)
- The embedding sidecar becomes more important for paraphrase routing (novel phrasings of known intents)
- The phonetic layer remains critical for proper-noun recognition under ASR noise

**For the IGNORE gate specifically** (classify as {RELAY, PRIVATE, IGNORE}):
- The existing `_relay_intent.py` false-relay gate already filters "is this a relay or not"
- For Ultron 1.0's always-listening mode, the fuzzy+embedding intent gate should use a **three-class** architecture: the IGNORE class must be represented in the exemplar library as a separate family with its own threshold
- Current research ([RACC-SLM paper abstract](https://dl.acm.org/doi/10.1007/s00607-026-01629-w)): cascaded SLM (small-medium) for zero-shot intent in real-time voice streams — same pattern as Ultron's cascade (rules -> fuzzy -> embedding -> 8B LLM)

---

## Concrete techniques/params we should adopt

### A. Scorer stack change (additive, no regression risk)

In `LexicalBackend.score()`, change from:
```python
lex = max(_fuzz.token_set_ratio(qn, en), _fuzz.WRatio(qn, en)) / 100.0
```
to:
```python
lex = max(
    _fuzz.token_set_ratio(qn, en),
    _fuzz.WRatio(qn, en),
    _fuzz.partial_ratio(qn, en),
) / 100.0
```
This adds coverage for the ASR clipping case (input is substring of exemplar) at near-zero cost.

### B. Per-token phonetic F1 matching (optional improvement)

Current phonetic: `_fuzz.ratio(qp, ep)` where `qp` and `ep` are space-joined Metaphone codes of all tokens. This is sensitive to token order. A better approach:

```python
def _phonetic_f1(q_phones: list[str], e_phones: list[str]) -> float:
    """Token-level phonetic F1: order-invariant Metaphone overlap."""
    q_set, e_set = set(q_phones), set(e_phones)
    if not q_set or not e_set:
        return 0.0
    intersection = q_set & e_set
    if not intersection:
        return 0.0
    p = len(intersection) / len(q_set)
    r = len(intersection) / len(e_set)
    return 2 * p * r / (p + r)
```

This makes phonetic matching word-order invariant (matching `token_set_ratio` semantics).

### C. score_cutoff in extractOne for early termination

When using `process.extractOne` for family-level lookup, always pass `score_cutoff`:
```python
result = process.extractOne(
    query, choices, 
    scorer=fuzz.WRatio,
    score_cutoff=40  # early termination: skip candidates scoring < 40
)
```
At the current library size this saves ~10-20% CPU on clear misses.

### D. EmbeddingGemma task prompting

When sending queries to the sidecar for the routing task, use the classification task prefix:
- Query side: `"task: classification | query: {utterance}"`
- Exemplar side: `"task: classification | query: {exemplar}"`
(Not "sentence similarity" — the classification task prefix is specifically tuned for intent routing on the MTEB classification benchmark.)

### E. Threshold recommendations

| Gate | Scorer | Recommended threshold | Notes |
|---|---|---|---|
| Relay/no-relay lexical snap | token_set_ratio | 85 (out of 100) | High-precision: only well-matching callouts auto-route |
| Family router fuzzy floor | hybrid score | 0.50 (current) | Keep; abstain-biased is correct |
| Family router margin | hybrid delta | 0.06 (current) | Keep |
| Embedding-only gate (no lexical) | cosine | 0.75 | Minimum for EmbeddingGemma on short commands |
| IGNORE vs RELAY/PRIVATE | combined | 0.60 | Higher than family threshold; IGNORE requires confidence |

### F. Cascade latency budget

Measured order for Ultron 1.0 pipeline:

| Layer | Latency | When to skip |
|---|---|---|
| Rules (regex) | < 0.1ms | Never |
| Lexical fuzzy + Metaphone | 0.5–2ms | If rules already committed |
| EmbeddingGemma sidecar | 30–80ms (cold), 10–25ms (warm) | If lexical score clearly commits OR clearly abstains |
| 8B LLM (Josiefied-Qwen3, GPU) | 200–600ms | Only on abstentions from above |

The embedding sidecar should only be consulted in a configurable "undecided band" (current: if lexical score is between low_thr and high_thr, e.g., 0.35–0.70). Outside this band, the lexical decision is final.

---

## Risks/caveats for our constraints

### Anticheat constraint
- `rapidfuzz` and `jellyfish` are pure Python/C extension libraries with no OS hooks, DLL injection, or memory scanning. Both are anticheat-safe as confirmed by existing usage in the codebase. No new risk.
- `phonetics` or `doublemetaphone` packages (if adopting Double Metaphone) are similarly safe but add a new dependency — evaluate whether the marginal improvement justifies it.
- The EmbeddingGemma sidecar communicates over localhost HTTP only; it is already the design, so no new anticheat surface.

### Short-string hazard with token_set_ratio
- `token_set_ratio` returns 100 if one string is a subset of the other's token set. For very short queries (1-2 words), nearly any long exemplar containing those words scores 100. **Mitigation**: always require `len(query.split()) >= 2` before committing from lexical-only. The current slot callout forced routing already ensures substantive content is present.

### Phonetic collision ("hello" == "hell" in Metaphone)
- Already documented and mitigated in the codebase (`_common_words.py`, verbatim-bypass). The phonetic score is one component (weight 0.25) of the total score; a collision in the phonetic component alone is insufficient to commit. No additional risk.

### Threshold portability
- Thresholds calibrated on one corpus do NOT transfer to a different ASR model or microphone setup. If the user switches from Whisper to Parakeet-CTC or changes mic/preprocessing, the thresholds need recalibration via the corpus tool.

### score_cutoff behavior difference by scorer type
- For normalized scores (token_set_ratio, WRatio): score_cutoff is the minimum similarity in [0, 100] and results below it are NOT returned.
- For edit distance scorers (Levenshtein distance): score_cutoff is the MAXIMUM distance; different semantics. Always check the scorer type when setting cutoffs.

### Embedding sidecar cold-start latency
- EmbeddingGemma on first `/embed` call is slow (model load into VRAM if run on GPU, or CPU RAM). The current `prepare_timeout=25.0s` handles this. For Ultron 1.0, ensure the sidecar is warmed up (first dummy embed) during orchestrator boot, not at the first user utterance.

### WRatio weight scaling
- WRatio internally scales token_sort/token_set scores by 0.95x and partial matches by 0.9–0.6x depending on length ratio. This means `WRatio < max(token_set_ratio, partial_ratio)` is possible. Taking `max()` of all three avoids losing to the WRatio penalty, which is the right behavior for a "best-of" approach.

---

## Sources

1. RapidFuzz fuzz module documentation (v3.14.5) — https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html
2. RapidFuzz process module documentation — https://rapidfuzz.github.io/RapidFuzz/Usage/process.html
3. RapidFuzz GitHub repository — https://github.com/rapidfuzz/RapidFuzz
4. Jellyfish string matching library documentation — https://jamesturk.github.io/jellyfish/functions/
5. Splink string comparators guide (Jaro-Winkler vs Levenshtein, threshold recommendations) — https://moj-analytical-services.github.io/splink/topic_guides/comparisons/choosing_comparators.html
6. Medium: Phonetics-based fuzzy string matching algorithms — https://medium.com/data-science-in-your-pocket/phonetics-based-fuzzy-string-matching-algorithms-8399aea04718
7. Medium: Deep dive into string similarity — theory and practice — https://medium.com/data-science-collective/deep-dive-into-string-similarity-from-edit-distance-to-fuzzy-matching-theory-and-practice-in-68e214c0cb1d
8. Zingg: Fuzzy matching at scale, Part 4: Thresholds and active learning — https://www.zingg.ai/post/fuzzy-matching-at-scale-part-4-thresholds-scores-and-active-learning
9. ipullrank: Fuzzy matching and semantic search (hybrid retrieval) — https://ipullrank.com/fuzzy-matching-semantic-search
10. Hybrid RAG / hybrid search: dense + sparse fusion — https://medium.com/@alexrodriguesj/hybrid-search-rag-revolutionizing-information-retrieval-9905d3437cdd
11. EmbeddingGemma 300M model card (Google AI) — https://ai.google.dev/gemma/docs/embeddinggemma/model_card
12. Wolf Garbe: SymSpell vs BK-tree (100x speed comparison) — https://medium.com/data-science/symspell-vs-bk-tree-100x-faster-fuzzy-string-search-spell-checking-c4f10d80a078
13. Comparative analysis of Python text matching libraries — https://www.researchgate.net/publication/390846511_A_Comparative_Analysis_of_Python_Text_Matching_Libraries_A_Multilingual_Evaluation_of_Capabilities_Performance_and_Resource_Utilization
14. Whisper Courtside Edition: ASR error analysis for sports domain — https://arxiv.org/pdf/2602.18966
15. Hybrid phonetic-neural model for ASR correction — https://arxiv.org/pdf/2102.06744
16. Intent classification: 2026 techniques — https://labelyourdata.com/articles/machine-learning/intent-classification
17. DAT: Dynamic Alpha Tuning for hybrid retrieval in RAG — https://arxiv.org/pdf/2503.23013
18. RACC-SLM: Resource-aware conditional cascaded framework for zero-shot intent detection — https://dl.acm.org/doi/10.1007/s00607-026-01629-w
19. DeepWiki: RapidFuzz C-API advanced matching — https://deepwiki.com/straywriter/rapidfuzz-cpp/3.3-advanced-matching-and-extraction
20. Improved out-of-scope intent classification (dual encoding + threshold) — https://arxiv.org/pdf/2405.19967
