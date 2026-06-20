"""Tests for the Ultron 1.0 agent-kit reference (src/kenning/audio/agent_kits.py).

Validates roster completeness, the C_domain-verified corrections, the must-inject post-cutoff agents,
and the loader (tolerant lookup, de-dup, cap). Hermetic.
"""
import pytest

from kenning.audio import agent_kits as ak


def test_roster_complete_29_agents():
    assert len(ak.AGENT_KITS) == 29
    # role coverage sanity: every entry starts with a known role
    roles = {v.split(" |")[0] for v in ak.AGENT_KITS.values()}
    assert roles == {"Duelist", "Initiator", "Controller", "Sentinel"}


def test_version_stamped():
    assert ak.KITS_VERSION.startswith("v2026")


@pytest.mark.parametrize("agent,needle", [
    ("Sova", "Recon Bolt"),
    ("Sova", "Hunter's Fury"),
    ("Jett", "Tailwind"),
    ("KAY/O", "ZERO/point"),
])
def test_known_kits(agent, needle):
    fact = ak.agent_kit_fact(agent)
    assert fact is not None and needle in fact


@pytest.mark.parametrize("agent,needle", [
    ("Iso", "suppress"),          # C_domain: Undercut now also suppresses
    ("Clove", "8pts"),            # C_domain: Not Dead Yet = 8 pts (was 6)
    ("Veto", "7pts"),             # C_domain: Evolution = 7 pts (was TBC)
    ("Harbor", "post-rework"),    # 11.10 rework grounded
])
def test_c_domain_corrections_applied(agent, needle):
    assert needle in ak.agent_kit_fact(agent)


@pytest.mark.parametrize("agent", ["Waylay", "Veto", "Miks"])
def test_post_cutoff_agents_grounded(agent):
    fact = ak.agent_kit_fact(agent)
    assert fact is not None and "post-cutoff: ground here" in fact


def test_unknown_agent_returns_none():
    assert ak.agent_kit_fact("Gandalf") is None
    assert ak.agent_kit_fact("") is None
    assert ak.agent_kit_fact(None) is None


def test_tolerant_lookup():
    assert ak.agent_kit_fact("sova") == ak.agent_kit_fact("Sova")
    assert ak.agent_kit_fact("kay/o") == ak.agent_kit_fact("KAY/O")


def test_kit_facts_for_dedup_and_cap():
    facts = ak.kit_facts_for(["Sova", "Sova", "Jett", "Reyna", "Neon", "Omen"], limit=4)
    assert len(facts) == 4           # capped
    assert sum(1 for f in facts if f.startswith("Sova:")) == 1  # de-duped
    assert ak.kit_facts_for([]) == []
    assert ak.kit_facts_for(["Gandalf"]) == []
