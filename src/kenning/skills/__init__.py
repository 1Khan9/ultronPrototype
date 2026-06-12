"""Trigger-loaded knowledge bundles ("skills") that inject capability-specific
context into the system prompt only when the user message matches a trigger.

Pattern lineage attributed in ``THIRD_PARTY_NOTICES.md``.

The OpenHands V1 server walks four sources (public / user / org / project)
and exposes a REST endpoint that the sandbox agent calls. Kenning is a
single-process voice-first assistant; we keep the multi-source merge
but skip the HTTP indirection -- a :class:`SkillRegistry` loads from
local directories directly and the orchestrator queries it in-process.

Always-on skills (no triggers) stay separate from the trigger-loaded
ones so the voice baseline can keep IDENTITY.md / SOUL.md anchored
without ceremony.
"""

from kenning.skills.models import (
    KeywordTrigger,
    Skill,
    SkillMatch,
    SkillSource,
    SkillType,
    TaskTrigger,
    Trigger,
    matches_text,
)
from kenning.skills.loader import (
    SkillLoadStats,
    load_skill_from_path,
    load_skills_from_directory,
)
from kenning.skills.registry import (
    DEFAULT_KEYWORD_MIN_USER_TEXT_CHARS,
    DEFAULT_PUBLIC_SKILLS_DIRNAME,
    DEFAULT_PROJECT_SKILLS_DIRNAME,
    DEFAULT_USER_SKILLS_DIR_NAME,
    SkillRegistry,
    build_default_registry,
    format_skills_block,
    get_skill_registry,
    maybe_get_skills_block,
    set_skill_registry,
    reset_skill_registry_for_testing,
)

__all__ = [
    "DEFAULT_KEYWORD_MIN_USER_TEXT_CHARS",
    "DEFAULT_PROJECT_SKILLS_DIRNAME",
    "DEFAULT_PUBLIC_SKILLS_DIRNAME",
    "DEFAULT_USER_SKILLS_DIR_NAME",
    "KeywordTrigger",
    "Skill",
    "SkillLoadStats",
    "SkillMatch",
    "SkillRegistry",
    "SkillSource",
    "SkillType",
    "TaskTrigger",
    "Trigger",
    "build_default_registry",
    "format_skills_block",
    "get_skill_registry",
    "load_skill_from_path",
    "load_skills_from_directory",
    "matches_text",
    "maybe_get_skills_block",
    "reset_skill_registry_for_testing",
    "set_skill_registry",
]
