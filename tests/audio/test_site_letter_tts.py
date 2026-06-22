"""Tests for the site-letter TTS pronunciation transform (relay_tts_text).

A callout site letter A/B/C must be spoken as the LETTER (ay/bee/see), not the
word 'a'. The LLM writes site letters UPPERCASE (the article stays lowercase
'a'), so a mid-sentence uppercase A/B/C is a site reference; relay_tts_text
spells it phonetically for Kokoro while the displayed/logged line stays clean.
"""
import pytest

from kenning.audio.relay_speech import relay_tts_text


@pytest.mark.parametrize("line,expected", [
    # the reported case: "A" before "and" was spoken as the article "uh"
    ("rotate to A and plant", "rotate to eigh and plant"),
    ("Look for a pick on B, then rotate to A and plant.",
     "Look for a pick on bee, then rotate to eigh and plant."),
    ("they're on A.", "they're on eigh."),
    ("push B", "push bee"),
    ("plant on C", "plant on see"),
    ("two on A, one rotating B", "two on eigh, one rotating bee"),
    # the existing 'A <location>' rule still fires (A site -> eigh site)
    ("Sova hit 84 on A main", "Sova hit 84 on eigh main"),
    ("A site is open", "eigh site is open"),
    # site letters at clause end / before a sub-location are spoken as letters too
    # (these moved here from test_relay_speech_expansion's "untouched" list, since
    # the old design wrongly assumed Kokoro already said them as letters)
    ("They are A.", "They are eigh."),
    ("They are B long.", "They are bee long."),
    ("Push to A. They never learn.", "Push to eigh. They never learn."),
])
def test_site_letter_spoken_as_letter(line, expected):
    assert relay_tts_text(line) == expected


@pytest.mark.parametrize("line", [
    "look for a pick",          # lowercase article 'a' must NOT change
    "a man can dream",          # article
])
def test_lowercase_article_untouched(line):
    assert relay_tts_text(line) == line


def test_leading_capital_article_not_a_site_letter():
    # A sentence-initial capitalized 'A' before a noun is the article, not a site;
    # only the mid-sentence 'B' (a real site) is converted.
    assert relay_tts_text("A Sage is anchoring B") == "A Sage is anchoring bee"
