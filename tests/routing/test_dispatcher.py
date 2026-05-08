"""OpenClawDispatcher stub-response tests."""

from __future__ import annotations

import asyncio

import pytest

from ultron.openclaw_routing import (
    OpenClawDispatcher,
    classify_routing,
)
from ultron.openclaw_routing.intents import (
    BrowserIntent,
    DispatchResult,
    FileOpIntent,
    MediaGenIntent,
    MessagingIntent,
    ShellOpIntent,
)


@pytest.fixture
def dispatcher():
    return OpenClawDispatcher()


def _run(coro):
    return asyncio.run(coro)


def test_handle_browser_returns_stub(dispatcher):
    intent = BrowserIntent(action="navigate", url="https://example.com")
    result = _run(dispatcher.handle_browser(intent))
    assert isinstance(result, DispatchResult)
    assert result.success is False
    assert "page" in result.voice_message.lower()
    assert "gateway" in result.voice_message.lower()
    assert result.metadata["stub"] is True
    assert result.metadata["capability"] == "browser_automation"
    assert "not yet integrated" in result.error


def test_handle_media_generation_returns_stub(dispatcher):
    intent = MediaGenIntent(medium="image", description="cat in a top hat")
    result = _run(dispatcher.handle_media_generation(intent))
    assert result.success is False
    assert "generate" in result.voice_message.lower()
    assert result.metadata["stub"] is True
    assert result.metadata["capability"] == "media_generation"


def test_handle_messaging_returns_stub(dispatcher):
    intent = MessagingIntent(channel="telegram", body="build done")
    result = _run(dispatcher.handle_messaging(intent))
    assert result.success is False
    assert "send" in result.voice_message.lower()
    assert result.metadata["stub"] is True
    assert result.metadata["capability"] == "messaging"


def test_handle_file_operation_returns_stub(dispatcher):
    intent = FileOpIntent(operation="read", path="/etc/hosts")
    result = _run(dispatcher.handle_file_operation(intent))
    assert result.success is False
    assert "files" in result.voice_message.lower()
    assert result.metadata["stub"] is True
    assert result.metadata["capability"] == "file_operations"


def test_handle_shell_operation_returns_stub(dispatcher):
    intent = ShellOpIntent(command="dir")
    result = _run(dispatcher.handle_shell_operation(intent))
    assert result.success is False
    assert "shell" in result.voice_message.lower()
    assert result.metadata["stub"] is True
    assert result.metadata["capability"] == "shell_operations"


def test_voice_messages_in_ultron_voice(dispatcher):
    """Spot-check that the stub messages avoid filler and apologetic
    phrasing per Ultron's system prompt rules."""
    bad_phrases = [
        "certainly", "of course", "happy to", "i'm so sorry",
        "i would be happy", "i'd love to",
    ]
    intents = [
        BrowserIntent(action="navigate"),
        MediaGenIntent(medium="image", description=""),
        MessagingIntent(channel="telegram", body=""),
        FileOpIntent(operation="read", path="/x"),
        ShellOpIntent(command="ls"),
    ]
    methods = [
        dispatcher.handle_browser, dispatcher.handle_media_generation,
        dispatcher.handle_messaging, dispatcher.handle_file_operation,
        dispatcher.handle_shell_operation,
    ]
    for fn, intent in zip(methods, intents):
        result = _run(fn(intent))
        msg_lower = result.voice_message.lower()
        for bad in bad_phrases:
            assert bad not in msg_lower, (
                f"voice message has banned phrase {bad!r}: {result.voice_message!r}"
            )


def test_dispatcher_reads_config_at_construction():
    """Dispatcher caches openclaw.enabled and stub_responses_enabled at
    construction time. Tests that change config afterward don't affect
    an already-built dispatcher (which is fine — operator changes config
    and restarts)."""
    d1 = OpenClawDispatcher()
    assert d1.enabled is False  # config default
    assert isinstance(d1.stub_responses_enabled, bool)


# ---------------------------------------------------------------------------
# End-to-end through classify_routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utt,expected_capability", [
    ("open hacker news", "browser_automation"),
    ("make me an image of a cat", "media_generation"),
    ("send a message to my phone", "messaging"),
    ("read the file at C:/x.txt", "file_operations"),
    ("run dir on the desktop", "shell_operations"),
])
def test_classify_then_dispatch_round_trip(dispatcher, utt, expected_capability):
    """Classify an utterance, dispatch the resulting automation_intent,
    expect a stub for the right capability."""
    intent = classify_routing(utt)
    auto = intent.automation_intent
    assert auto is not None, f"automation_intent missing for {utt!r}"

    if isinstance(auto, BrowserIntent):
        result = _run(dispatcher.handle_browser(auto))
    elif isinstance(auto, MediaGenIntent):
        result = _run(dispatcher.handle_media_generation(auto))
    elif isinstance(auto, MessagingIntent):
        result = _run(dispatcher.handle_messaging(auto))
    elif isinstance(auto, FileOpIntent):
        result = _run(dispatcher.handle_file_operation(auto))
    elif isinstance(auto, ShellOpIntent):
        result = _run(dispatcher.handle_shell_operation(auto))
    else:
        pytest.fail(f"unknown automation_intent type: {type(auto).__name__}")

    assert result.success is False
    assert result.metadata["capability"] == expected_capability
