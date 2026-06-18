"""Flavor-lint gate for the AGENT_FLAVOR library (2026-06-18).

AGENT_FLAVOR is a 1,628-entry hand-curated/audited per-agent contextual library.
``_tail_schema.lint_agent_flavor`` checks its structural + character integrity so
a curation slip (a wrong-gender pronoun, an unknown situation/tag, an empty or
duplicate tail, a paragraph pasted by accident) cannot ship. This is the gate.
"""
from __future__ import annotations

from kenning.audio._agent_flavor import AGENT_FLAVOR
from kenning.audio._tail_schema import (
    AGENT_GENDER,
    GENDER_PRONOUNS,
    TailEntry,
    lint_agent_flavor,
)


def test_agent_flavor_is_clean():
    findings = lint_agent_flavor(AGENT_FLAVOR)
    assert not findings, (
        f"{len(findings)} flavor-lint finding(s):\n  "
        + "\n  ".join(findings[:60])
    )


def test_lint_catches_a_wrong_gender_tail():
    # A synthetic library with a 'she' agent given a 'he' pronoun must be caught.
    bad = {
        "Jett": {  # Jett is "she"
            "spotted": [TailEntry("His dash will not save him.", frozenset())],
        },
    }
    assert AGENT_GENDER["Jett"] == "she"
    findings = lint_agent_flavor(bad)
    assert any("Jett.spotted" in f and "tail uses" in f for f in findings), findings


def test_lint_catches_structural_problems():
    bad = {
        "Sage": {
            "spotted": [
                TailEntry("Good.", frozenset()),
                TailEntry("Good.", frozenset()),          # duplicate
                TailEntry("", frozenset()),               # empty
                TailEntry("x", frozenset({"loc:nowhere"})),  # bad loc class
                TailEntry("y", frozenset({"weird:tag"})),    # bad namespace
            ],
            "not_a_situation": [TailEntry("z", frozenset())],  # unknown situation
        },
        "NotAnAgent": {  # missing gender
            "spotted": [TailEntry("hi", frozenset())],
        },
    }
    findings = lint_agent_flavor(bad)
    joined = "\n".join(findings)
    assert "duplicate tail" in joined
    assert "empty tail" in joined
    assert "unknown loc class" in joined
    assert "unknown tag namespace" in joined
    assert "unknown situation key" in joined
    assert "no AGENT_GENDER entry" in joined


def test_lint_allows_suffixed_and_ability_situations():
    ok = {
        "Raze": {  # Raze is "she"
            "moving (pushing/rushing)": [TailEntry("She rushes. Predictable.", frozenset())],
            "ability_boom_bot": [TailEntry("Her bot, my outline.", frozenset())],
        },
    }
    assert lint_agent_flavor(ok) == []
