"""Tests for the Channel abstraction (Track 6, 2026-05-19)."""

from __future__ import annotations

import pytest

from ultron.channels import Channel, ChannelMetadata


# ---------------------------------------------------------------------------
# Channel enum
# ---------------------------------------------------------------------------


def test_channel_string_values_are_locked():
    """The string values are persisted in Qdrant payloads + observation
    rows. Don't change them without a migration plan."""
    assert Channel.USER.value == "user"
    assert Channel.TEAMMATE.value == "teammate"
    assert Channel.SYSTEM.value == "system"


def test_channel_from_str_known_values():
    assert Channel.from_str("user") == Channel.USER
    assert Channel.from_str("teammate") == Channel.TEAMMATE
    assert Channel.from_str("system") == Channel.SYSTEM


def test_channel_from_str_case_insensitive():
    assert Channel.from_str("USER") == Channel.USER
    assert Channel.from_str("TeamMate") == Channel.TEAMMATE
    assert Channel.from_str("  System  ") == Channel.SYSTEM


def test_channel_from_str_defaults_to_user_on_unknown():
    """Legacy payloads / corrupt data fall back to USER."""
    assert Channel.from_str("nonsense") == Channel.USER
    assert Channel.from_str("") == Channel.USER
    assert Channel.from_str(None) == Channel.USER  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ChannelMetadata
# ---------------------------------------------------------------------------


def test_metadata_default_is_user_channel():
    meta = ChannelMetadata()
    assert meta.channel == Channel.USER
    assert meta.speaker_tag is None
    assert meta.confidence == 1.0


def test_metadata_payload_dict_minimal():
    """Bare user channel emits only required fields."""
    meta = ChannelMetadata()
    payload = meta.as_payload_dict()
    assert payload == {"channel": "user", "channel_confidence": 1.0}


def test_metadata_payload_dict_with_speaker_tag():
    meta = ChannelMetadata(
        channel=Channel.TEAMMATE,
        speaker_tag="Marcus",
        confidence=0.85,
    )
    payload = meta.as_payload_dict()
    assert payload["channel"] == "teammate"
    assert payload["speaker_tag"] == "Marcus"
    assert abs(payload["channel_confidence"] - 0.85) < 1e-6


def test_metadata_payload_dict_omits_empty_speaker_tag():
    meta = ChannelMetadata(channel=Channel.TEAMMATE, speaker_tag=None)
    payload = meta.as_payload_dict()
    assert "speaker_tag" not in payload


def test_metadata_payload_dict_with_extra():
    meta = ChannelMetadata(
        channel=Channel.USER,
        extra={"source_device": "Focusrite"},
    )
    payload = meta.as_payload_dict()
    assert payload["channel_extra"] == {"source_device": "Focusrite"}


def test_metadata_frozen():
    """ChannelMetadata is frozen -- helps the orchestrator pass it
    through layers without worrying about mutation."""
    meta = ChannelMetadata()
    with pytest.raises(Exception):  # FrozenInstanceError
        meta.channel = Channel.TEAMMATE  # type: ignore[misc]
