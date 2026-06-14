# Comprehensive loop — base5 (seed 5) HAND analysis + fix plan (by me, not agents)

Baseline metrics (asr_base5, 1608 spoken / 20k matcher): matcher clean 0.991, false-relay 0,
gates ALL 0 (OOV/fallback/isolation), ASR-coverage 0.996, fact-retention 0.945
(owner 0.81), inversion 0.0037, hallucination 0.013, compound-zero-loss 0.925,
LLM-flag 0.19 (token-metric inflated by legit rephrase), flavor coverage 0.67,
soundboard-max-repeat 17, AUDIO blips 6.84/1000 (target <=2).

## Issue clusters (from reading every flagged case verbatim)
1. **"ask <teammate> if <clause>"** -> relays "If <clause>." literally (named-question
   handler covers how/what/where, not 'if'). FIX: add 'if/whether' -> pose the yes/no
   question to the addressee ("Harbor, have you used your cove?").
2. **Enemy-register flavor on TEAMMATE-directed lines** (praise/advice/question to our
   agent gets an enemy contempt tail: "...perfect. They chose right poorly."). FIX: do
   NOT apply enemy flavor when the line is addressed to / about OUR agent (named
   addressee, or 'my/our <agent>'); use command/none.
3. **Economy SAVE-line parrot** on non-eco 'save' ("Jett save the dash" -> "We save this
   round..."; "their eco round" -> "We have insufficient credits"). FIX: tighten
   _as_economy_callout (don't fire on 'save <ability/noun>' or enemy-subject eco) + a
   post-LLM guard that rejects a verbatim economy/consolation EXAMPLE line when the
   input category doesn't match.
4. **Confabulated agent callouts** (dominant hallucination): vague input -> invented
   specific callout ("lead with util"->"Viper walled B"; "retake B now"->"Two Sova...";
   invented mid-line vocatives "Calm down, Jett. ..."). FIX: (a) extend invented-vocative
   strip to MID-line ", <RosterName>," not in input; (b) post-LLM: reject an output that
   introduces an agent+ability/position callout absent from the input (hallucinated
   tactical claim) -> abstain to literal/fallback.
5. **Identity-question + tactical-fact compound** drops the tactical fact. FIX: the
   compound splitter should peel the identity-question piece and still relay the tactical
   piece (or route the tactical piece deterministically).
6. **Ownership inversion on possessives** ("our Sage rez, their Sage dead" -> "Their Sage
   rezzed"; "their lurker free kills" -> "our lurker"). FIX: strengthen _repair/inversion
   guard on our<->their with an explicit possessive-agent subject check.
7. **Audio blips**: trailing-burst on over-truncated 1-word lines (root cause = bad
   truncation, fix #then blip gone) + 600ms internal dropout on 9-14s LLM lines. FIX:
   tighten off-snap length (shorter Ultron) + lower the internal-pause cap / trim >550ms
   dead-air; investigate the 1-word truncation ("Dig.","Corner.","Own A.").
8. **Metric hardening**: canonicalize 'way lay'->waylay (+ other 2-word agent STT) in the
   scorecard fact extractor (false-positive hallucinations).

## Order: 1,2,3 (contained, high-value) -> 4a,8 -> 6 -> 4b,5,7 (deeper). Re-run + re-examine each.
