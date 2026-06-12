"""Per-project configuration discovery (`.kenning/` convention).

Pattern lineage attributed in ``THIRD_PARTY_NOTICES.md``.

OpenHands looks for ``.openhands/skills/``, ``.openhands/setup.sh``,
``.openhands/pre-commit.sh``, ``.openhands/hooks.json`` at the project
root when starting a conversation against a repo. Kenning's analog uses
the ``.kenning/`` directory carrying:

* ``skills/`` -- per-project skill catalogue, merged at PROJECT
  precedence with the global + user sources.
* ``setup.sh`` -- one-time per-session env setup (Windows note: the
  shell is whatever the operator names; the discovery layer just
  records the path, the supervisor decides whether/how to invoke it,
  and the safety validator's explicit-intent gate fires on first
  use per repo).
* ``identity_override.md`` -- extra system prompt to append to the
  global SOUL.md/IDENTITY.md for this repo only. The voice baseline
  contract stays intact (the override is per-call appendix, not a
  mutation of the locked voice files).
* ``safety_rules.yaml`` -- per-project rule overrides layered on top
  of the global Cap-1..Cap-4 set.
* ``test_command.json`` -- custom test command the supervisor uses
  instead of the default sweep.
* ``pre_commit.sh`` (T9 precursor) -- per-project pre-commit gate.
* ``voicepack_override.json`` -- non-voicepack-file cadence override
  (``tts.pause_ms`` / ``tts.kokoro.speed`` etc.; the LOCKED voicepack
  file is NEVER touched here).
* ``intent_triggers.yaml`` -- additional voice-intent phrases for
  this project.

Discovery is sync, cheap (one stat per candidate file), mtime-cached,
and intentionally non-binding: every component is optional and the
returned :class:`ProjectConfig` carries ``None`` for missing pieces.
"""

from kenning.projects.discovery import (
    DEFAULT_PROJECT_CONFIG_DIRNAME,
    ProjectConfig,
    ProjectConfigField,
    ProjectDiscoveryStats,
    discover_project_config,
    invalidate_discovery_cache,
)

__all__ = [
    "DEFAULT_PROJECT_CONFIG_DIRNAME",
    "ProjectConfig",
    "ProjectConfigField",
    "ProjectDiscoveryStats",
    "discover_project_config",
    "invalidate_discovery_cache",
]
