"""Tests for pre-synthesis text hygiene (2026-06-11 live incidents)."""

from __future__ import annotations

import numpy as np
import pytest

from ultron.tts.text_hygiene import sanitize_spoken_text


@pytest.mark.parametrize(
    "raw,expected",
    [
        # The live incidents, verbatim shapes.
        ("*repositions window on monitor to show a blank, dark screen*", ""),
        ('"No think.', "No think."),  # quote stripped; words remain
        ('"', ""),
        ("Sure. /no_think", "Sure."),
        ("/no_think", ""),
        # Mixed content keeps the speech, drops the directions.
        ("*nods slowly* Understood.", "Understood."),
        ("Understood. [sighs] Moving on.", "Understood. Moving on."),
        ("Rotate B now. <|im_end|>", "Rotate B now."),
        ("<think>hmm</think>Done.", "Done."),
        # Normal speech is untouched.
        ("The current temperature is 48 degrees.",
         "The current temperature is 48 degrees."),
        ("Clove, smoke window every round.",
         "Clove, smoke window every round."),
        # Punctuation-only / empty.
        ("...", ""),
        ("", ""),
    ],
)
def test_sanitize_spoken_text(raw: str, expected: str) -> None:
    assert sanitize_spoken_text(raw) == expected


def test_kokoro_synthesize_skips_unspeakable_text() -> None:
    """The engine returns a zero clip (no model call) for inputs that
    are entirely stage direction / control tokens."""
    from ultron.tts.kokoro_engine import KokoroSpeech

    engine = KokoroSpeech.__new__(KokoroSpeech)
    engine._sample_rate = 24000
    # _ensure_loaded would raise if reached -- the hygiene gate must
    # short-circuit first.
    engine._ensure_loaded = lambda: (_ for _ in ()).throw(  # type: ignore
        AssertionError("model must not load for unspeakable text"))

    pcm, sr = engine._synthesize("*opens a window and stares*")
    assert sr == 24000
    assert isinstance(pcm, np.ndarray) and pcm.size == 0
