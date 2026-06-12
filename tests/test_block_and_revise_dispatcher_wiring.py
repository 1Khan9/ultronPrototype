"""4B optimization plan Item 8 — dispatcher wiring tests.

Verifies that ``OpenClawDispatcher`` runs the block-and-revise
validator before each ``handle_*`` method when the feature is enabled,
short-circuits with the validator's reason when blocked, and falls
through to the existing stub response when allowed / disabled / no
LLM wired.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from kenning.openclaw_routing.dispatcher import OpenClawDispatcher
from kenning.openclaw_routing.intents import (
    BrowserIntent,
    FileOpIntent,
    MediaGenIntent,
    MessagingIntent,
    ShellOpIntent,
)


def _cfg(enabled: bool) -> MagicMock:
    cfg = MagicMock()
    cfg.openclaw.enabled = False
    cfg.openclaw.gateway_url = None
    cfg.openclaw.fail_open = True
    cfg.openclaw.block_and_revise.enabled = enabled
    cfg.routing.stub_responses_enabled = True
    return cfg


def _llm_returning(verdict: str) -> MagicMock:
    """Mock LLM whose ``generate`` returns the given verdict text."""
    llm = MagicMock()
    llm.generate.return_value = verdict
    return llm


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Disabled flag — validator never runs, dispatch hits stub directly
# ---------------------------------------------------------------------------


def test_disabled_flag_skips_validator() -> None:
    llm = _llm_returning("BLOCK\nbad")
    cfg = _cfg(enabled=False)
    d = OpenClawDispatcher(config=cfg, llm=llm)
    intent = BrowserIntent(action="navigate", url="https://x.com", raw_text="open x")
    result = _run(d.handle_browser(intent))
    # Stub voice msg returned (no validator interception)
    assert "gateway isn't connected yet" in result.voice_message
    assert result.metadata.get("stub") is True
    # validator never called
    llm.generate.assert_not_called()


def test_no_llm_skips_validator() -> None:
    """Even when enabled, a None LLM short-circuits — preserves dispatch
    path when llm hasn't been threaded yet."""
    cfg = _cfg(enabled=True)
    d = OpenClawDispatcher(config=cfg, llm=None)
    intent = BrowserIntent(action="navigate", url="https://x.com", raw_text="open x")
    result = _run(d.handle_browser(intent))
    assert "gateway isn't connected yet" in result.voice_message
    assert result.metadata.get("blocked") is not True


# ---------------------------------------------------------------------------
# Enabled + LLM + ALLOW — dispatch proceeds to stub
# ---------------------------------------------------------------------------


def test_validator_allow_dispatches_to_stub() -> None:
    llm = _llm_returning("ALLOW\nlegitimate request")
    cfg = _cfg(enabled=True)
    d = OpenClawDispatcher(config=cfg, llm=llm)
    intent = BrowserIntent(action="navigate", url="https://x.com", raw_text="open x")
    result = _run(d.handle_browser(intent))
    # Stub response (validator allowed → existing dispatch path)
    assert "gateway isn't connected yet" in result.voice_message
    assert result.metadata.get("stub") is True
    assert result.metadata.get("blocked") is not True
    llm.generate.assert_called_once()


# ---------------------------------------------------------------------------
# Enabled + LLM + BLOCK — short-circuit with validator's reason
# ---------------------------------------------------------------------------


def test_validator_block_short_circuits() -> None:
    llm = _llm_returning("BLOCK\nthat URL is unrelated to the user's stated goal")
    cfg = _cfg(enabled=True)
    d = OpenClawDispatcher(config=cfg, llm=llm)
    intent = BrowserIntent(
        action="navigate",
        url="https://random-thing.com",
        raw_text="check the news",
    )
    result = _run(d.handle_browser(intent))
    assert result.success is False
    assert "I held off on that" in result.voice_message
    assert "unrelated to the user's stated goal" in result.voice_message
    assert result.metadata.get("blocked") is True
    assert result.metadata.get("verdict") == "BLOCK"
    assert result.metadata.get("tool_name") == "browser"


# ---------------------------------------------------------------------------
# Validator wired across all five handlers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("intent,handler", [
    (
        MediaGenIntent(medium="image", description="cat painting", raw_text="paint a cat"),
        "handle_media_generation",
    ),
    (
        MessagingIntent(channel="telegram", body="hi", recipient="bob", raw_text="text bob"),
        "handle_messaging",
    ),
    (
        FileOpIntent(operation="read", path="C:/x.txt", raw_text="read x"),
        "handle_file_operation",
    ),
    (
        ShellOpIntent(command="echo hi", raw_text="run echo"),
        "handle_shell_operation",
    ),
])
def test_all_handlers_run_validator_when_enabled(intent, handler) -> None:
    llm = _llm_returning("BLOCK\nbad call")
    cfg = _cfg(enabled=True)
    d = OpenClawDispatcher(config=cfg, llm=llm)
    method = getattr(d, handler)
    result = _run(method(intent))
    assert result.metadata.get("blocked") is True


# ---------------------------------------------------------------------------
# Validator failure falls open
# ---------------------------------------------------------------------------


def test_validator_exception_falls_open() -> None:
    """If the validator path itself raises, dispatch must proceed
    (never hard-block on a flaky validator)."""
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("model crashed")
    cfg = _cfg(enabled=True)
    d = OpenClawDispatcher(config=cfg, llm=llm)
    intent = BrowserIntent(action="navigate", url="https://x.com", raw_text="open x")
    result = _run(d.handle_browser(intent))
    # Stub returned; not blocked
    assert result.metadata.get("blocked") is not True
    assert "gateway isn't connected yet" in result.voice_message


# ---------------------------------------------------------------------------
# Voice controller threading — llm_engine must reach dispatcher
# ---------------------------------------------------------------------------


def test_voice_controller_threads_llm_to_dispatcher(tmp_path) -> None:
    """``CapabilityVoiceController.handle_capability_intent`` must build
    the dispatcher with its ``llm_engine`` so the validator can run."""
    from kenning.coding.voice import CapabilityVoiceController
    from kenning.openclaw_routing.intents import (
        BrowserIntent, RoutingIntent, RoutingIntentKind,
    )

    fake_llm = MagicMock(name="fake_llm_engine")
    ctrl = CapabilityVoiceController(
        runner=MagicMock(),
        registry=MagicMock(),
        resolver=MagicMock(),
        sandbox_root=tmp_path / "sandbox",
        llm_engine=fake_llm,
    )

    # First call constructs the runner + dispatcher and caches it.
    intent = RoutingIntent(
        kind=RoutingIntentKind.BROWSER_AUTOMATION,
        raw_text="open x",
        automation_intent=BrowserIntent(
            action="navigate", url="https://x.com", raw_text="open x",
        ),
    )
    ctrl.handle_capability_intent(intent)
    runner = ctrl._automation_runner  # noqa: SLF001
    dispatcher = runner._dispatcher  # noqa: SLF001
    assert dispatcher._llm is fake_llm  # noqa: SLF001
