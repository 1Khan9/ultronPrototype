r"""Full-pipeline relay validation with ASR + waveform checks vs the transcript.

For each command: matcher -> build_relay_line (incl. the 3B + the deterministic
repair guardrail) -> Kokoro synth (all trim/blip/smooth/dead-space processes) ->
  * analyze_clip   -> any blip/burst/dropout finding,
  * flow gaps      -> any unnatural internal dead space + trailing tail,
  * Whisper ASR    -> compared to the EXACT line that was generated, to prove
                      the audio faithfully renders the text (nothing clipped).

Calibration: Whisper on the stylized Kenning voice is imperfect, so a single
low score is reviewed by hand against the waveform, not auto-failed. Loads the
3B (gaming) + Kokoro(kenning) + Whisper once.

    python scripts/relay_test/validate_pipeline.py
"""
from __future__ import annotations
import difflib
import re
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))

from kenning.audio.relay_speech import match_relay_command, build_relay_line
from kenning.audio.output_quality import analyze_clip
from harness import _load_llm
from flow_check import env_db, gaps, trailing

FRAME_MS = 10.0

# (command, expected-content hint for manual review)
CASES = [
    # snap callouts (literal)
    "tell my team there is one mid",
    "tell my team they are vents",
    "tell my team sova hit 84",
    "tell my team last is heaven",
    "tell my team to rotate now",
    # ults (multi-name)
    "tell my team their breach has ult",
    "tell my team their fade, breach, and yoru all have ults",
    "tell my team the enemy sova and kayo both have ults",
    # eco / tactics
    "tell my team to play back and not give them guns because they are on eco",
    "tell my team to default and look for guns since we are on eco",
    "tell my team to attack a site as five because the enemy is on eco",
    "tell my team to play off site because their raze has ult",
    # enemy reads
    "tell my team the enemy team is very aggressive and loves to rush",
    "tell my team the enemy yoru will tp back site",
    # self play-style (the repair-framework targets)
    "tell my team I am playing for retake",
    "tell my team I am fighting for main control",
    "tell my team I am playing off site",
    "tell my team I am force buying a gun",
    # banter clapbacks
    "jett is flaming you, respond",
    "sage just called you cringe, respond",
    "breach just told you to shut up, respond",
    # marvel (long, multi-sentence)
    "reyna asked about iron man, respond",
    "my teammate asked about tony stark, respond",
    "sage asked what you think of captain america, respond",
    "my teammate said your movie was terrible, respond",
    # identity
    "my teammate asked if you are an AI, respond",
    "my teammate asked if you are a streamer, respond",
    # greet / farewell (curated)
    "greet my team",
    "say bye to my team, we won",
    "say goodbye to my team, we lost",
    # generic
    "tell my team we are going to crush them",
]


def _norm(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def _present(word: str, pool: set[str]) -> bool:
    """Is ``word`` present in the ASR pool -- exact, substring, or a close
    phonetic/spelling match? Tolerates the ASR's homophone spellings of
    Valorant jargon (Yoru/your, KAY-O/K.O., Raze/raise, ult/alt, eco/echo)
    so only GENUINELY missing words (clipped audio) count against fidelity."""
    for a in pool:
        if word == a or (len(word) >= 4 and (word in a or a in word)):
            return True
        if difflib.SequenceMatcher(a=word, b=a).ratio() >= 0.8:
            return True
    return False


def _union_recall(reference: str, *asr_texts: str) -> float:
    """Fraction of the LLM line's words heard by AT LEAST ONE ASR (fuzzy).

    The LLM line is the reference transcript (what the audio SHOULD say); the
    ASR texts are independent transcripts of what the audio DOES say. A word
    missing from every ASR is real evidence the audio dropped/clipped it."""
    e = _norm(reference)
    if not e:
        return 1.0
    pool: set[str] = set()
    for t in asr_texts:
        pool |= set(_norm(t))
    return sum(1 for w in e if _present(w, pool)) / len(e)


def _char_ratio(reference: str, *asr_texts: str) -> float:
    """Best char-level similarity of the line vs any ASR. A clipped chunk drops
    this sharply; a jargon homophone (Yoru/your) keeps it high -- so it
    separates real audio loss from ASR spelling noise."""
    e = " ".join(_norm(reference))
    best = 0.0
    for t in asr_texts:
        h = " ".join(_norm(t))
        if h:
            best = max(best, difflib.SequenceMatcher(a=e, b=h).ratio())
    return best


def _longest_silence_run_ms(db: "np.ndarray", floor_db: float,
                            frame_ms: float = 10.0) -> float:
    """Longest contiguous run (ms) of frames at/below floor_db = the FLAT
    pure-silence core. Distinguishes real dead space (long flat core) from a
    continuous reverb decay (only a brief dip below the floor)."""
    if db.size == 0:
        return 0.0
    below = db <= floor_db
    best = run = 0
    for b in below:
        run = run + 1 if b else 0
        best = max(best, run)
    return best * frame_ms


def _resample_16k(pcm_i16: np.ndarray, sr: int) -> np.ndarray:
    a = pcm_i16.astype(np.float32) / 32768.0
    if sr == 16000:
        return a
    from scipy.signal import resample_poly
    from math import gcd
    g = gcd(sr, 16000)
    return resample_poly(a, 16000 // g, sr // g).astype(np.float32)


def main() -> int:
    llm = _load_llm()
    from kenning.tts.kokoro_engine import KokoroSpeech
    from kenning.transcription.whisper_engine import WhisperEngine
    tts = KokoroSpeech(voice="kenning"); tts.warmup()
    whisper = WhisperEngine()
    # Second, independent ASR (in-process) -- cross-checks the audio so a
    # single engine's homophone mishear isn't read as a clipped word.
    try:
        from kenning.transcription.moonshine_engine import MoonshineEngine
        moon = MoonshineEngine()
    except Exception as e:                                    # noqa: BLE001
        print(f"[warn] second ASR unavailable: {e}")
        moon = None

    def _asr(eng, pcm16):
        try:
            return eng.transcribe(pcm16) if eng is not None else ""
        except Exception:                                    # noqa: BLE001
            return ""

    recent: list[str] = []
    flags = 0
    for cmd_text in CASES:
        cmd = match_relay_command(cmd_text)
        if cmd is None:
            print(f"\nNONE | {cmd_text!r}"); flags += 1; continue
        line = build_relay_line(cmd, llm=llm, rephrase=True, recent_lines=recent[-6:])
        recent.append(line)
        pcm, sr = tts._synthesize(line)
        pcm = np.asarray(pcm).reshape(-1)
        rep = analyze_clip(pcm, sr, label=line[:50])
        kinds = [f.kind for f in rep.findings]
        d = env_db(pcm, sr)
        ig = gaps(d, -45.0, 150.0)
        tms, _ = trailing(d, -40.0)
        # Real dead space = a FLAT pure-silence core (the compressor's domain),
        # NOT a continuous reverb decay. The compressor caps such cores at
        # ~120 ms, so any contiguous <=-76 dB run > 200 ms is a genuine miss.
        flat = _longest_silence_run_ms(d, -76.0)
        pcm16 = _resample_16k(pcm, sr)
        hw = _asr(whisper, pcm16)
        hm = _asr(moon, pcm16)
        recall = _union_recall(line, hw, hm)               # vs the LLM line
        cratio = _char_ratio(line, hw, hm)

        issues = []
        if any(k in ("trailing_burst", "leading_burst", "hard_tail",
                     "hard_onset", "discontinuity")
               for k in kinds):
            issues.append(f"BLIP:{kinds}")
        if flat > 200:
            issues.append(f"FLAT-DEADSPACE:{flat:.0f}ms")
        # A clipped word is absent from BOTH ASRs (low recall) AND lowers the
        # char-level similarity; a jargon mishear keeps chars similar -> not a clip.
        if recall < 0.85 and cratio < 0.78:
            issues.append(f"MISSING-WORDS recall={recall:.2f} chars={cratio:.2f}")
        if issues:
            flags += 1
        tag = "  !! " + " ".join(issues) if issues else "  ok"
        print(f"\nIN   {cmd_text!r}")
        print(f" SAY  {line!r}")          # transcript 2: what the LLM says it should say
        print(f" AUD  {rep.duration_s:.2f}s tail={tms:.0f}ms flat_silence={flat:.0f}ms "
              f"kinds={kinds or 'none'}")
        print(f" W>   {hw!r}")            # transcript 1a: Whisper of the audio
        print(f" M>   {hm!r}")            # transcript 1b: Moonshine of the audio
        print(f" ==>  audio-vs-LLM: word_recall={recall:.2f} char_sim={cratio:.2f}{tag}")

    print(f"\n==== {len(CASES)} cases, {flags} flagged for review ====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
