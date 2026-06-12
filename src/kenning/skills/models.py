"""Skill / trigger value types.

Two trigger families:

* :class:`KeywordTrigger` -- the user message contains any of the listed
  keywords as a whole-word, case-insensitive substring. Adopts the
  OpenHands semantic where any of the listed terms is sufficient.
* :class:`TaskTrigger` -- the user message starts with (or contains as a
  standalone token) one of the listed ``/command`` slash commands. Used
  for explicit invocations the user types deliberately.

A :class:`Skill` with no trigger is treated as always-on by the registry,
which the caller can choose to load or skip independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence


class SkillType(str, Enum):
    """Coarse semantic class for a skill.

    Values:
        KNOWLEDGE: domain knowledge to inject when triggered.
        TASK: a procedural / how-to skill that activates on a slash
            command.
        ALWAYS_ON: the skill has no trigger and the registry returns
            it unconditionally.
    """

    KNOWLEDGE = "knowledge"
    TASK = "task"
    ALWAYS_ON = "always_on"


class SkillSource(str, Enum):
    """Where the skill was loaded from.

    Mirrors the OpenHands public / user / project distinction
    (organisation is intentionally skipped -- kenning is single-user).
    Source priority for later-wins dedup: PUBLIC < USER < PROJECT.
    """

    PUBLIC = "public"
    USER = "user"
    PROJECT = "project"
    OTHER = "other"

    @property
    def precedence(self) -> int:
        """Higher precedence wins on duplicate skill names.

        The catalog's later-wins semantic means the project-local
        version of a skill overrides the user version, which overrides
        the public one.
        """

        if self is SkillSource.PUBLIC:
            return 0
        if self is SkillSource.USER:
            return 1
        if self is SkillSource.PROJECT:
            return 2
        return -1


@dataclass(frozen=True)
class KeywordTrigger:
    """Match when the user text contains any of ``keywords`` (case-insensitive).

    A non-zero ``min_user_text_chars`` guards against false fires on
    one-word interjections ("ssh" alone shouldn't load the ssh skill).
    Default is 0 (no guard); callers / loaders typically override per
    skill from the frontmatter.
    """

    keywords: tuple[str, ...]
    min_user_text_chars: int = 0

    def matches(self, user_text: str) -> bool:
        if not user_text or len(user_text) < self.min_user_text_chars:
            return False
        return matches_text(user_text, self.keywords)


@dataclass(frozen=True)
class TaskTrigger:
    """Match when the user text invokes one of the slash ``commands``.

    Commands are stored with their leading ``/`` for clarity. Matching
    requires the command to appear at the start of the text OR after a
    leading natural-language preamble that ends in whitespace ("can you
    /onboard please") -- the latter handles voice-transcription cases
    where the STT engine spelled out a colon or comma before the slash.
    """

    commands: tuple[str, ...]

    def matches(self, user_text: str) -> bool:
        if not user_text:
            return False
        normalized = user_text.lower().strip()
        for command in self.commands:
            cmd = command.lower().strip()
            if not cmd:
                continue
            if not cmd.startswith("/"):
                cmd = "/" + cmd
            # Whole-token match: command appears at start, or as a
            # standalone whitespace-bounded token elsewhere.
            if normalized == cmd:
                return True
            if normalized.startswith(cmd + " ") or normalized.startswith(cmd + ","):
                return True
            # Allow the slash to appear after a preamble. We require the
            # command to be a whole token; ``/order`` shouldn't match
            # ``/o``.
            pattern = r"(?:^|\s)" + re.escape(cmd) + r"(?:$|\s|[,.!?])"
            if re.search(pattern, normalized):
                return True
        return False


Trigger = KeywordTrigger | TaskTrigger


@dataclass(frozen=True)
class Skill:
    """A loaded skill ready to be matched + injected.

    Attributes:
        name: Stable identifier (matches the frontmatter ``name`` or the
            file stem when frontmatter is missing).
        content: The post-frontmatter markdown body. Injected into the
            system prompt when this skill matches.
        trigger: Optional :class:`KeywordTrigger` / :class:`TaskTrigger`.
            ``None`` indicates the skill is always-on.
        source: Where the skill was loaded from (informs dedup).
        type: Semantic class.
        description: Optional human-readable summary surfaced in
            ``kenning diag skills``.
        path: Source file path (informational; not used by matching).
        version: Optional version string from frontmatter.
        extra: Any additional frontmatter keys not consumed above
            (passed through for forward compatibility).
    """

    name: str
    content: str
    trigger: Trigger | None = None
    source: SkillSource = SkillSource.OTHER
    type: SkillType = SkillType.KNOWLEDGE
    description: str | None = None
    path: Path | None = None
    version: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def is_always_on(self) -> bool:
        return self.trigger is None

    def matches(self, user_text: str) -> bool:
        """Return ``True`` iff this skill should fire on ``user_text``.

        Always-on skills return ``True`` unconditionally so the registry
        can include them every turn.
        """

        if self.trigger is None:
            return True
        try:
            return self.trigger.matches(user_text)
        except Exception:
            # Defence: a malformed trigger shouldn't take the whole
            # registry down. The registry's caller also has fail-open
            # protection but pin the contract here too.
            return False


@dataclass(frozen=True)
class SkillMatch:
    """One match returned by :class:`SkillRegistry`.

    Includes the skill and the kind of trigger that fired so consumers
    can introspect ("which keyword woke this skill up?").
    """

    skill: Skill
    matched_terms: tuple[str, ...]

    @property
    def name(self) -> str:
        return self.skill.name

    @property
    def content(self) -> str:
        return self.skill.content


_KEYWORD_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def matches_text(user_text: str, keywords: Sequence[str]) -> bool:
    """Case-insensitive whole-word substring match.

    ``"ssh"`` in ``"please ssh into the box"`` -> True. ``"ssh"`` in
    ``"sshd_config"`` -> False (whole-token match requires word
    boundaries on both sides).

    Empty inputs short-circuit to False. The implementation tokenises
    once via :data:`_KEYWORD_TOKEN_RE` and compares against a lowered
    keyword set.
    """

    if not user_text or not keywords:
        return False
    lower_text = user_text.lower()
    token_set = {tok.lower() for tok in _KEYWORD_TOKEN_RE.findall(lower_text)}
    for keyword in keywords:
        if not keyword:
            continue
        normalized = keyword.lower().strip()
        if not normalized:
            continue
        # Multi-word keywords: substring match against lowered text.
        if " " in normalized:
            if normalized in lower_text:
                return True
            continue
        # Single-word keywords: token-set match for whole-word semantics.
        if normalized in token_set:
            return True
    return False


def find_matched_keywords(user_text: str, keywords: Sequence[str]) -> tuple[str, ...]:
    """Return the subset of ``keywords`` that actually matched.

    Used by :class:`SkillRegistry` to populate :class:`SkillMatch.matched_terms`.
    """

    if not user_text or not keywords:
        return ()
    lower_text = user_text.lower()
    token_set = {tok.lower() for tok in _KEYWORD_TOKEN_RE.findall(lower_text)}
    matched: list[str] = []
    for keyword in keywords:
        if not keyword:
            continue
        normalized = keyword.lower().strip()
        if not normalized:
            continue
        if " " in normalized:
            if normalized in lower_text:
                matched.append(keyword)
            continue
        if normalized in token_set:
            matched.append(keyword)
    return tuple(matched)


def find_matched_commands(user_text: str, commands: Sequence[str]) -> tuple[str, ...]:
    """Return the subset of slash ``commands`` that actually matched."""

    if not user_text or not commands:
        return ()
    normalized = user_text.lower().strip()
    matched: list[str] = []
    for command in commands:
        cmd = command.lower().strip()
        if not cmd:
            continue
        if not cmd.startswith("/"):
            cmd = "/" + cmd
        pattern = r"(?:^|\s)" + re.escape(cmd) + r"(?:$|\s|[,.!?])"
        if normalized == cmd or re.search(pattern, normalized):
            matched.append(command)
    return tuple(matched)
