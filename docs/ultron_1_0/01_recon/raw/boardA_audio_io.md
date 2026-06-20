# A8: Audio I/O — Capture, TTS, Output Routing, Channels, PTT

## Overview

The audio I/O layer is the outermost ring of the pipeline: raw microphone samples enter at one end and PCM clips exit at several output sinks simultaneously. The stack is layered as follows:

1. **Capture** — `sounddevice.InputStream` → thread-safe queue → `AudioCapture.get_chunk()`
2. **Ring buffer** — shared pre-roll store fed from every chunk; orchestrator slices wake-mode or follow-up-mode pre-roll out of it on demand
3. **VAD** — Silero v5 streaming 512-sample windows → `SPEECH_START` / `SPEECH_END` events with hysteresis
4. **Smart Turn V3** — ONNX classifier run post-SPEECH_END to confirm the utterance is truly complete (reduces silence requirement from ~1200 ms to ~500 ms when the model agrees)
5. **Wake word** — openWakeWord custom ONNX (`kenning.onnx` / `ultron.onnx`); per-word thresholds + consecutive-frame gate; hot-swap at runtime
6. **Whisper STT** — not in this board's scope, but the pipeline feeds it
7. **Kokoro TTS** (`KokoroSpeech`) — StyleTTS2 + ISTFTNet @ 24 kHz, sentence-boundary streamed, producer-consumer pipeline, DSP post-pass
8. **Output routing** — single chokepoint `make_output_stream()` in `devices.py`; four simultaneous sinks: desktop speakers, relay B1 mic (team), OBS broadcast mirror, and user monitor
9. **PTT** — external USB-HID microcontroller, two backends (RawHID preferred, serial fallback); controller drives hold/release/heartbeat lifecycle
10. **Stop** — `_cancel_all_playback()` tears down every output channel instantly; wired to voice command, STOP button overlay, and PTT GUI toggle

---

## Files & Key Symbols

| Path | Role | Key symbols |
|---|---|---|
| `src/kenning/audio/capture.py` | InputStream wrapper | `AudioCapture`, `_callback`, `drain()`, `input_gain_db` |
| `src/kenning/audio/ring_buffer.py` | Pre-roll store | `RingBuffer.snapshot(last_n_samples)` |
| `src/kenning/audio/vad.py` | Silero VAD wrapper | `VoiceActivityDetector`, `SpeechEvent`, `set_min_silence_duration_ms()` |
| `src/kenning/audio/smart_turn.py` | End-of-turn ONNX | `SmartTurnDetector`, `SmartTurnVerdict`, `build_detector_from_config()` |
| `src/kenning/audio/wake_word.py` | openWakeWord wrapper | `WakeWordDetector`, `reload_for_word()`, `fired_recently()` |
| `src/kenning/audio/broadcast.py` | OBS audio tee | `BroadcastSink`, `get_broadcast_sink()`, `cancel_current()`, `configure_from_config()` |
| `src/kenning/audio/monitor.py` | User speaker relay tee | `get_monitor_sink()`, `maybe_submit()`, `cancel_current()` |
| `src/kenning/audio/devices.py` | Device resolution + stream factory | `resolve_device()`, `make_output_stream()`, `_prefer_wasapi_index()` |
| `src/kenning/audio/output_quality.py` | Background artifact analyzer | `OutputQualityWatcher`, `analyze_clip()`, `get_output_watcher()` |
| `src/kenning/audio/voicemeeter_level.py` | VoiceMeeter B1/B2 boot guard | `check_relay_bus_level()` |
| `src/kenning/audio/stop_button.py` | Clickable kill overlay | `StopButtonOverlay`, `match_stop_button_command()` |
| `src/kenning/audio/waveform.py` | OBS radial visualizer | `WaveformSink`, `submit()`, `configure_from_config()`, `_RenderState` |
| `src/kenning/channels.py` | Channel abstraction | `Channel` (USER/TEAMMATE/SYSTEM), `ChannelMetadata` |
| `src/kenning/tts/kokoro_engine.py` | Primary TTS engine | `KokoroSpeech`, `speak_stream()`, `_synthesize()`, `_play()`, `set_live_speaker_mute()`, `_broadcast_submit()` |
| `src/kenning/audio/relay_speech.py` (lines 6449–6751) | Relay output + team DSP | `resolve_relay_device()`, `_shape_for_team()`, `play_to_device()` |
| `src/kenning/ptt/backends.py` | HID/serial PTT transport | `RawHidPttBackend`, `SerialHidPttBackend`, `NullPttBackend`, `find_hid_ptt_device()` |
| `src/kenning/ptt/controller.py` | PTT lifecycle | `PttController.hold()`, `PttController.release()`, `build_ptt_controller()` |
| `src/kenning/pipeline/orchestrator.py` (selected sections) | Wires everything | `_cancel_all_playback()`, `_restart_capture_stream()`, `_interrupt_watcher()`, `_capture_utterance()` |
| `config/settings.py` | Legacy shim constants | `SAMPLE_RATE`, `BLOCKSIZE`, `VAD_THRESHOLD`, `PUSH_TO_TALK_ENABLED`, `STOP_COMMAND_ENABLED` |
| `src/kenning/config.py` (AudioConfig) | Pydantic config schema | `AudioConfig.prefer_wasapi_output`, `stop_command_enabled`, `mute_speakers`, `cold_pre_roll_seconds`, `warm_pre_roll_seconds`, `ring_buffer_seconds` |

---

## Control / Data Flow

### Capture path (microphone → VAD → STT)

```
Focusrite mic
  │
  ▼
sd.InputStream (capture.py:109)
  │  callback: _callback() — audio thread
  │  copies chunk, applies input_gain_db (linear mul, hard-clipped ±1)
  │  queue.put_nowait() — drop-oldest if full
  │
  ▼
AudioCapture._queue (maxsize=1024)
  │
  ├──► RingBuffer.write()   ← ring fed from every chunk in wake/follow-up loops
  │
  ├──► WakeWordDetector.process()  (wake_wait loop)
  │       float32 → int16 PCM → openWakeWord model
  │       per-word threshold + consecutive-frame gate
  │       cooldown_seconds between triggers
  │
  ├──► VoiceActivityDetector.process()  (capture_utterance loop)
  │       accumulates → 512-sample Silero windows
  │       emits SPEECH_START / SPEECH_END with hysteresis
  │
  └──► SmartTurnDetector.is_complete()  (post-SPEECH_END)
           WhisperFeatureExtractor → ONNX inference (CPUExecutionProvider)
           returns SmartTurnVerdict or None (undecided)
```

Pre-roll slicing:
- Cold pre-roll (post-wake): `ring.snapshot(last_n_samples=cold_pre_roll_samples)` — default `0.15 s` = 2,400 samples at 16 kHz. Keeps the wake-word tail from contaminating Whisper.
- Warm pre-roll (post-TTS follow-up): `ring.snapshot(last_n_samples=warm_pre_roll_samples)` — default `0.5 s` = 8,000 samples.
- Pre-roll chunk (chunks[0]) is also fed into `vad.process()` before the live loop begins (orchestrator.py, `_capture_utterance`) so VAD latches `speech_seen` on the pre-recorded tail even if the user started speaking during the wake-word recognition window.

Capture stall watchdog (orchestrator.py:222–224 + 7004–7024):
- `_CAPTURE_STALL_TIMEOUTS = 2`, `_CAPTURE_STALL_SECONDS = 1.0`
- After ~2 successive `None` returns from `get_chunk(timeout=~0.5s)` the orchestrator calls `_restart_capture_stream()`: stops + starts the InputStream, drains the queue.
- Fires in `_wait_for_wake_word`, `_capture_utterance`, and `_follow_up_listen`.

### TTS synthesis path (text → PCM)

```
LLM token fragments
  │
  ▼
KokoroSpeech.speak_stream(fragments)  [or .speak(text) for one-shot]
  │
  ├── synth worker thread: _run_synth_loop()
  │     - accumulates tokens, finds safe sentence boundaries
  │     - per-sentence: _synthesize(sentence)
  │         1. sanitize_spoken_text() — strip stage directions / control tokens
  │         2. ack-cache hit? → return pre-rendered clip (~5 ms)
  │         3. _ensure_loaded() → KPipeline lazy-load
  │         4. KPipeline(text, voice, speed) → per-sentence audio tensors
  │         5. trim_and_fade() each chunk (BLIP fix — strips per-sentence boundary noise)
  │         6. concatenate with KENNING_TTS_SENTENCE_PAUSE_MS gap (default 320 ms)
  │         7. spectral_smooth() — STFT median-filter for pitch wobble
  │         8. trim_and_fade() outer clip
  │         9. apply_runtime_filter() (optional, pre-fine-tune; default OFF)
  │        10. int16 clamp
  │        11. max_pause_cap_ms trim (optional)
  │        12. diagnostics: analyze_clip() raw vs DSP (when audio_diagnostics ON)
  │         → returns (int16 PCM, 24000)
  │
  ├── playback thread (main thread under _playback_lock)
  │     - _consume_preopened_stream() OR _open_output_stream()
  │     - for each ClipItem:
  │         _broadcast_submit(item.audio, sr)   ← tees to OBS broadcast + waveform
  │         _stereo_pcm() mono→stereo
  │         if _speakers_muted(): zero the stereo array
  │         stream.write() in 50ms blocks (stop_event check each block)
```

`prepare_output_stream()` (called by orchestrator during STT on a daemon thread):
- Pre-opens `sd.OutputStream(sr=24000, channels=2, dtype="int16")` + writes 50 ms silence to wake the WASAPI device clock.

### Output routing — all sinks

```
KokoroSpeech playback
  │
  ├─ make_output_stream(output_device, 24000, 2, "int16")
  │     1. WASAPI + prefer_wasapi_output → latency='low' + WasapiSettings(auto_convert=True)
  │     2. fallback: latency='low' generic
  │     3. fallback: plain OutputStream
  │   → DESKTOP SPEAKERS (the user's headphones / A1 bus)
  │     • if _speakers_muted() → zeros written (stream clock intact, no click)
  │
  ├─ broadcast.submit(pcm, sr)   → BroadcastSink daemon thread
  │     → OBS BROADCAST DEVICE (e.g. "Voicemeeter AUX Input" / B3 bus)
  │       always fed regardless of speaker mute
  │
  └─ waveform.submit(pcm, sr)   → WaveformSink pacer thread
        → OBS WAVEFORM OVERLAY (window capture — visual only, no audio device)

relay_speech.play_to_device(pcm, sr, relay_device_index, cancel_event=_relay_interrupt)
  │
  ├─ polyphase resample to device native rate (scipy.signal.resample_poly)
  ├─ _shape_for_team(f, out_rate)   [team DSP chain, see below]
  ├─ int16 clamp + mono→stereo
  └─ make_output_stream(relay_device_index, out_rate, 2, "int16")
       → RELAY MIC BUS (e.g. "Voicemeeter Input" / B1 bus → Valorant)
         • chunked write with cancel_event check every chunk_ms=100ms

monitor.maybe_submit(pcm, sr)   [called from relay path, gated by echo_to_user]
  └─ BroadcastSink(name="monitor") → USER'S DEFAULT OUTPUT DEVICE
       • skipped if audio.mute_speakers OR relay_speech.echo_to_user=False
```

### Team-relay DSP chain (_shape_for_team, relay_speech.py:6600)

Only applied to the Valorant mic path. All stages independently env-gated, fail-open:

1. `_team_bandshape()` — `butter(2, 100 Hz, highpass)` + optional LP (default OFF) — strips DC/rumble; gated by `KENNING_RELAY_COMMS_FILTER` (default ON)
2. `_team_normalize()` — voiced-frame RMS normalize to `KENNING_RELAY_TARGET_DBFS` (default -20 dBFS), clamped ±12 dB — gated by `KENNING_RELAY_NORMALIZE` (default ON)
3. `_team_comfort_noise()` — adds pinkish noise at `KENNING_RELAY_NOISE_DBFS` (default -58 dBFS, hard-capped -52 dBFS) so Vivox noise-suppressor has a stationary reference — gated by `KENNING_RELAY_COMFORT_NOISE` (default ON)
4. `_team_softclip()` — tanh soft-clip ceiling at `KENNING_RELAY_CEILING_DBFS` (default -1 dBFS) — gated by `KENNING_RELAY_SOFTCLIP` (default ON)

Whole chain gated by `KENNING_RELAY_TEAM_DSP` (default ON).

### PTT lifecycle

```
PttController.hold()              ← called by relay handler before clip play
  │  _state=IDLE → sends CMD_DOWN (b"D") to microcontroller
  │  starts driver thread
  │  sleeps lead_ms (default 120 ms) so game transmit opens before audio
  │
  ├─ driver thread loop:
  │    HOLDING: sends CMD_HEARTBEAT every heartbeat_ms (default 50 ms)
  │             max_hold_seconds watchdog (default 8.0 s) force-releases
  │    RELEASING: waits release_at = now + release_tail_ms + jitter
  │               sends CMD_UP (b"U") then IDLE
  │
PttController.release()           ← called after clip drains
  schedules release: release_tail_ms + random jitter (0..release_jitter_ms=60 ms)
  a new hold() before the tail cancels the scheduled release → keeps key down

Backends:
  RawHidPttBackend (preferred): hidapi HID OUTPUT reports to VID=0x1209 usage_page=0xFFC0
  SerialHidPttBackend (legacy): pyserial serial.write() to Arduino COM port VID=0x2341
  NullPttBackend: when PTT disabled or no device detected
```

PTT runtime toggle: the STOP button overlay's PTT button calls `on_toggle_ptt(bool)` → orchestrator's `_ptt_runtime_enabled` flag. When OFF, relay still plays to B1 but no HID command is sent.

### All-channel stop (_cancel_all_playback, orchestrator.py:10583)

Fired by:
- Voice command "Ultron, stop" (via `_interrupt_watcher` which runs during TTS playback when `BARGE_IN_ENABLED` or `STOP_COMMAND_ENABLED`)
- STOP button click → `StopButtonOverlay._fire()` → `on_stop` callback

Actions (all best-effort/fail-open):
1. `self.tts.stop()` — sets `KokoroSpeech._stop_event`, calls `sd.stop()`, closes pre-opened stream
2. `self.llm.cancel()` — aborts any in-flight LLM generation
3. `self._relay_interrupt.set()` — `play_to_device`'s chunked write sees this and exits early
4. `broadcast.cancel_current()` — drains OBS mirror queue, sets `_cancel` event (broadcast daemon stops at next 50ms block)
5. `monitor.cancel_current()` — same for user speaker monitor

### Wake-word-only utterance pruning

After wake fires, if the full transcript matches `_WAKE_REMNANT_RE` (bare "Ultron"/"Kenning" with no command), orchestrator logs `routing:wake_word_only` and returns to wake-wait without dispatching — prevents a bare wake from being treated as a command (orchestrator.py around line 6651).

### STOP button overlay (stop_button.py)

- In-process `tkinter` window, daemon thread
- Borderless, always-on-top, black background; draggable drag bar
- Optional PTT row (green "PTT ON" / grey "PTT OFF")
- Right-click anywhere hides it; voice "show/hide the stop button" opens/closes via `match_stop_button_command()`
- Button command calls `on_stop()` directly (same thread as Tk UI loop)
- Window is built fresh on each `show()` call (overrideredirect windows don't withdraw reliably on Windows)

### Waveform / Broadcast sinks — shared BroadcastSink pattern

Both `BroadcastSink` (broadcast.py) and the monitor sink (monitor.py) share the same daemon-thread pattern:
- `submit()` is a no-op fast-path when device is None (one attribute read)
- PCM is copied to int16 and dropped on a bounded queue (maxsize=16)
- Consumer thread calls `_ensure_stream()` → `make_output_stream()` on first use / device change
- Mono PCM is widened to stereo (centered) for VoiceMeeter virtual input strips
- Writes in 50ms blocks; checks `_cancel` flag and `_device_spec` between blocks
- `cancel_current()` sets `_cancel` event + drains queue; next `submit()` clears it

---

## Key Findings

1. **`make_output_stream()` is the single latency chokepoint** for all four output sinks (speakers, OBS broadcast, relay B1, user monitor). It prefers WASAPI low-latency + `auto_convert=True` (handles Kokoro's 24 kHz on 48 kHz endpoints without PortAudio resampling artifacts) over MME/DirectSound. All callers funnel through it.

2. **The relay team path is the only path with DSP post-processing** (`_shape_for_team()`). Desktop speakers and OBS broadcast receive pristine Kokoro output. The team path additionally runs a polyphase resample to the native device rate before opening the stream — this avoids the double-SRC artifact when Voicemeeter Input resolves to a 44.1 kHz WASAPI endpoint.

3. **Speaker mute is a zero-latency tri-state** (`_live_speaker_mute` in kokoro_engine.py:59). The GUI writes a Python global (atomic under CPython GIL); the playback thread reads it each clip. Silencing writes zeros instead of skipping writes (stream clock intact, no underrun click). OBS broadcast/waveform are always fed regardless of mute.

4. **PTT is strictly external hardware** — no in-process input injection, no SendInput. The host writes a single byte to a USB HID OUTPUT report (device I/O, not system input). NullPttBackend is the default; any open failure leaves PTT inert rather than falling back to software input.

5. **The capture stall watchdog** (`_restart_capture_stream`) handles the "Ultron went deaf" symptom: after a heavy CPU turn (LLM/Whisper), PortAudio can stop delivering callbacks. After ~1–2 stall cycles the orchestrator restarts the InputStream. Fired in three code paths: wake-wait, capture-utterance, follow-up-listen.

6. **The channel abstraction (`channels.py`) is a data stub** — `Channel.USER` / `TEAMMATE` / `SYSTEM` and `ChannelMetadata` exist but the TEAMMATE channel is not yet wired to a second `AudioCapture` instance. The wiring is deferred (comment in channels.py:23). All existing call sites default to `Channel.USER`.

7. **Smart Turn V3** reduces VAD silence requirement from legacy ~1200 ms to ~500 ms for clean utterances. Model is 8M params (Whisper Tiny encoder + linear head), int8 ONNX, ~12 ms inference. Fail-open at every layer: missing model → legacy VAD; inference error → None verdict → trust VAD.

8. **Pre-roll is sliced from a shared RingBuffer** (capacity = `ring_buffer_seconds = 0.5 s`). Cold pre-roll (default 0.15 s) was deliberately kept short to avoid wake-word tail contamination. Warm pre-roll (default 0.5 s) must be at least as large as the detection latency so leading words aren't clipped.

9. **Kokoro synthesis pipeline** has multiple optional DSP passes in order: per-chunk `trim_and_fade()` (BLIP fix at sentence boundaries) → spectral smoothing → outer `trim_and_fade()` → optional runtime Pedalboard filter → int16 clamp → optional pause cap. All fail-open: a DSP failure passes the raw audio through.

10. **The BroadcastSink (OBS)** is the only sink that is always active (when configured) for BOTH conversational and relay output. The waveform overlay (`waveform.py`) is similarly universal. The monitor sink only covers the relay path (normal conversation already hits desktop speakers through the Kokoro speaker path).

11. **`audio.stop_command_enabled: true` (default)** decouples "Ultron, stop" from `barge_in_enabled`. On this production box, barge-in is held OFF (self-trigger on monitor loopback), but stop-command runs the interrupt watcher independently.

---

## Flags & Config

### config.yaml / AudioConfig keys

| Key | Default | Effect |
|---|---|---|
| `audio.sample_rate` | 16000 | Capture + VAD sample rate |
| `audio.channels` | 1 | Mono capture |
| `audio.blocksize` | 256 | PortAudio callback blocksize (16 ms at 16 kHz); VAD internally batches to 512 |
| `audio.input_device` | null | Input device name substring or PortAudio index; env `KENNING_AUDIO_DEVICE` |
| `audio.output_device` | null | Default speaker output; env `KENNING_AUDIO_OUTPUT_DEVICE` |
| `audio.broadcast_device` | "Voicemeeter AUX Input" | OBS audio mirror; env `KENNING_AUDIO_BROADCAST_DEVICE` |
| `audio.prefer_wasapi_output` | true | Prefer WASAPI low-latency for all output streams |
| `audio.mute_speakers` | false | Silence desktop speaker path; OBS + relay unaffected |
| `audio.barge_in_enabled` | true | Let wake-word interrupt TTS (held OFF on this box due to loopback) |
| `audio.stop_command_enabled` | true | Run interrupt watcher for "Ultron, stop" independent of barge-in |
| `audio.barge_in_grace_seconds` | 0.5 | Suppress interrupt watcher for this long after TTS starts |
| `audio.ring_buffer_seconds` | 0.5 | Total ring buffer capacity |
| `audio.cold_pre_roll_seconds` | 0.15 | Pre-roll slice from ring after wake-word fires |
| `audio.warm_pre_roll_seconds` | 0.5 | Pre-roll slice from ring in follow-up-listen mode |
| `audio.input_gain_db` | 0.0 | Linear pre-amp applied in audio callback (range -20..+40 dB) |
| `relay_speech.output_device` | "Voicemeeter Input" | B1 bus for Valorant team chat |
| `relay_speech.echo_to_user` | true | Also play relay clips on the user's desktop speakers (monitor sink) |
| `push_to_talk.enabled` | false | Master PTT switch; env `KENNING_PTT_ENABLED` |
| `push_to_talk.serial_port` | "auto" | COM port for legacy serial backend; env `KENNING_PTT_SERIAL_PORT` |
| `push_to_talk.backend` | "auto" | `"auto"` / `"rawhid"` / `"serial"` |
| `push_to_talk.heartbeat_ms` | 50 | Firmware keep-alive interval |
| `push_to_talk.release_tail_ms` | 150 | Post-clip key hold before releasing |
| `push_to_talk.lead_ms` | 120 | Pre-clip key hold to open game transmit channel |
| `push_to_talk.release_jitter_ms` | 60 | Random extra on release tail (anti-fingerprint) |
| `push_to_talk.max_hold_seconds` | 8.0 | Hardware watchdog force-release timeout |
| `vad.threshold` | (from yaml) | Silero speech probability gate |
| `vad.min_speech_duration_ms` | (from yaml) | Sustained speech to declare SPEECH_START |
| `vad.min_silence_duration_ms` | (from yaml) | Sustained silence to declare SPEECH_END; overridden by smart-turn fast path |
| `vad.smart_turn.enabled` | true | Use Smart Turn V3 ONNX post-VAD |
| `vad.smart_turn.completion_threshold` | 0.5 | Min probability for "complete" verdict |
| `wake_word.name` | "ultron" | Active wake word |
| `wake_word.threshold` | (from yaml) | Default per-word threshold; overridden by `wake_word.thresholds` map |
| `wake_word.min_consecutive_frames` | 1 | Minimum consecutive frames above threshold to fire |
| `wake_word.consecutive_frames` | `{ultron: N, ...}` | Per-word consecutive-frame gate map |
| `visualizer.enabled` | false | Waveform overlay for OBS window capture |
| `tts.output_low_latency_mode` | (from yaml) | Pass `latency='low'` to Kokoro's stream open |
| `tts.speculative_stream_open_enabled` | (from yaml) | Pre-open output stream during STT |

### Environment variables (not in config.yaml)

| Env var | Default | Effect |
|---|---|---|
| `KENNING_RELAY_TEAM_DSP` | "1" | Master toggle for all team-relay DSP stages |
| `KENNING_RELAY_COMMS_FILTER` | "1" | HP/LP bandshape stage |
| `KENNING_RELAY_NORMALIZE` | "1" | RMS normalization stage |
| `KENNING_RELAY_COMFORT_NOISE` | "1" | Comfort noise floor stage |
| `KENNING_RELAY_SOFTCLIP` | "1" | Tanh soft-clip ceiling |
| `KENNING_RELAY_HIGHPASS_HZ` | 100.0 | HP cutoff in _team_bandshape |
| `KENNING_RELAY_LOWPASS_HZ` | 0.0 | LP cutoff (0 = OFF) |
| `KENNING_RELAY_TARGET_DBFS` | -20.0 | RMS normalize target |
| `KENNING_RELAY_NOISE_DBFS` | -58.0 | Comfort noise level (hard-capped -52 dBFS) |
| `KENNING_RELAY_CEILING_DBFS` | -1.0 | Soft-clip ceiling |
| `KENNING_RELAY_VM_LEVEL_GUARD` | "0" | Enable VoiceMeeter B1/B2 boot guard |
| `KENNING_RELAY_VM_RESTORE` | "0" | Auto-set B1 to match B2 (else warn-only) |
| `KENNING_RELAY_VM_B1_INDEX` | 5 | VoiceMeeter B1 bus index |
| `KENNING_RELAY_VM_B2_INDEX` | 6 | VoiceMeeter B2 bus index |
| `KENNING_RELAY_VM_DELTA_DB` | 6.0 | Warn when B2-B1 exceeds this |
| `KENNING_TTS_SENTENCE_PAUSE_MS` | 320 | Gap between sentences in multi-chunk synthesis |
| `KENNING_WAKE_TRIM_TO_SPEECH` | (falsy) | VAD-based wake-word audio strip at capture time |
| `KENNING_STOP_COMMAND_ENABLED` | config | Override audio.stop_command_enabled |
| `KENNING_BARGE_IN_ENABLED` | config | Override audio.barge_in_enabled |
| `KENNING_BARGE_IN_GRACE_SECONDS` | config | Override barge-in grace |
| `KENNING_WAKE_WORD_THRESHOLD` | config | Override wake_word.threshold |
| `KENNING_PTT_ENABLED` | config | Override push_to_talk.enabled |
| `KENNING_PTT_SERIAL_PORT` | config | Override push_to_talk.serial_port |
| `KENNING_AUDIO_DEVICE` | config | Override audio.input_device |
| `KENNING_AUDIO_OUTPUT_DEVICE` | config | Override audio.output_device |
| `KENNING_AUDIO_BROADCAST_DEVICE` | config | Override audio.broadcast_device |
| `KENNING_VOICEMEETER_DLL` | default path | Path to VoicemeeterRemote64.dll |

---

## Extension Points

1. **Adding a new output sink**: implement the `BroadcastSink` pattern (configure, submit, cancel_current, configure_from_config) and call it from `_broadcast_submit()` in kokoro_engine.py + `play_to_device()` in relay_speech.py. The existing OBS broadcast and monitor sinks show the exact plug points.

2. **Adding a new TTS engine**: implement `speak()`, `speak_stream()`, `warmup()`, `prepare_output_stream()`, `stop()`, `set_ack_cache()`. The orchestrator selects by `tts.engine` config key. Kokoro and XTTS are already wired; swapping is config-only.

3. **Always-listening / no-wakeword mode**: `Channel.TEAMMATE` is already scaffolded in channels.py with `AudioConfig` fields for a second `AudioCapture` instance. The wiring to a second capture loop (the teammate channel) is explicitly deferred (channels.py:20–28). The addressing classifier already takes a channel argument.

4. **Extending the team-relay DSP**: add a new stage function to relay_speech.py and call it inside `_shape_for_team()` with its own env-gate. No orchestrator changes needed.

5. **New wake words**: drop an ONNX model file into `models/openwakeword/` and call `wake_detector.reload_for_word(name)`. The `_consec_by_word` and `_thresholds` maps in `wake_word.config` allow per-word tuning without retraining.

6. **Per-word sensitivity tuning**: `wake_word.thresholds` (dict) + `wake_word.consecutive_frames` (dict) in config.yaml — add entries keyed by word name.

7. **Adjusting Smart Turn V3 behavior**: `vad.smart_turn.completion_threshold`, `vad.smart_turn.fast_path_silence_duration_ms`, `vad.smart_turn.incomplete_extension_ms` — no code changes.

8. **VoiceMeeter level auto-restore**: set `KENNING_RELAY_VM_LEVEL_GUARD=1` + `KENNING_RELAY_VM_RESTORE=1` to make the boot guard actively set B1 to match B2.

9. **Kokoro DSP toggles**: `apply_spectral_smooth`, `apply_trim_fade`, `apply_runtime_filter`, prosody hook factors (`f0_contour_factor`, etc.) are constructor args readable from config — u1.0 can expose these as live hot-reload knobs.

---

## Retire-not-Remove Candidates (u1.0)

1. **Deterministic snap dispatch in `relay_speech.py`** — the entire snap-registry (`SNAP_REGISTRY`, `_apply_snap_registry`, hardcoded snap paths like `_THANK_YOU_RE`, `match_flavor_toggle`, etc.) will be replaced by LLM routing with exemplars. The snap functions become prompt-exemplar data. Do NOT delete: they are the source-of-truth corpus for exemplar construction.

2. **`VoiceActivityDetector.set_min_silence_duration_ms()`** — the adaptive end-of-turn policy that bumps the silence requirement for long utterances. Still useful for u1.0 always-listening mode (prevents the detector from firing on mid-thought pauses when the user is giving a long relay). Keep as is.

3. **`Smart Turn V3`** — latency optimization for the post-VAD always-on path. Retain for u1.0 where it becomes even more important (no explicit wake word → every captured utterance goes through STT).

4. **`_shape_for_team()` DSP chain** — still required for Valorant relay quality. No change for u1.0.

5. **`Channel.TEAMMATE`** — the data model is correct and should be wired in u1.0 to the actual second-capture loop. Not a retire candidate; it is a complete-not-remove candidate.

6. **`BroadcastSink` / `WaveformSink` pattern** — the OBS broadcast and waveform overlay remain unchanged. The waveform overlay gets the ULTRON persona nameplate already.

7. **`match_stop_button_command()` in stop_button.py** — this voice-command matcher for show/hide the STOP window is a deterministic snap that should become an LLM routing exemplar in u1.0. Keep the regex as fallback / exemplar.

8. **`OutputQualityWatcher`** — keep as-is; not on hot path; useful for monitoring u1.0 regressions.

---

## Gotchas

1. **Kokoro TTS outputs 24 kHz mono; the relay B1 device (VoiceMeeter Input) may expose a 44.1 or 48 kHz WASAPI endpoint**. `play_to_device()` polyphase resamples before opening the stream. If `sounddevice.query_devices()` fails or returns 0, the code falls back to WASAPI auto-convert. The auto-convert was confirmed to produce audible artifacts through Valorant's codec, so the polyphase path matters.

2. **WASAPI `auto_convert=True` lets 24 kHz audio play on 48 kHz WASAPI endpoints for the speaker/OBS paths** — this is intentional and correct for those sinks. It should NOT be relied on for the team relay path (see above).

3. **VoiceMeeter B1 bus sitting ~21 dB below B2** causes Vivox AGC to over-amplify and lift the codec noise floor. The code-side fix is `_shape_for_team()`; the hardware fix is raising the B1 fader. Both are needed: the code normalizes across relay clips, but the absolute level seen by Vivox is still the bus fader.

4. **`cold_pre_roll_seconds`** must be tuned to the wake-model's typical fire latency. Setting it too high (e.g. 0.35 s as tried during the 2026-06-18 stream rollback) causes the wake tail ("...tron") to contaminate Whisper as phantom prefixes ("Franz", "Prong"). Repo default is 0.15 s.

5. **`Whisper_INITIAL_PROMPT='Kenning.'`** (`.env`) shadows `_DOMAIN_PROMPT` via Python's `or` short-circuit, effectively disabling domain biasing (agent name recognition). The wip branch fixes this; the stream-build and main branch still have the bug. u1.0 should address this explicitly.

6. **`barge_in_enabled`** is held OFF on this production box (VoiceMeeter loopback causes self-triggers). The "Ultron, stop" command is kept working via the separate `stop_command_enabled` flag. The interrupt watcher uses a stricter wake threshold (0.7 / 3 consecutive frames) to reduce loopback false-fires.

7. **PTT `lead_ms = 120 ms`**: the relay handler blocks for 120 ms before writing audio to give the game's transmit channel time to open. This adds 120 ms to relay latency. If PTT is off (`NullPttBackend`), `hold()` is a pure no-op with zero delay.

8. **Capture queue `drop-oldest` policy**: when the audio thread's queue is full (consumer thread busy, e.g. during a CPU-heavy LLM turn), the callback silently drops the oldest block. `drain()` on the consumer side reports the count. This is the root cause of the "capture stall" symptom when combined with the PortAudio host-buffer overrun.

9. **Tkinter overlays (stop_button, waveform)** each run in their own daemon thread with their own `Tk()` root. The Tcl interpreter must be torn down on the thread that created it (`root.destroy()` in `finally`). The code is correct on this point but it's a subtle invariant — any future UI work must maintain it.

10. **`BroadcastSink._write_clip()` only polls `_cancel` between 50ms blocks**. On a long relay clip, cancellation latency is up to 50 ms from the stop command. This is acceptable but worth noting.

11. **Smart Turn V3 is enabled by default** (`vad.smart_turn.enabled: true`) but requires the ONNX model file at the configured `model_path`. If the file is absent, the system silently falls back to legacy VAD-only detection (1200 ms silence default) with a WARN log. u1.0 operators should verify the model is present.

---

## Open Questions

1. **u1.0 always-listening**: when wakeword is optional/off, VAD fires on ALL mic input including Discord chatter, TV audio, and ambient noise. How will the pipeline distinguish (A) talking to Discord/stream, (B) talking to Ultron privately, (C) relaying to team? The `Channel.TEAMMATE` abstraction exists but is unimplemented. The addressing classifier's confidence fusion (`KENNING_ADDRESSING_TAU`, log-odds fuser) was designed for this but is currently behind `addressing.follow_up_enabled=false` due to false-positive issues.

2. **Second capture path for teammate channel**: when the teammate channel is actually wired, will it share the same `AudioCapture` instance (multiplexed) or require a second `sounddevice.InputStream`? VoiceMeeter loopback and the hardware mic may be on different PortAudio devices. The current `AudioCapture` class supports one device per instance.

3. **Kokoro 24 kHz → relay device rate**: the polyphase resample inside `play_to_device()` queries the LIVE device's `default_samplerate`. If VoiceMeeter is not running at boot, the query fails and falls back to WASAPI auto-convert. Is there a startup check for this?

4. **`_WAKE_REMNANT_RE` + `_domain_prompt` interaction**: when u1.0 removes the explicit wake-word requirement, the wake-remnant pruning logic in the orchestrator needs to be rethought — bare "Ultron" spoken without intent would previously fall through to the LLM.

5. **Audio quality watcher (`OutputQualityWatcher`)** is gated by `audio_diagnostics_enabled()` which is typically OFF during live play. If u1.0 increases output verbosity (longer responses), artifact rate should be monitored. Is there a plan to run the watcher in a lightweight always-on mode?

6. **KENNING_TTS_SENTENCE_PAUSE_MS = 320 ms** between Kokoro sentences: for u1.0 high-verbosity mode with longer LLM responses, does this inter-sentence pause feel natural or too long for a conversational AI persona?

7. **`VoiceActivityDetector.set_min_silence_duration_ms()`** adaptive bump for long utterances — in always-on mode this fires more often. What is the right `long_utterance_threshold_seconds` for a user giving a long relay command vs a factual question to Ultron?

8. **Smart Turn V3 model file location**: is `models/smart-turn/smart-turn-v3.*-cpu.onnx` present on the production machine and included in deployment scripts?

9. **`relay_speech.echo_to_user`**: when the user is wearing headphones that are ALSO on the VoiceMeeter chain, does the monitor echo play alongside the team-relay audio (double-play through VoiceMeeter A bus)? The current routing assumes the desktop speakers (A1) and the B1 relay mic are separate paths. If they share an output device, echo creates audible duplication.
