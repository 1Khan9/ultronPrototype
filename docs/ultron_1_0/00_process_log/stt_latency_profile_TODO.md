# STT latency profile — TODO (note left 2026-06-24)

Latency is workable for now; functionality is the priority. This note captures
where the latency work stands so it can be resumed cold.

## What's done
- **TRUE-latency metric is LIVE** (`orchestrator.py`): every relay turn logs
  `RESPONSE LATENCY: SPEECH-END -> first audio = X ms (turn-close -> audio = Y ms;
  pre-turn-close wait = Z ms)`. `_speech_end_t0` is stamped on the last speech
  chunk in both capture loops; the old `turn-close -> audio` metric UNDER-reported
  by hiding `Z` (the silence/early-complete wait before turn-close).
- **The workflow's "spec-drain grace" (finding 6 option 1) is a METRIC ILLUSION**
  — proven by the timing math AND the live metric. The STT->LLM->synth pipeline
  finishes at a fixed wall-clock time after speech-end; deferring turn-close only
  relabels `Y`/`Z`, it does NOT move when the audio plays. Do NOT implement it.

## What the live data shows (2026-06-24, Huihui-3.5-4B on GPU + game)
| turn | SPEECH-END -> audio (TRUE) | turn-close -> audio (old) | hidden | Whisper STT |
|---|---|---|---|---|
| "rotate to B" | 986 ms | 664 ms | 322 ms | 422 ms |
| compound (5-word) | 1427 ms | 1088 ms | 339 ms | 531 ms |
- The **STT (~420-530 ms)** is the single biggest REDUCIBLE chunk; the relay LLM is
  fully overlapped (`line_build=1ms`), synth ~80-115 ms, pre-turn-close wait ~330 ms.

## NEXT (resume here) — run with Ultron STOPPED
1. **Isolated STT benchmark.** Load the STT model alone (nothing else on the GPU)
   and transcribe a fixed ~2 s clip; compare to the in-app 420-530 ms.
   - If isolated ~150 ms ⇒ **GPU contention** ⇒ fix WITHOUT an accuracy hit
     (pin STT to a higher-priority CUDA stream / ensure no concurrent LLM-gen or
     Kokoro synth on the same stream during the STT). Best path.
   - If isolated also ~450 ms ⇒ it's the **model** ⇒ faster-STT A/B
     (distil-large-v3 or small.en) with the agent-name/site mishear trade-off.
2. Secondary: the ~330 ms pre-turn-close wait is the VAD/Smart-Turn endpointing —
   reducible only at the risk of truncating speech; lower priority.

## STT config
`stt.model = deepdml/faster-whisper-large-v3-turbo-ct2`, `beam=1` (config.yaml).
Whisper RTF observed 0.13-0.31 (varies with GPU load → contention suspected).
