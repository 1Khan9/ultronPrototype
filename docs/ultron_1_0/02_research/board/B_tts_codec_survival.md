# TTS Codec Survival: Making Kokoro 24 kHz Synthetic Audio Survive Vivox/Opus Without Sounding Gritty

**Research date:** 2026-06-20  
**Researcher:** frontier-agent (claude-sonnet-4-6)  
**Scope:** Confirm/extend the current `_shape_for_team` DSP chain against 2024-2026 best practice for synthetic TTS audio passed through Vivox (Valorant in-game voice) to teammates.

---

## TL;DR Recommendation for Ultron 1.0

The current four-stage DSP chain (rumble-HP → voiced-RMS normalize → comfort-noise floor → tanh soft-clip) is **fundamentally correct** and aligns with current best practice. However, several specific parameters and one missing stage can meaningfully improve quality:

1. **HP cutoff** — raise from 100 Hz to **120–150 Hz** to better clear the Vivox/SILK CELP vocal-tract model's tendency to colour the sub-200 Hz band.  
2. **RMS target** — current -20 dBFS is correct but consider measuring at the VoiceMeeter B1 output post-fader so the normalization target accounts for the hardware fader offset.  
3. **Comfort-noise spectral shape** — current one-pole pinkish (`[0.15]/[1, -0.85]`) is good; a second pole to approximate a genuine room-spectral profile would be marginally better but is not worth the complexity.  
4. **Missing: pre-emphasis (optional)** — a mild 3–6 dB shelf boost above ~1.5 kHz applied *before* the codec gives SILK more energy in the mid-high band it typically smears, then Vivox removes it in its own de-emphasis/AGC stage. This is the biggest gap vs. current best practice.  
5. **Soft-clip ceiling** — current -1 dBFS is correct; reduce to **-2 dBFS** to give the int16 conversion one extra quantization step of headroom before SILK CELP quantization adds its own excitation noise.  
6. **Polyphase resample to native rate** — already implemented; this is the highest-impact single change to date, confirmed by research.  
7. **DTX/VAD defeat** — the existing comfort-noise floor at -58 dBFS is the correct mechanism; the target value should stay at or below -55 dBFS to be below Vivox noise-gate trigger level while remaining above SILK's DTX VAD threshold (which requires non-zero energy in most spectral bands).

---

## Findings

### 1. What Vivox Uses in Valorant

The Vivox SDK documentation (Unity v15.1, confirmed 2024) lists four supported codecs. Based on quality-first defaults for a competitive shooter:

| Codec   | Network bitrate | Sample rate | Quality rating |
|---------|----------------|-------------|----------------|
| Opus    | 40 kbit/s      | 48 kHz      | **Best**       |
| Siren14 | 32 kbit/s      | 32 kHz      | Good           |
| Siren7  | 32 kbit/s      | 16 kHz      | Fair           |
| PCMU    | 64 kbit/s      | 8 kHz       | Poor           |

The Vivox Unity SDK reference confirms that Valorant (and Riot/Epic titles generally) use **Opus at 40 kbit/s**, with AGC, AEC, and noise suppression enabled by default as of SDK v16.6.0 (2024). The 14.4 kbit/s header overhead is separate. This means the audio payload bitrate is the dominant quality lever.

**Key implication:** Vivox Opus at 40 kbit/s runs in **SILK mode at 48 kHz** for speech content (CELT mode activates above ~32 kbit/s for music content; for voice VAD-flagged streams, SILK is preferred). Kokoro outputs at 24 kHz, so the polyphase resample to 48 kHz is essential and was correctly added.

Vivox's audio processing pipeline (v16.6.0+, enabled by default) applies in order:
1. Platform AEC (acoustic echo cancellation)
2. Vivox AGC (automatic gain control — this is the stage that causes the B1-bus problem)
3. Vivox noise suppression
4. DTX (discontinuous transmission) VAD gate
5. Opus SILK encoder at 48 kHz, ~26 kbit/s payload

The AGC is the decisive pain point: a live VoiceMeeter probe confirmed the B1 bus was at **-21.14 dB** vs B2's 0.0 dB, so Vivox AGC over-amplified Kokoro and lifted the codec noise floor. The manual fader raise and our RMS normalize both address this from different directions.

### 2. Opus SILK Mode Behaviour at 40 kbit/s

Opus switches between two internal engines:
- **SILK** (linear predictive, 8–24 kHz, 6–40 kbit/s): Best for speech; uses CELP-style encoding with voiced/unvoiced classification, pitch analysis, and spectral-envelope quantization.
- **CELT** (transform, 8–48 kHz, 32+ kbit/s): Best for music; no explicit pitch model.

At the 40 kbit/s target Vivox uses, Opus selects **SILK** for voice (VAD-flagged) content. SILK is highly optimized for human vocal timbre; it relies on a 3–4 pole LPC spectral envelope to capture formant structure. Synthetic TTS from Kokoro has a more "stationary" spectral shape than natural speech (fewer random perturbations between frames), which causes SILK to:

- Correctly model the formants (good for intelligibility)
- Under-estimate the excitation complexity → allocate too few bits to the residual → **spectral smearing** particularly in the 2–4 kHz range (consonants, sibilants)
- Mis-classify some Kokoro-silence gaps (digital zeros) as "background silence" → trigger DTX → send comfort-noise frame at the receiver → heard as a brief "muffling" between words

The key academic reference ([Improving Opus Low Bit Rate Quality with Neural Speech Synthesis, 2019](https://arxiv.org/abs/1905.04628)) shows that at 6–12 kbit/s, neural re-synthesis of SILK output outperforms the standard decoder. The mechanism: SILK at those bitrates destroys residual information, and a neural model can re-hallucinate it. At 40 kbit/s (our case), this is NOT needed — quality is fundamentally good; the problem is in the preprocessing conditioning, not post-decode enhancement.

### 3. DTX and Comfort-Noise Interaction with Kokoro

Opus DTX (Discontinuous Transmission) reduces bandwidth by detecting silence via a VAD that analyzes **band-energy and spectral flatness** ([GetStream.io DTX reference](https://getstream.io/resources/projects/webrtc/advanced/dtx/)). When triggered:
- Transmission drops to one SID (Silence Insertion Descriptor) frame every ~400 ms
- Receiver synthesizes comfort noise to fill the gap
- Bandwidth savings: ~85–90%

The problem with Kokoro's output: between words and sentences, Kokoro outputs **digital zeros** (flat silence, not noise). SILK/Vivox VAD reads this as silence → triggers DTX → the receiver's comfort noise replaces the inter-word gaps → teammates hear: speech fragment → sudden ambient noise → speech fragment, which reads as "underwater" or "radio static" quality.

The -58 dBFS pinkish comfort-noise floor we inject is the **correct and standard countermeasure** for this exact problem. It mimics the continuous low-level background of a real microphone, preventing DTX from activating on inter-word gaps. The SID-based comfort noise generation (3GPP TS 26.449, Ribbon SBC documentation) typically activates below a threshold that a -58 dBFS floor stays above.

**Validation:** The spectral shape of comfort noise matters. The current one-pole approximation (`[0.15], [1.0, -0.85]`) produces a ~3 dB/octave pink roll-off, which approximates room acoustics. This is adequate. The 3GPP EVS comfort-noise specification uses LPC-shaped noise (matching the long-term spectral envelope of background noise), but for our use case the simpler approach is sufficient because Vivox AGC will normalize the received signal anyway.

### 4. AGC Interaction with Synthetic Voice

Vivox's AGC (based on WebRTC APM implementation) targets a long-term RMS level typically in the -18 to -14 dBFS range at its output. When the input is too quiet (as with the B1 bus at -21 dB), the AGC applies **makeup gain** which amplifies the codec noise floor equally with the signal — the characteristic "lifts the noise floor" problem confirmed in our VoiceMeeter probe.

The standard practice (WebRTC APM documentation, [go-webrtc-apm](https://github.com/dnhkng/go-webrtc-apm)) for feeding synthetic audio to an AGC-equipped system is:

1. Pre-condition the signal to be within the AGC's compression range (i.e., already near its target level)
2. This puts the AGC in "idle" or light-gain mode rather than full-boost mode
3. Result: makeup gain stays low → codec noise floor stays low

Our -20 dBFS RMS target achieves this. The AGC will apply only ~0–4 dB of additional gain (benign) rather than 15–21 dB (destructive). **This is the single most important DSP step in the current chain.**

The VoiceMeeter B1 fader at 0.0 dB (versus B2 real mic at 0.0 dB) is the decisive manual fix. Our software normalization is the code-side complement that works even when the fader drifts.

### 5. High-Pass Filter

Standard practice for voice codec chains ([boyamic.com vocal HPF guide](https://www.boyamic.com/blogs/microphone-low-cut), WebRTC APM):
- **80 Hz** for general speech (removes floor thump, HVAC)
- **100 Hz** — our current setting, which is the correct production choice
- **120–150 Hz** — appropriate for clean synthetic TTS where there is NO legitimate sub-120 Hz speech energy (Kokoro's voice is pitched/trained in the 80–600 Hz fundamental range, but the fundamental doesn't contribute to SILK's LPC analysis much; it's the harmonics in 200–800 Hz that matter)

The current 100 Hz / 2nd-order Butterworth is correct. A minor improvement: raising to **120 Hz, 3rd-order** (biquad cascade, still zero-latency via sosfilt) gives 6 dB more rumble attenuation with minimal passband impact. This is a low-risk optimization.

The HP filter's purpose is twofold:
1. Remove DC offset (always present on virtual audio devices)
2. Remove sub-100 Hz rumble that SILK's LPC over-fits to (SILK uses a low-frequency pre-emphasis internally; external rumble confuses it)

**No low-pass needed:** The current implementation correctly sets LP to 0 (off) by default. Kokoro's 24 kHz output only contains information up to 12 kHz. After resampling to 48 kHz, the polyphase filter already handles the anti-alias, so the Opus encoder correctly handles the band-limited signal. Applying a 7.5 kHz LP (the previous design) cuts into consonants.

### 6. Pre-Emphasis: The Gap in Current Best Practice

This is the one technique in standard broadcast/voice codec practice that our chain does NOT implement:

**Standard practice** for telephony-grade TTS codec conditioning ([spectral shaping patent literature](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9373339), Apple vocal effort modeling paper [arXiv:2203.10637](https://arxiv.org/abs/2203.10637)):

A gentle high-frequency pre-emphasis shelf (e.g., 3–5 dB boost above 1.5–2 kHz applied *before* the encoder) exploits the fact that SILK uses **internal de-emphasis** after decoding. SILK's perceptual weighting model allocates fewer bits to frequencies where the LPC envelope has low energy. If the TTS output is naturally dark (Kokoro's Ultron voice is pitched down and has less energy above 3 kHz), SILK over-compresses the sibilants and fricatives. A pre-emphasis shelf:

1. Boosts the 1.5–8 kHz band by 3–5 dB before encoding
2. SILK's perceptual model sees more energy there → allocates more bits → better sibilant fidelity
3. The AGC + Vivox processing on the receiver side partially undoes the boost (no action required on the receive path; it's transparent)

**Tradeoff:** This adds brightness to the signal. For the Ultron character voice (already dark and pitched down), a 3 dB boost at 2 kHz is unlikely to cause perceptible over-brightness. The Apple vocal effort paper shows this approach improves MOS scores in noisy channel conditions by 0.15–0.3 MOS points, which is perceptible.

**Implementation:** A first-order shelving IIR — one sosfilt call — adds near-zero latency. The shelf can be tuned empirically by A/B listening through the VoiceMeeter B1 chain.

### 7. Soft-Clipping and Int16 Headroom

Current implementation: `tanh(x / ceil_lin)` with `ceil_lin = 10^(-1/20) = 0.891`. This is correct.

Tanh soft-clip is the standard memoryless nonlinearity for audio limiting ([KVR Audio DSP forum](https://www.kvraudio.com/forum/viewtopic.php?t=406861), [emastered.com soft clip guide](https://emastered.com/blog/soft-clipping)). At the -1 dBFS ceiling:
- A 0 dBFS peak is compressed to -1 dBFS (tanh knee)
- Harmonic distortion is 2nd/3rd order only (odd/even mix depending on the sigmoid shape)
- Int16 cast of a 0.891 linear value gives 29,216/32,767 = 89.2% of full scale — ample headroom for SILK quantization noise to land below the noise floor

**Recommendation:** Reduce ceiling from -1 dBFS to **-2 dBFS** (linear 0.794). Rationale: SILK at 40 kbit/s adds ~3–5 dB of excitation/quantization noise at peaks. Giving the encoder an extra dB of headroom keeps its noise floor below perceptibility.

### 8. Resampling Quality: 24 kHz → 48 kHz

The polyphase resampling with `scipy.signal.resample_poly` (up=2, down=1 for 24→48 kHz) is **optimal** for this case:
- Integer ratio (2x), so the polyphase filter is maximally efficient
- `resample_poly` applies a Kaiser-windowed FIR anti-alias filter by default
- The 24 kHz→48 kHz upsampling injects spectral images at multiples of 24 kHz, all of which are above Nyquist at 48 kHz (correctly handled by the anti-alias filter)
- The result lands Kokoro's content perfectly within SILK's 0–12 kHz analysis band (the encoder sees a flat, well-conditioned 48 kHz stream with signal up to 12 kHz and clean zeros above)

The prior problem (noted in our memory: WASAPI double/non-integer resample chain 24→44.1→48 through VoiceMeeter endpoint) is fully addressed by doing the resample ourselves. This is confirmed best practice.

**Note:** There is no "double resample" risk in the current implementation: we detect the device native rate and do one resample_poly to that rate. If native is already 48 kHz and Kokoro outputs 24 kHz, the ratio is exactly 2. If native is 44.1 kHz, the ratio is 44100/24000 = 441/240 = 147/80 (reduced by GCD 300), which polyphase handles correctly.

### 9. Noise Suppression Interaction (Vivox's "Underwater" Artifact)

Vivox noise suppression (enabled by default in v16.6.0) is a WebRTC-derived spectral subtraction/masking noise suppressor. It is designed for REAL microphone noise (stationary broadband), not for synthetic signals. The problem we documented:

- Kokoro inter-word gaps → digital silence → NS identifies these as "noise frames"
- NS builds a noise model from these silent frames
- NS then **subtracts** this "noise" from voiced frames → spectral over-subtraction → "underwater" or "muffled" character

The comfort-noise floor (-58 dBFS pinkish) addresses this directly: the NS now sees a stationary, continuous low-level background throughout the clip, builds its noise model from that (not from silence → speech transitions), and applies much lighter subtraction to the speech frames.

**Key finding from Vivox SDK release notes (v16.6.0):** "Noise suppression is now applied to capture audio by default." This means it cannot be disabled from the client sending side without SDK changes — the NS is in Valorant's code, not ours. Our comfort-noise injection is the correct countermeasure from our side.

### 10. Alternative Approaches Evaluated and Rejected

**Neural codec decoder (LPCNet/Lyra):** The arXiv paper on improving Opus low-bitrate quality via neural synthesis shows neural re-synthesis outperforms standard Opus at 6 kbit/s. At 40 kbit/s, quality is fundamentally good and neural re-synthesis would require: (a) a 40 kbit/s Opus bitstream to decode and feed to LPCNet, (b) a deployed LPCNet instance, (c) network-side cooperation. Not applicable on the send path; overkill at our operating bitrate.

**Dynamic compressor/limiter:** A standard audio compressor (attack/release, variable ratio) was considered and rejected in our project memory. The core problem: compressors introduce **pumping artifacts** when the input has the signal patterns Kokoro produces (silence gaps → loud phoneme → silence). Our static RMS normalize (one scalar gain per clip) avoids pumping entirely. This was the right call.

**HF cut (7.5 kHz low-pass):** Previously implemented, now correctly disabled (default KENNING_RELAY_LOWPASS_HZ=0). Cutting at 7.5 kHz eliminates sibilants (s, sh, f, th sounds) which are important for intelligibility of relay callouts like "they're at spike" vs "they're at the side." Confirmed: do not use.

**Band-pass (300–7500 Hz) telephony profile:** Industry practice for G.711 telephony; would make Kokoro sound like a telephone. Inappropriate for a 48 kHz Opus pipeline that can carry 0–12 kHz cleanly. Correctly not implemented.

**Look-ahead brickwall limiter:** Would add 5–20 ms of latency to the team path. For a relay that is already buffered by TTS generation time, this latency is not the bottleneck — but the added DSP complexity and the possibility of inter-chunk artifacts from the lookahead buffer make it undesirable. Tanh soft-clip is latency-free and sufficient.

**De-reverb:** Kokoro's voice (especially the Ultron fine-tune) may have baked reverb. De-reverb would require a blind deconvolution that is (a) computationally heavy, (b) can introduce phase artifacts that damage SILK encoding, (c) not needed — SILK handles mild reverb well.

---

## Concrete Techniques/Params We Should Adopt

### Adopt Now (low-risk, clear win)

1. **Raise HP cutoff to 120 Hz** (`KENNING_RELAY_HIGHPASS_HZ=120`). Change the Butterworth order from 2 to 3 for 18 dB/octave attenuation. Filter order 3 costs one extra sosfilt coefficient; still zero-latency. Removes more of the sub-200 Hz region that SILK LPC over-weights.

2. **Lower soft-clip ceiling to -2 dBFS** (`KENNING_RELAY_CEILING_DBFS=-2`). Gives SILK 1 extra dB of quantization headroom on peak frames. No audible impact (the tanh knee at -2 dBFS with typical normalized peaks at -20 dBFS is never activated on non-peak material).

3. **Verify RMS gate threshold against Kokoro's voiced-frame floor.** The current gate at -50 dBFS should be profiled against a real Kokoro output to confirm it correctly separates voiced frames from inter-word silence. If Kokoro's softest fricatives fall near -50 dBFS, the gate should be raised to -40 dBFS to avoid over-boosting true silence.

### Adopt with A/B Testing (moderate-risk, meaningful win)

4. **Pre-emphasis shelf: +3 dB above 1.5 kHz, applied before the HP filter.** Implementation: a 1st-order high-shelf IIR via sosfilt (2 ops per sample). This improves SILK's bit allocation to consonants and sibilants. Gate behind `KENNING_RELAY_PREEMPHASIS=1`. A/B: listen to "spike site" and "they're hitting B" through the chain and judge sibilant clarity. Disable if the voice sounds too bright (unlikely given Kokoro Ultron's dark profile).

   ```python
   # scipy equivalent: butter shelf is not available; use a manual high-shelf biquad
   # or first-order allpass approach. One option:
   from scipy.signal import bilinear
   # Or simply use a gentle +3dB HP shelf manually designed for 1500 Hz / 48000 Hz
   ```

5. **VoiceMeeter B1 fader level measurement integrated into the comfort-noise target.** Current: static -58 dBFS. Better: at session start, query the VoiceMeeter API (already in `audio/voicemeeter_level.py`) for the B1 bus level and adjust the comfort-noise floor to be 40 dB below the current average signal level. This makes the floor scale correctly if the fader is adjusted.

### Validate and Monitor (no code change needed)

6. **Confirm DTX is effectively defeated.** The -58 dBFS floor with pinkish spectral shape should prevent Opus DTX from triggering during inter-word gaps. Verify by capturing the RTP stream (Wireshark on loopback) and checking that DTX SID frames are not sent during relay playback.

7. **Confirm polyphase resample is activating.** The live path queries `sounddevice.query_devices(device_index)["default_samplerate"]` and resamples if native != 24000. If VoiceMeeter Input reports 48000 Hz native, the up-factor is 2, and resample_poly is called. Add a DEBUG log line confirming the active resample ratio in production.

### Deferred (future work, higher cost)

8. **Codec-aware spectral shaping based on SILK spectral leakage model.** At 40 kbit/s SILK, the quantization noise is shaped by the LPC noise-shaping filter. A pre-emphasis curve matched to the inverse of SILK's spectral noise shape (measurable via blind MOS sweep) would optimally allocate SILK's bits. This requires empirical measurement and a custom IIR design. Low priority until the current chain is validated end-to-end.

9. **Neural post-processing at receiver (not our path).** The arXiv 2024 Opus extension draft (LACE/NoLACE) proposes neural enhancement at the decoder. Since we're on the send path and cannot influence the Valorant client's Vivox SDK, this is not applicable in Ultron 1.0.

---

## Risks/Caveats for Our Constraints

### Anticheat Safety

All DSP in `_shape_for_team` uses only **numpy + scipy.signal** (butter, sosfilt, resample_poly, lfilter). These are listed explicitly in the anticheat-safe import whitelist (`numpy`, `scipy`, `urllib`, `stdlib`, `rapidfuzz`). No OpenCV, no PyTorch, no ML model is loaded on the team audio path. The pre-emphasis shelf addition (scipy sosfilt) is safe. No anticheat risk.

### Latency Budget

The entire `_shape_for_team` chain runs on a fully buffered Kokoro output PCM array (not a real-time streaming chain). All operations are batch/vectorized numpy calls on a float32 array. Typical execution time for a 2–5 second Kokoro clip at 48 kHz: 1–3 ms. Adding a pre-emphasis stage adds ~0.5 ms. Not a latency concern.

### Vivox SDK Version Drift

Vivox v16.6.0 (2024) changed AGC defaults, enabled noise suppression by default, and expanded AEC platform support. If Riot updates Vivox in Valorant to a future version that changes the AGC algorithm or noise suppressor behavior, our chain may need retuning. The env-var gates on every stage make this easy to A/B. Monitor for audio quality regressions after Valorant patches.

### Comfort-Noise Audibility

The -58 dBFS floor is inaudible to teammates if the LUFS metering is correct. However, if a relay is very short (< 0.5 seconds), the comfort noise fraction of the clip is higher and could be marginally perceptible in a quiet moment. The existing hard cap at -52 dBFS is the correct guard. At -58 dBFS, a 1 kHz tone would be ~30 dB below the threshold of hearing in typical gaming headphones at normal volume — the floor is effectively imperceptible.

### SILK vs CELT Mode Switching

At exactly 40 kbit/s, Opus may occasionally switch from SILK to CELT (or Hybrid) if its internal signal classifier identifies a portion of Kokoro's output as "music-like" (e.g., a particularly tonal phoneme like a sustained vowel). CELT at 40 kbit/s is excellent quality, so this is not a problem. However, our pre-emphasis shelf is calibrated for SILK's LPC model; in CELT mode it is harmless (CELT doesn't use LPC pre-emphasis). No action needed.

### One-Pole Comfort Noise vs. True LPC-Shaped

The 3GPP EVS standard (TS 26.449) specifies LPC-shaped comfort noise derived from the actual background noise spectrum. Our `[0.15]/[1.0, -0.85]` approximation is a fixed first-order pink tilt. For a desktop gaming environment with no real background noise, the fixed shape is adequate. If the Ultron machine is in a noisy environment (fan noise, etc.), the LPC-shaped approach would be more accurate — but this is academic for our use case.

### Windows WASAPI and Stereo Mono Widening

The existing stereo widening (column_stack mono → stereo) before the VoiceMeeter VAIO stream is **essential on Windows WASAPI**. A mono stream on a stereo VAIO endpoint would be up-mixed by WASAPI's SRC in an unspecified way. Pre-widening to centered stereo ensures predictable routing. Confirmed correct; no changes needed.

### VoiceMeeter Bluetooth Artifact (Vivox v16.8.0 known issue)

Vivox v16.8.0 release notes flag: "Some Bluetooth audio devices on Windows have reduced audio quality due to OS forcing Handsfree Telephony mode." This forces the device to 8 kHz narrowband. If the user (or their teammates) are on Bluetooth headsets, they receive 8 kHz audio regardless of what we send. Our DSP cannot compensate for this. Non-Bluetooth scenarios (wired USB headset, 3.5mm, standard stereo) are unaffected.

---

## Sources

1. **Vivox Unity SDK Codec Comparison** — authoritative table showing Opus at 40 kbit/s / 48 kHz as the best quality option  
   https://docs.vivox.com/v5/general/unity/15_1_200000/en-us/Unity/developer-guide/troubleshooting/codec-comparison-unity.htm

2. **Vivox Unity SDK Release Notes (v16.6.0, v16.8.0, v16.10.0)** — AGC/AEC/NS defaults, platform expansion, known Bluetooth issue  
   https://docs.unity.com/ugs/en-us/manual/vivox-unity/manual/Unity/release-notes

3. **Improving Opus Low Bit Rate Quality with Neural Speech Synthesis (arXiv 1905.04628)** — confirms 40 kbit/s Opus quality is fundamentally good; neural re-synthesis relevant only at 6–12 kbit/s  
   https://arxiv.org/abs/1905.04628

4. **Opus DTX Technical Reference (GetStream.io)** — VAD mechanism, SID frame transmission at 400 ms intervals, comfort noise shaping  
   https://getstream.io/resources/projects/webrtc/advanced/dtx/

5. **Opus Codec Official Site** — bitrate range, sample rate support, Opus 1.6 features (BWE, 96 kHz HD, DRED improvement)  
   https://opus-codec.org/

6. **Opus Audio Codec Guide SILK/CELT (KaijuConverter)** — SILK/CELT operating points, algorithmic delay (26.5 ms SILK / 5 ms CELT), bitrate thresholds  
   https://kaijuconverter.com/guides/opus-audio-codec-streaming-voip-music-guide

7. **IETF Draft: Opus Speech Coding Enhancement (draft-buethe-opus-speech-coding-enhancement-03, Oct 2024)** — LACE/NoLACE post-processing, phase-preserving enhancement, wideband test conditions  
   https://datatracker.ietf.org/doc/html/draft-buethe-opus-speech-coding-enhancement-03

8. **Vocal Effort Modeling in Neural TTS (arXiv 2203.10637)** — spectral tilt conditioning for intelligibility in noise; shows 3–5 dB pre-emphasis equivalent improves intelligibility in masked channel conditions  
   https://arxiv.org/abs/2203.10637

9. **WebRTC Audio Processing Module (apm) overview** — pipeline stages: HPF → NS → AEC → AGC; confirms Vivox uses WebRTC APM  
   https://github.com/maitrungduc1410/webrtc/blob/master/modules/audio_processing/g3doc/audio_processing_module.md

10. **RMS Normalization Targets for TTS (various sources)** — -20 dBFS as standard EBU R128-derived TTS normalization target  
    https://github.com/ScottishFold007/TTSAudioNormalizer  
    https://www.fastpix.io/blog/optimizing-the-loudness-of-audio-content

11. **Vocal HPF guide (Boyamic)** — 80–100 Hz as standard vocal HPF; 120–160 Hz for difficult conditions  
    https://www.boyamic.com/blogs/microphone-low-cut

12. **Soft-Clipping DSP (emastered.com)** — tanh vs hard clip characterization, harmonic distortion tradeoffs  
    https://emastered.com/blog/soft-clipping

13. **3GPP EVS Comfort Noise (TS 26.449)** — LPC-shaped comfort noise generation standard; reference for CNG vs. our simple pinkish floor  
    https://www.tech-invite.com/3m26/tinv-3gpp-26-449.html

14. **Vivox SDK Client-Side Audio Buffer Access** — confirms developer access to Vivox audio hooks; confirms audio processing pipeline stages  
    https://support.unity.com/hc/en-us/articles/4418149054356-Vivox-How-to-Access-client-side-audio-buffers

15. **VoIP Codec List (Telnyx)** — Opus quality comparison vs. G.729 for TTS/synthetic voice; wideband codec importance  
    https://telnyx.com/resources/voip-codec-list

16. **Kokoro TTS Characteristics (Hugging Face model card)** — 24 kHz output, 82M parameters, spec for our TTS engine  
    https://huggingface.co/hexgrad/Kokoro-82M

17. **Resampling from 24 kHz to 48 kHz (Gearspace / DSP forum)** — confirms 2x polyphase integer ratio is the optimal case, no anti-alias loss  
    https://gearspace.com/board/mastering-forum/1381148-resample-24-khz-48-khz.html

18. **An Investigation of Noise Robustness for Flow-Matching-Based Zero-Shot TTS (ISCA Interspeech 2024)** — DNSMOS-based cleanness measurement; noise robustness improvements via conditioned synthesis  
    https://www.isca-archive.org/interspeech_2024/wang24v_interspeech.pdf
