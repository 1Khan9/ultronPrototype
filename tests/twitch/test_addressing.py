"""Tests for S10a — semantic chat addressing (deterministic-first, FAIL-CLOSED).

Fully OFFLINE: real :class:`ChatEvent` instances (the committed dataclass) + a
deterministic in-memory ``embed_fn`` mock for the residual path. No network, no
creds, no models. Asserts the cost-asymmetric contract: ambiguity / errors / a
bare unaddressed line all fail CLOSED to IGNORE, and resolution is by the
immutable user_id / login so a spoofed display name is ignored.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kenning.twitch.addressing import (
    AddressVerdict,
    ChatAddress,
    classify_chat,
)
from kenning.twitch.clients.eventsub import ChatEvent

# --- canonical identities under test ----------------------------------------- #
BOT_LOGIN = "ultronbot"
BOT_UID = "999000111"
STREAMER_LOGIN = "thestreamer"
STREAMER_UID = "555000222"

# A third, innocent viewer.
OTHER_LOGIN = "randomviewer"
OTHER_UID = "777000333"


def _classify(event: ChatEvent, *, embed_fn=None) -> AddressVerdict:
    return classify_chat(
        event,
        bot_login=BOT_LOGIN,
        bot_user_id=BOT_UID,
        streamer_login=STREAMER_LOGIN,
        streamer_user_id=STREAMER_UID,
        embed_fn=embed_fn,
    )


def _event(text, *, fragments=None, reply_parent_user_id=None,
           chatter_user_id="100", chatter_login="chatterjoe",
           chatter_name="ChatterJoe") -> ChatEvent:
    return ChatEvent(
        broadcaster_user_id=STREAMER_UID,
        chatter_user_id=chatter_user_id,
        chatter_login=chatter_login,
        chatter_name=chatter_name,
        text=text,
        fragments=fragments or [],
        reply_parent_user_id=reply_parent_user_id,
    )


def _mention_fragment(*, user_id, user_login, user_name=None, text=None):
    """A typed Twitch ``mention`` fragment (nested ``mention`` object form)."""
    return {
        "type": "mention",
        "text": text if text is not None else f"@{user_login}",
        "mention": {
            "user_id": user_id,
            "user_login": user_login,
            "user_name": user_name if user_name is not None else user_login,
        },
    }


# --------------------------------------------------------------------------- #
# 1. reply-to-bot -> TO_ULTRON (immutable parent_user_id)
# --------------------------------------------------------------------------- #
def test_reply_to_bot_is_to_ultron():
    ev = _event("yeah but is that true though", reply_parent_user_id=BOT_UID)
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON
    assert v.confidence >= 0.95
    assert "reply" in v.reason


def test_reply_to_someone_else_is_not_to_ultron_via_reply():
    # Reply to another user, no @bot, bare banter -> not TO_ULTRON by the reply rule.
    ev = _event("lol yeah", reply_parent_user_id=OTHER_UID)
    v = _classify(ev)
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 2. @bot -> TO_ULTRON (both by typed fragment user_id and by raw @login)
# --------------------------------------------------------------------------- #
def test_at_bot_fragment_user_id_is_to_ultron():
    frag = _mention_fragment(user_id=BOT_UID, user_login=BOT_LOGIN)
    ev = _event(f"@{BOT_LOGIN} what is the score", fragments=[frag])
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON
    assert "user_id" in v.reason


def test_at_bot_raw_login_only_is_to_ultron():
    # No typed fragments at all — only the raw '@login' in the body. Login is
    # immutable, so this still resolves to the bot.
    ev = _event(f"@{BOT_LOGIN.upper()} you there?")  # case-insensitive
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


# --------------------------------------------------------------------------- #
# 3. @otheruser -> TO_OTHER
# --------------------------------------------------------------------------- #
def test_at_other_user_is_to_other():
    frag = _mention_fragment(user_id=OTHER_UID, user_login=OTHER_LOGIN)
    ev = _event(f"@{OTHER_LOGIN} nice play man", fragments=[frag])
    v = _classify(ev)
    assert v.address == ChatAddress.TO_OTHER


def test_raw_at_other_user_is_to_other():
    ev = _event("@someguy123 you dropped that round")
    v = _classify(ev)
    assert v.address == ChatAddress.TO_OTHER


# --------------------------------------------------------------------------- #
# 4. streamer @ -> TO_STREAMER
# --------------------------------------------------------------------------- #
def test_at_streamer_fragment_is_to_streamer():
    frag = _mention_fragment(user_id=STREAMER_UID, user_login=STREAMER_LOGIN)
    ev = _event(f"@{STREAMER_LOGIN} great stream today", fragments=[frag])
    v = _classify(ev)
    assert v.address == ChatAddress.TO_STREAMER


def test_at_streamer_raw_login_is_to_streamer():
    ev = _event(f"yo @{STREAMER_LOGIN} clutch that round")
    v = _classify(ev)
    assert v.address == ChatAddress.TO_STREAMER


# --------------------------------------------------------------------------- #
# 5. '!command' -> COMMAND  (even when it also @mentions someone)
# --------------------------------------------------------------------------- #
def test_bang_prefix_is_command():
    ev = _event("!points")
    v = _classify(ev)
    assert v.address == ChatAddress.COMMAND
    assert v.confidence >= 0.95


def test_bang_command_wins_over_mention():
    # A '!' command takes precedence over a trailing @bot mention.
    frag = _mention_fragment(user_id=BOT_UID, user_login=BOT_LOGIN)
    ev = _event(f"!gamble 100 @{BOT_LOGIN}", fragments=[frag])
    v = _classify(ev)
    assert v.address == ChatAddress.COMMAND


# --------------------------------------------------------------------------- #
# 6. bare chatter -> IGNORE (fail-closed, no embedder)
# --------------------------------------------------------------------------- #
def test_bare_chatter_ignores_fail_closed():
    ev = _event("that was such a sick flick honestly")
    v = _classify(ev)
    assert v.address == ChatAddress.IGNORE
    assert "fail-closed" in v.reason


def test_empty_text_ignores():
    ev = _event("    ")
    v = _classify(ev)
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 7. leading 'ultron' token -> TO_ULTRON
# --------------------------------------------------------------------------- #
def test_leading_ultron_token_is_to_ultron():
    ev = _event("ultron are you real")
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON
    assert "leading" in v.reason


def test_leading_ultron_variant_is_to_ultron():
    # Common ASR/typo variant chat uses.
    ev = _event("hey altron what do you think")
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


def test_leading_bot_login_token_is_to_ultron():
    # Custom-named bot, leading bare login token (no '@').
    ev = _event(f"{BOT_LOGIN} whats the round count")
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


def test_third_person_ultron_mention_is_not_leading():
    # "ultron is broken" reads as ABOUT the bot, not TO it. No leading-address
    # boost (the regex anchors a name FOLLOWED by address-y content is fine, but a
    # bare third-person statement still leads with 'ultron' -> we accept that as
    # addressed only via the leading rule; assert the mid-sentence case ignores).
    ev = _event("i think the ultron bot is kinda broken lol")
    v = _classify(ev)
    # 'ultron' is mid-sentence, no '@', no leading token -> fail-closed IGNORE.
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 8. spoofed display name is ignored (resolution uses immutable user_id / login)
# --------------------------------------------------------------------------- #
def test_spoofed_display_name_does_not_resolve_to_bot():
    # A troll sets their DISPLAY name to "Ultron" but their login/user_id are
    # their own. An @mention of THEM must be TO_OTHER, never TO_ULTRON.
    frag = _mention_fragment(
        user_id=OTHER_UID, user_login=OTHER_LOGIN, user_name="Ultron",
    )
    ev = _event(
        f"@{OTHER_LOGIN} gg",
        fragments=[frag],
        chatter_name="Ultron",  # spoofed display name on the chatter too
    )
    v = _classify(ev)
    assert v.address == ChatAddress.TO_OTHER


def test_spoofed_chatter_name_does_not_self_address():
    # The CHATTER's display name is "ultron" but the line is bare banter; the
    # spoofable name must not turn this into TO_ULTRON.
    ev = _event("ggs everyone good games", chatter_name="ultron")
    v = _classify(ev)
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 9. residual embed path — both directions (margin honored)
#
#    The residual tier is CLOSED OFF by default since 2026-07-08 (it replied to
#    un-prefaced chat on the live stream) — these tests exercise the MECHANISM
#    behind its flag, so they enable it and restore the default afterwards.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def residual_tier_on():
    from kenning.twitch.addressing import set_residual_addressing_enabled
    set_residual_addressing_enabled(True)
    yield
    set_residual_addressing_enabled(False)


def _direction_embed_fn():
    """A deterministic mock embedder.

    Lines that look like they're addressed to the bot embed near unit vector
    ``[1, 0]``; banter embeds near ``[0, 1]``. The to-Ultron exemplar cloud lands
    near ``[1,0]`` and the not-cloud near ``[0,1]``, so a to-Ultron query gets a
    positive margin and a banter query a negative one — exercising both residual
    branches deterministically with no real model.
    """
    pos_markers = ("you", "your", "answer", "respond", "think", "real",
                   "opinion", "funny", "joke", "watching", "understand", "would")
    neg_markers = ("gg", "lol", "stream", "game", "clutch", "poggers", "same",
                   "lagging", "hello", "insane", "love", "time")

    def embed(text: str):
        t = (text or "").lower()
        pos = sum(t.count(m) for m in pos_markers)
        neg = sum(t.count(m) for m in neg_markers)
        # Bias toward [1,0] when pos-leaning, [0,1] when neg-leaning. Always a
        # nonzero, finite 2-vector.
        x = 1.0 + 2.0 * pos
        y = 1.0 + 2.0 * neg
        norm = math.sqrt(x * x + y * y)
        return [x / norm, y / norm]

    return embed


def test_residual_to_ultron_direction(residual_tier_on):
    ev = _event("do you actually understand what we say and would you respond")
    v = _classify(ev, embed_fn=_direction_embed_fn())
    assert v.address == ChatAddress.TO_ULTRON
    assert "residual" in v.reason


def test_residual_not_to_ultron_direction_ignores(residual_tier_on):
    ev = _event("gg that clutch was insane lol same poggers")
    v = _classify(ev, embed_fn=_direction_embed_fn())
    assert v.address == ChatAddress.IGNORE
    assert "residual" in v.reason


def test_residual_without_embedder_ignores():
    # Same to-Ultron-leaning line, but NO embedder supplied -> fail-closed IGNORE.
    ev = _event("do you actually understand what we say")
    v = _classify(ev, embed_fn=None)
    assert v.address == ChatAddress.IGNORE
    assert "fail-closed" in v.reason


# --------------------------------------------------------------------------- #
# 10. fail-closed robustness — embedder raising / returning garbage
# --------------------------------------------------------------------------- #
def test_residual_embedder_raises_fails_closed(residual_tier_on):
    def boom(_text):
        raise RuntimeError("embedder sidecar down")

    ev = _event("do you understand what we are saying right now")
    v = _classify(ev, embed_fn=boom)
    assert v.address == ChatAddress.IGNORE
    assert "fail-closed" in v.reason


def test_residual_embedder_returns_empty_fails_closed(residual_tier_on):
    ev = _event("would you answer my question please")
    v = _classify(ev, embed_fn=lambda _t: [])
    assert v.address == ChatAddress.IGNORE


def test_residual_embedder_returns_nan_fails_closed(residual_tier_on):
    ev = _event("would you answer my question please")
    v = _classify(ev, embed_fn=lambda _t: [float("nan"), 1.0])
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 10b. residual with a NUMPY ndarray embed_fn — the PRODUCTION shape
#      (regression for the 2026-06-28 live break: the orchestrator injects
#      ``embed_fn = lambda t: (_eb.embed([t]) or [None])[0]`` which returns a
#      numpy ndarray of np.float32. ``if not vec`` raised "truth value of an
#      array is ambiguous" -> classify_chat failed CLOSED to IGNORE on EVERY
#      chat message, 343x/session. The Python-list mocks above never caught it.)
# --------------------------------------------------------------------------- #
def _numpy_direction_embed_fn():
    """``_direction_embed_fn`` but returns a numpy ndarray of ``np.float32`` --
    EXACTLY what the orchestrator's real embed_fn yields per text."""
    base = _direction_embed_fn()

    def embed(text: str):
        return np.asarray(base(text), dtype=np.float32)

    return embed


def test_residual_numpy_embed_fn_to_ultron_does_not_crash(residual_tier_on):
    # A to-Ultron-leaning line with a NUMPY embed_fn must run the residual path
    # (reason mentions 'residual') and resolve TO_ULTRON -- NOT raise the
    # array-truthiness ValueError and fall to the 'classify error' fail-closed.
    ev = _event("do you actually understand what we say and would you respond")
    v = _classify(ev, embed_fn=_numpy_direction_embed_fn())
    assert v.address == ChatAddress.TO_ULTRON
    assert "residual" in v.reason


def test_residual_numpy_embed_fn_banter_ignores_via_residual(residual_tier_on):
    # Banter with a numpy embed_fn must IGNORE through the residual BELOW-MARGIN
    # branch ('residual' in reason), proving the path ran rather than crashed.
    ev = _event("gg that clutch was insane lol same poggers")
    v = _classify(ev, embed_fn=_numpy_direction_embed_fn())
    assert v.address == ChatAddress.IGNORE
    assert "residual" in v.reason


def test_residual_numpy_embed_fn_with_nan_fails_closed(residual_tier_on):
    # A numpy vector carrying a NaN must still fail closed (not crash).
    ev = _event("would you answer my question please")
    v = _classify(ev, embed_fn=lambda _t: np.asarray([float("nan"), 1.0], dtype=np.float32))
    assert v.address == ChatAddress.IGNORE


# --------------------------------------------------------------------------- #
# 11. residual tier DISABLED BY DEFAULT (2026-07-08) — the live-stream misfires
#     (2026-07-07 kenning.log: these un-prefaced lines each drew a public reply
#     through the residual tier the day after the numpy fix revived it). With
#     the tier at its default-OFF, an EXPLICIT signal (reply / @mention /
#     leading name) is required; the guessing tier never engages, even with an
#     embedder that would score maximum to-Ultron similarity.
# --------------------------------------------------------------------------- #
def _always_to_ultron_embed_fn():
    """Worst-case embedder: EVERYTHING lands exactly on the to-Ultron cloud.

    Queries and to-Ultron exemplars embed identically ([1,0]) while the
    not-to-Ultron cloud lands orthogonal ([0,1]) -- so if the residual tier ran,
    every line would clear the floor and margin and commit TO_ULTRON. Proves the
    default-OFF gate blocks even a maximally confident residual."""
    from kenning.twitch.addressing import NOT_TO_ULTRON_EXEMPLARS

    def embed(text: str):
        if text in NOT_TO_ULTRON_EXEMPLARS:
            return [0.0, 1.0]
        return [1.0, 0.0]

    return embed


def test_residual_tier_default_off():
    from kenning.twitch.addressing import residual_addressing_enabled
    assert residual_addressing_enabled() is False


@pytest.mark.parametrize("live_misfire_text", [
    "Sery_Bot is here seryboArrive",
    "idk",
    "either works",
    "or would that be broken",
])
def test_live_misfire_lines_ignore_by_default(live_misfire_text):
    ev = _event(live_misfire_text)
    v = _classify(ev, embed_fn=_always_to_ultron_embed_fn())
    assert v.address == ChatAddress.IGNORE
    assert "residual tier disabled" in v.reason


def test_explicit_signals_still_win_with_tier_off():
    # The deterministic tiers are untouched: leading name, reply-parent, and
    # @mention all still resolve TO_ULTRON with the residual tier off, even
    # with an embedder supplied.
    emb = _always_to_ultron_embed_fn()
    assert _classify(_event("ultron what do you think"), embed_fn=emb).address \
        == ChatAddress.TO_ULTRON
    assert _classify(_event("either works", reply_parent_user_id=BOT_UID),
                     embed_fn=emb).address == ChatAddress.TO_ULTRON
    frag = _mention_fragment(user_id=BOT_UID, user_login=BOT_LOGIN)
    assert _classify(_event(f"@{BOT_LOGIN} idk", fragments=[frag]),
                     embed_fn=emb).address == ChatAddress.TO_ULTRON


def test_residual_tier_setter_round_trip(residual_tier_on):
    # With the tier explicitly enabled, the same misfire line DOES reach the
    # residual path (the fixture restores the OFF default afterwards).
    from kenning.twitch.addressing import residual_addressing_enabled
    assert residual_addressing_enabled() is True
    ev = _event("Sery_Bot is here seryboArrive")
    v = _classify(ev, embed_fn=_always_to_ultron_embed_fn())
    assert v.address == ChatAddress.TO_ULTRON
    assert "residual" in v.reason


# --------------------------------------------------------------------------- #
# precedence + parsing edge cases
# --------------------------------------------------------------------------- #
def test_reply_to_bot_beats_at_other_user():
    # Reply parent is the bot AND the body @mentions another user -> reply wins.
    frag = _mention_fragment(user_id=OTHER_UID, user_login=OTHER_LOGIN)
    ev = _event(f"@{OTHER_LOGIN} yeah", reply_parent_user_id=BOT_UID, fragments=[frag])
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


def test_at_bot_beats_at_other_when_both_mentioned():
    # Body @mentions both the bot and another viewer -> bot resolution wins.
    frags = [
        _mention_fragment(user_id=OTHER_UID, user_login=OTHER_LOGIN),
        _mention_fragment(user_id=BOT_UID, user_login=BOT_LOGIN),
    ]
    ev = _event(f"@{OTHER_LOGIN} and @{BOT_LOGIN} settle this", fragments=frags)
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


def test_from_eventsub_mention_shape_round_trips():
    # Build a real EventSub-shaped payload through ChatEvent.from_eventsub so the
    # fragment-parsing contract is exercised end to end.
    payload = {
        "event": {
            "broadcaster_user_id": STREAMER_UID,
            "chatter_user_id": "100",
            "chatter_user_login": "chatterjoe",
            "chatter_user_name": "ChatterJoe",
            "message_id": "abc-123",
            "message": {
                "text": f"@{BOT_LOGIN} are you watching this",
                "message_type": "text",
                "fragments": [
                    {"type": "text", "text": ""},
                    _mention_fragment(user_id=BOT_UID, user_login=BOT_LOGIN),
                    {"type": "text", "text": " are you watching this"},
                ],
            },
        }
    }
    ev = ChatEvent.from_eventsub(payload)
    assert ev is not None
    v = _classify(ev)
    assert v.address == ChatAddress.TO_ULTRON


def test_garbage_fragments_do_not_crash_fail_closed():
    # Malformed fragments (not dicts / missing keys) must not raise — fail-closed.
    ev = _event(
        "just chatting here",
        fragments=[None, 42, {"type": "mention"}, {"no_type": True}],
    )
    v = _classify(ev)
    assert v.address == ChatAddress.IGNORE


def test_non_chatevent_object_fails_closed():
    # A wholly unexpected object (no .text / .fragments) must IGNORE, never raise.
    class Weird:
        pass

    v = classify_chat(
        Weird(),
        bot_login=BOT_LOGIN,
        bot_user_id=BOT_UID,
        streamer_login=STREAMER_LOGIN,
        streamer_user_id=STREAMER_UID,
    )
    assert v.address == ChatAddress.IGNORE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
