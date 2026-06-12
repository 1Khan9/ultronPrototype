"""Channel abstraction for Kenning's voice pipeline (Track 6, 2026-05-19).

The orchestrator originally assumed one audio capture path (the
hardware mic the user speaks into) and one output path (the user's
headphones). The Valorant content workflow needs a second pair:

* **User channel** -- hardware mic (Focusrite) -> headphones output.
  The existing pipeline. Used for personal interactions; addressing
  classifier decides "did the user just speak to Kenning?".

* **Teammate channel** -- Voicemeeter loopback of game voice ->
  Voicemeeter VAIO that feeds Valorant's mic input. Used when
  teammates address Kenning directly ("yo Kenning, push B"). The
  addressing classifier runs on teammate utterances with a tighter
  confidence gate.

This module ships the data carriers + the channel-aware
configuration. The orchestrator integration that actually wires two
AudioCapture instances + two output stream pre-opens is deferred
because it's a significant architectural change -- the safe path is
to ship the foundations + the addressing-classifier shape that
expects a channel argument, then flip on integration when the user
has the device names ready.

Default channel for every existing call site is :data:`Channel.USER`,
so legacy behaviour is byte-for-byte preserved. The teammate path
only fires when the orchestrator explicitly hands the metadata
through.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class Channel(str, enum.Enum):
    """Which audio channel produced an utterance / consumes a response.

    Members are string-valued so the channel can flow through Qdrant
    payloads, observation rows, and audit logs as a stable label.
    """

    USER = "user"
    """The hardware mic the operator speaks into. Default."""

    TEAMMATE = "teammate"
    """Voicemeeter loopback of game-voice. Teammate utterances enter
    here; Kenning's responses on this channel go OUT through the
    virtual mic feeding Valorant."""

    SYSTEM = "system"
    """Background / scripted / synthetic input that doesn't come from a
    real audio source. Standing-order outputs, scheduled task narration,
    etc. Reserved for future use."""

    @classmethod
    def from_str(cls, value: str) -> "Channel":
        """Coerce a string to a :class:`Channel`. Falls back to
        :data:`Channel.USER` on unrecognised input -- defensive
        against payload data from older sessions that lack the
        ``channel`` field."""
        if not value:
            return cls.USER
        lowered = value.strip().lower()
        for member in cls:
            if member.value == lowered:
                return member
        return cls.USER


@dataclass(frozen=True)
class ChannelMetadata:
    """Per-utterance metadata threaded through the pipeline.

    Carries the channel id plus optional speaker-tag (if a future
    diarization pass distinguishes individual teammates) and a
    confidence score for the channel attribution itself.

    The orchestrator stamps this on every utterance as it leaves the
    audio capture layer; downstream classifiers / memory writes /
    audit logs read it for branching decisions.
    """

    channel: Channel = Channel.USER
    speaker_tag: Optional[str] = None
    confidence: float = 1.0
    extra: dict = field(default_factory=dict)

    def as_payload_dict(self) -> dict:
        """Render as a Qdrant-payload-safe dict.

        Used by :class:`ConversationMemory` so a turn's channel is
        retrievable + filterable. ``None`` speaker_tag is omitted to
        keep payloads compact.
        """
        out: dict = {
            "channel": self.channel.value,
            "channel_confidence": float(self.confidence),
        }
        if self.speaker_tag:
            out["speaker_tag"] = self.speaker_tag
        if self.extra:
            out["channel_extra"] = dict(self.extra)
        return out


__all__ = [
    "Channel",
    "ChannelMetadata",
]
