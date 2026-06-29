"""Stream-promo relay is CLOSED OFF by default (2026-06-28, user direction).

The ``_PROMO_RE`` self-promo / stream-plug matcher used to turn any passing
mention of the stream ("my stream", "my twitch", "twitch.tv", "follow me on
twitch", ...) into a curated promo shout relayed to the TEAM mic. The streamer
uses exactly that phrasing while talking TO CHAT, so it misfired constantly.

The matcher is now retired-not-removed: gated behind ``KENNING_PROMO_RELAY``
(``promo_relay_enabled()`` / ``set_promo_relay_enabled``), DEFAULT OFF. These
tests pin both the default-closed behaviour and the reversible restore path.
"""
from __future__ import annotations

import pytest

from kenning.audio import relay_speech as rs

# Phrases whose ONLY relay-worthy signal is the stream-plug trigger -- with the
# matcher off these must NOT become a promo (they fall through to normal routing).
_PROMO_TRIGGERS = (
    "go check out my stream",
    "follow me on twitch",
    "check me out at twitch.tv",
    "come watch my stream",
    "subscribe to me",
)


@pytest.fixture(autouse=True)
def _restore_promo_flag():
    """The flag is process-global; snapshot + restore so a test cannot leak it
    into the rest of the suite."""
    prev = rs.promo_relay_enabled()
    try:
        yield
    finally:
        rs.set_promo_relay_enabled(prev)


def _directive(text):
    c = rs.match_relay_command(text)
    return None if c is None else getattr(c, "directive", None)


def test_promo_relay_is_disabled_by_default():
    assert rs.promo_relay_enabled() is False


@pytest.mark.parametrize("text", _PROMO_TRIGGERS)
def test_promo_trigger_does_not_relay_when_closed(text):
    rs.set_promo_relay_enabled(False)
    # No promo command is constructed -- the path is closed.
    assert _directive(text) != "promo"


@pytest.mark.parametrize("text", _PROMO_TRIGGERS)
def test_promo_trigger_relays_when_explicitly_enabled(text):
    # Reversible: restoring the flag brings the curated stream-plug back.
    rs.set_promo_relay_enabled(True)
    assert _directive(text) == "promo"


def test_explicit_team_relay_with_stream_content_relays_literally_not_promo():
    # An explicit "tell my team X" that happens to mention the stream must relay
    # the LITERAL words, never be hijacked into the canned promo (flag OFF).
    rs.set_promo_relay_enabled(False)
    c = rs.match_relay_command("tell my team my stream is poppin")
    assert c is not None
    assert getattr(c, "directive", None) != "promo"
    assert "stream" in (getattr(c, "payload", "") or "").lower()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
