"""Tests for the IT (Interactive Tools) safety category (catalog T11)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kenning.safety.rules.category_it import (
    DEFAULT_BLOCK_MESSAGE,
    DEFAULT_PREFIX_BLOCKLIST,
    DEFAULT_STANDALONE_BLOCKLIST,
    DEFAULT_UNLESS_REGEX,
    IT1InteractivePrefixRule,
    IT2InteractiveStandaloneRule,
    IT3InteractiveUnlessRegexRule,
    InteractiveToolsConfig,
    build_category_it_rules,
    extract_command,
)
from kenning.safety.validator import RuleContext, Verdict


def _ctx(tool_name: str, **arguments) -> RuleContext:
    return RuleContext(
        tool_name=tool_name,
        arguments=arguments,
        capability="shell",
        paths=[],
        user_text="",
    )


# ---------------------------------------------------------------------------
# Constants -- mirror SWE-Agent's ToolFilterConfig
# ---------------------------------------------------------------------------


def test_default_prefix_blocklist_includes_swe_agent_entries():
    for entry in ("vim", "vi", "emacs", "nano", "less", "tail -f", "make", "python -m venv"):
        assert entry in DEFAULT_PREFIX_BLOCKLIST


def test_default_standalone_blocklist_includes_repl_interpreters():
    for entry in ("python", "python3", "ipython", "bash", "sh", "vim", "su"):
        assert entry in DEFAULT_STANDALONE_BLOCKLIST


def test_default_unless_regex_radare2_present():
    assert "radare2" in DEFAULT_UNLESS_REGEX


def test_default_block_message_uses_action_placeholder():
    assert "{action}" in DEFAULT_BLOCK_MESSAGE


# ---------------------------------------------------------------------------
# extract_command heuristics
# ---------------------------------------------------------------------------


def test_extract_from_shell_tool_with_command_arg():
    ctx = _ctx("bash", command="vim foo.txt")
    assert extract_command(ctx) == "vim foo.txt"


def test_extract_from_shell_tool_with_cmd_arg():
    ctx = _ctx("shell", cmd="python script.py")
    assert extract_command(ctx) == "python script.py"


def test_extract_from_shell_tool_with_list_args():
    ctx = _ctx("bash", argv=["python", "-c", "print(1)"])
    cmd = extract_command(ctx)
    assert cmd is not None
    assert "python" in cmd


def test_extract_from_tool_name_when_command_like():
    ctx = _ctx("vim foo.txt")
    assert extract_command(ctx) == "vim foo.txt"


def test_extract_bare_interpreter_name():
    ctx = _ctx("python")
    assert extract_command(ctx) == "python"


def test_extract_returns_none_for_non_shell_tool():
    ctx = _ctx("create_file", path="/tmp/x")
    assert extract_command(ctx) is None


def test_extract_returns_none_for_empty_tool():
    ctx = _ctx("")
    assert extract_command(ctx) is None


# ---------------------------------------------------------------------------
# IT1 InteractivePrefixRule
# ---------------------------------------------------------------------------


@pytest.fixture
def stubs():
    return SimpleNamespace(policy=object(), resolver=object())


def test_it1_blocks_vim_prefix(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="vim foo.txt"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD
    assert "vim foo.txt" in r.context["command"]


def test_it1_blocks_tail_dash_f(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="tail -f /var/log/foo"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it1_blocks_python_m_venv(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="python -m venv .venv"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it1_allows_normal_tail(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    # "tail file" (not "tail -f") is allowed.
    r = rule.evaluate(_ctx("bash", command="tail file.txt"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it1_allows_python_script(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    # "python script.py" doesn't start with "python -m venv" so allowed.
    r = rule.evaluate(_ctx("bash", command="python script.py"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it1_word_boundary_respected(stubs):
    """vim_extension shouldn't match vim prefix."""
    rule = IT1InteractivePrefixRule(
        prefixes=["vim"], message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="vim_extension --help"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it1_no_prefixes_returns_allow(stubs):
    rule = IT1InteractivePrefixRule(prefixes=[], message=DEFAULT_BLOCK_MESSAGE)
    r = rule.evaluate(_ctx("bash", command="vim foo"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it1_non_shell_tool_passes_through(stubs):
    rule = IT1InteractivePrefixRule(
        prefixes=DEFAULT_PREFIX_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("create_file", path="/tmp/x"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


# ---------------------------------------------------------------------------
# IT2 InteractiveStandaloneRule
# ---------------------------------------------------------------------------


def test_it2_blocks_bare_python(stubs):
    rule = IT2InteractiveStandaloneRule(
        names=DEFAULT_STANDALONE_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="python"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it2_allows_python_with_args(stubs):
    rule = IT2InteractiveStandaloneRule(
        names=DEFAULT_STANDALONE_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    # The standalone matcher requires EXACT match -- python script.py is allowed.
    r = rule.evaluate(_ctx("bash", command="python script.py"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it2_blocks_bare_bash(stubs):
    rule = IT2InteractiveStandaloneRule(
        names=DEFAULT_STANDALONE_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="bash"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it2_blocks_bare_su(stubs):
    rule = IT2InteractiveStandaloneRule(
        names=DEFAULT_STANDALONE_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="su"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it2_unknown_command_passes(stubs):
    rule = IT2InteractiveStandaloneRule(
        names=DEFAULT_STANDALONE_BLOCKLIST, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="ls -la"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it2_empty_names_returns_allow(stubs):
    rule = IT2InteractiveStandaloneRule(names=[], message=DEFAULT_BLOCK_MESSAGE)
    r = rule.evaluate(_ctx("bash", command="python"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


# ---------------------------------------------------------------------------
# IT3 InteractiveUnlessRegexRule
# ---------------------------------------------------------------------------


def test_it3_blocks_radare2_without_dash_c(stubs):
    rule = IT3InteractiveUnlessRegexRule(
        name_to_regex=DEFAULT_UNLESS_REGEX, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="radare2 binary.elf"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it3_allows_radare2_with_dash_c(stubs):
    rule = IT3InteractiveUnlessRegexRule(
        name_to_regex=DEFAULT_UNLESS_REGEX, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command='radare2 -c "afl" binary.elf'), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it3_unknown_command_passes(stubs):
    rule = IT3InteractiveUnlessRegexRule(
        name_to_regex=DEFAULT_UNLESS_REGEX, message=DEFAULT_BLOCK_MESSAGE
    )
    r = rule.evaluate(_ctx("bash", command="ls -la"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


def test_it3_invalid_regex_skipped(stubs):
    # Constructor logs WARN; that command is not enforced.
    rule = IT3InteractiveUnlessRegexRule(
        name_to_regex={"validprog": "OK", "bad": "(["},  # bad is unparseable
        message=DEFAULT_BLOCK_MESSAGE,
    )
    # Valid one still works.
    r = rule.evaluate(_ctx("bash", command="validprog noflag"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.BLOCK_HARD


def test_it3_empty_regex_set_returns_allow(stubs):
    rule = IT3InteractiveUnlessRegexRule(name_to_regex={}, message=DEFAULT_BLOCK_MESSAGE)
    r = rule.evaluate(_ctx("bash", command="radare2 something"), policy=stubs.policy, resolver=stubs.resolver)
    assert r.verdict == Verdict.ALLOW


# ---------------------------------------------------------------------------
# build_category_it_rules factory
# ---------------------------------------------------------------------------


def test_factory_returns_three_rules_by_default():
    rules = build_category_it_rules()
    assert len(rules) == 3
    ids = sorted(r.rule_id for r in rules)
    assert ids == ["IT1", "IT2", "IT3"]


def test_factory_with_disabled_config_returns_empty():
    rules = build_category_it_rules(InteractiveToolsConfig(enabled=False))
    assert rules == []


def test_factory_respects_custom_lists():
    cfg = InteractiveToolsConfig(
        prefix_blocklist=["foo"],
        standalone_blocklist=["bar"],
        unless_regex={"baz": r"baz.*"},
    )
    rules = build_category_it_rules(cfg)
    assert len(rules) == 3


# ---------------------------------------------------------------------------
# Rule metadata invariants
# ---------------------------------------------------------------------------


def test_rule_ids_stable():
    rules = build_category_it_rules()
    for r in rules:
        assert r.rule_id.startswith("IT")
        assert r.category == "IT"
        assert r.description
