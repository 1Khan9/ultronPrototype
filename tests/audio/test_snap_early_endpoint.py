"""Tests for the snap-early-endpoint completeness gate (E3).

`relay_speech.is_complete_tactical_callout` is the sidecar-free predicate the
orchestrator's optional ``KENNING_SNAP_EARLY_ENDPOINT`` uses to decide whether a
sub-floor Smart-Turn "complete" verdict can close the capture early. It must be
CONSERVATIVE: a clean slot-callout closes early (safe -- not a fragment), while
anything ambiguous (fragments, bare prefixes, banter, questions) returns False so
the min-speech floor keeps extending (the anti-hallucination guarantee).
"""
from kenning.audio.relay_speech import is_complete_tactical_callout


class TestIsCompleteTacticalCallout:
    def test_complete_slot_callouts_return_true(self):
        # Positions / counts / agent-location -- unambiguous complete callouts.
        for text in (
            "two A main",
            "one back plat",
            "three mid",
            "Reyna is tree",
            "tell my team two A main",   # leading relay lead is stripped (sidecar-free)
            "tell the team one back plat",
        ):
            assert is_complete_tactical_callout(text) is True, text

    def test_fragments_and_bare_prefixes_return_false(self):
        # A single word / bare prefix is NOT a complete callout -> keep extending.
        for text in ("rotate", "Jett", "push", "spike", "one", ""):
            assert is_complete_tactical_callout(text) is False, text

    def test_banter_and_questions_return_false(self):
        for text in (
            "you guys are bad, lock in",
            "what should I do here",
            "are you a robot",
            "nice shot man",
        ):
            assert is_complete_tactical_callout(text) is False, text

    def test_damage_verb_forms_are_conservatively_excluded(self):
        # Damage-verb callouts ("Jett hit 84") don't pass the strict slot grammar,
        # so they conservatively return False -- they still relay normally and pay
        # the floor (no truncation risk), they just don't early-close. This pins
        # the conservative contract so a future broadening is a deliberate change.
        for text in ("Jett hit 84", "Sova hit 84, Breach hit 97", "spike A"):
            assert is_complete_tactical_callout(text) is False, text

    def test_fail_open_on_bad_input(self):
        # Never raises; non-str / None / junk -> False.
        assert is_complete_tactical_callout(None) is False          # type: ignore[arg-type]
        assert is_complete_tactical_callout("   ") is False
