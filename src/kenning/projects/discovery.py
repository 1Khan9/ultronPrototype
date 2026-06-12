"""Discover and load ``.kenning/`` per-project configuration.

The discovery layer reads files from disk and returns a frozen
:class:`ProjectConfig` snapshot. It does NOT invoke the setup script,
mutate the safety rules, or modify the global skill registry -- those
are caller-side decisions gated by the safety validator's
explicit-intent matcher (e.g. a setup.sh in a freshly-cloned repo must
get explicit user consent before any future session executes it).

The mtime cache keys on ``(repo_root, .kenning mtime)`` so a touched
config file invalidates on the next ``discover_project_config`` call.
Per the OpenHands shape, missing components are silently absent
rather than errors -- a project may opt into one piece without the
others.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

DEFAULT_PROJECT_CONFIG_DIRNAME = ".kenning"
"""Directory name under each project root holding the per-project config."""

_DEFAULT_FILENAMES: dict[str, str] = {
    "skills_dir": "skills",
    "setup_script": "setup.sh",
    "pre_commit_script": "pre_commit.sh",
    "identity_override": "identity_override.md",
    "safety_rules": "safety_rules.yaml",
    "test_command": "test_command.json",
    "voicepack_override": "voicepack_override.json",
    "intent_triggers": "intent_triggers.yaml",
    "hooks": "hooks.json",
}


class ProjectConfigField(str, Enum):
    """Stable identifiers for the recognised config fields.

    Used by callers + tests to refer to fields without hard-coding the
    on-disk filenames.
    """

    SKILLS_DIR = "skills_dir"
    SETUP_SCRIPT = "setup_script"
    PRE_COMMIT_SCRIPT = "pre_commit_script"
    IDENTITY_OVERRIDE = "identity_override"
    SAFETY_RULES = "safety_rules"
    TEST_COMMAND = "test_command"
    VOICEPACK_OVERRIDE = "voicepack_override"
    INTENT_TRIGGERS = "intent_triggers"
    HOOKS = "hooks"


@dataclass(frozen=True)
class ProjectDiscoveryStats:
    """Per-discovery diagnostic counters."""

    repo_root: Path
    config_dir: Path
    files_checked: int = 0
    files_found: int = 0
    parse_errors: tuple[str, ...] = field(default_factory=tuple)
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class ProjectConfig:
    """Snapshot of the ``.kenning/`` contents for one repository.

    Every attribute is optional; missing pieces are ``None``. The
    :attr:`raw_paths` mapping records the absolute paths the discovery
    found so callers can re-open the files (e.g. the safety validator
    re-reads ``safety_rules`` when checking gating).

    Parsed contents are exposed for the YAML/JSON files
    (:attr:`safety_rules`, :attr:`voicepack_override`, etc.) but the
    raw paths are also retained so callers that need bytes access
    don't have to re-parse via the discovery layer.
    """

    repo_root: Path
    config_dir: Path
    discovered_at: float

    skills_dir: Path | None = None
    setup_script: Path | None = None
    pre_commit_script: Path | None = None
    identity_override: str | None = None
    identity_override_path: Path | None = None
    safety_rules: Mapping[str, Any] | None = None
    safety_rules_path: Path | None = None
    test_command: Mapping[str, Any] | None = None
    test_command_path: Path | None = None
    voicepack_override: Mapping[str, Any] | None = None
    voicepack_override_path: Path | None = None
    intent_triggers: Mapping[str, Any] | None = None
    intent_triggers_path: Path | None = None
    hooks: Mapping[str, Any] | None = None
    hooks_path: Path | None = None

    raw_paths: Mapping[str, Path] = field(default_factory=dict)
    parse_errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_any_field(self) -> bool:
        """``True`` iff at least one recognised field was present."""

        return any(
            getattr(self, attr) is not None
            for attr in (
                "skills_dir",
                "setup_script",
                "pre_commit_script",
                "identity_override",
                "safety_rules",
                "test_command",
                "voicepack_override",
                "intent_triggers",
                "hooks",
            )
        )

    def get_path(self, field_name: ProjectConfigField | str) -> Path | None:
        """Return the absolute path for ``field_name`` (or ``None``)."""

        key = field_name.value if isinstance(field_name, ProjectConfigField) else field_name
        return self.raw_paths.get(key) if isinstance(self.raw_paths, dict) else None


# Discovery cache: per-repo + parent-dir-mtime.
_CACHE_LOCK = threading.RLock()
_DISCOVERY_CACHE: dict[Path, tuple[float, ProjectConfig]] = {}


def invalidate_discovery_cache(repo_root: Path | str | None = None) -> None:
    """Drop the discovery cache.

    With ``repo_root=None`` clears every entry; otherwise drops the
    single ``repo_root`` row.
    """

    with _CACHE_LOCK:
        if repo_root is None:
            _DISCOVERY_CACHE.clear()
            return
        path = Path(repo_root).resolve()
        _DISCOVERY_CACHE.pop(path, None)


def _config_dir(repo_root: Path) -> Path:
    return repo_root / DEFAULT_PROJECT_CONFIG_DIRNAME


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("project discovery: read failed for %s: %s", path, exc)
        return None


def _safe_load_json(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    text = _safe_read_text(path)
    if text is None:
        return None, "read failure"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"{path}: invalid JSON: {exc}"
        logger.warning("project discovery: %s", msg)
        return None, msg
    if not isinstance(parsed, Mapping):
        msg = f"{path}: expected JSON object at top level, got {type(parsed).__name__}"
        logger.warning("project discovery: %s", msg)
        return None, msg
    return parsed, None


def _safe_load_yaml(path: Path) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception as exc:                                    # noqa: BLE001
        return None, f"PyYAML unavailable: {exc!r}"
    text = _safe_read_text(path)
    if text is None:
        return None, "read failure"
    try:
        parsed = yaml.safe_load(text)
    except Exception as exc:                                    # noqa: BLE001
        msg = f"{path}: YAML parse error: {exc}"
        logger.warning("project discovery: %s", msg)
        return None, msg
    if parsed is None:
        return {}, None
    if not isinstance(parsed, Mapping):
        msg = f"{path}: expected mapping at top level, got {type(parsed).__name__}"
        logger.warning("project discovery: %s", msg)
        return None, msg
    return parsed, None


def _directory_mtime(directory: Path) -> float:
    """Return the most recent mtime within ``directory`` (or the dir's own).

    Walks one level deep so a touched immediate child invalidates the
    cache. ``.kenning/skills/`` deep edits should be picked up by the
    skill registry's own mtime cache (it tracks the skills/ tree
    independently); discovery only needs to spot top-level changes.
    """

    try:
        latest = directory.stat().st_mtime
    except OSError:
        return 0.0
    try:
        for entry in directory.iterdir():
            try:
                stat = entry.stat()
            except OSError:
                continue
            if stat.st_mtime > latest:
                latest = stat.st_mtime
    except OSError:
        pass
    return latest


def discover_project_config(
    repo_root: Path | str,
    *,
    use_cache: bool = True,
) -> ProjectConfig:
    """Return a :class:`ProjectConfig` for ``repo_root``.

    Args:
        repo_root: Project root directory.
        use_cache: When True (default), consult + populate the
            module-level cache keyed by ``repo_root`` + mtime
            fingerprint.

    Returns:
        A frozen :class:`ProjectConfig`. When no ``.kenning/`` directory
        exists OR the directory is empty, the returned config has
        every optional field set to ``None`` (``has_any_field=False``).
        Discovery NEVER raises -- per-file errors land in
        :attr:`ProjectConfig.parse_errors` and the affected field stays
        ``None``.
    """

    start = time.perf_counter()
    resolved_root = Path(repo_root).resolve()
    config_dir = _config_dir(resolved_root)

    # Cache lookup keyed by (resolved_root, mtime fingerprint).
    if use_cache:
        with _CACHE_LOCK:
            cached = _DISCOVERY_CACHE.get(resolved_root)
        if cached is not None:
            cached_fingerprint, cached_config = cached
            current_fp = _directory_mtime(config_dir) if config_dir.exists() else 0.0
            if current_fp == cached_fingerprint:
                return cached_config

    if not config_dir.exists() or not config_dir.is_dir():
        config = ProjectConfig(
            repo_root=resolved_root,
            config_dir=config_dir,
            discovered_at=time.time(),
        )
        if use_cache:
            with _CACHE_LOCK:
                _DISCOVERY_CACHE[resolved_root] = (0.0, config)
        return config

    parse_errors: list[str] = []
    raw_paths: dict[str, Path] = {}

    def _candidate(name: str) -> Path:
        return config_dir / _DEFAULT_FILENAMES[name]

    # --- Skills directory (existence check only) ---
    skills_dir: Path | None = None
    skills_dir_candidate = _candidate("skills_dir")
    if skills_dir_candidate.is_dir():
        skills_dir = skills_dir_candidate
        raw_paths["skills_dir"] = skills_dir

    # --- Setup script (existence + path; never invoked from here) ---
    setup_script: Path | None = None
    setup_candidate = _candidate("setup_script")
    if setup_candidate.is_file():
        setup_script = setup_candidate
        raw_paths["setup_script"] = setup_script

    # --- Pre-commit script ---
    pre_commit_script: Path | None = None
    pre_commit_candidate = _candidate("pre_commit_script")
    if pre_commit_candidate.is_file():
        pre_commit_script = pre_commit_candidate
        raw_paths["pre_commit_script"] = pre_commit_script

    # --- Identity override (read body verbatim) ---
    identity_override: str | None = None
    identity_override_path: Path | None = None
    identity_candidate = _candidate("identity_override")
    if identity_candidate.is_file():
        text = _safe_read_text(identity_candidate)
        if text is not None:
            identity_override = text
            identity_override_path = identity_candidate
            raw_paths["identity_override"] = identity_candidate

    # --- Safety rules (YAML) ---
    safety_rules: Mapping[str, Any] | None = None
    safety_rules_path: Path | None = None
    safety_candidate = _candidate("safety_rules")
    if safety_candidate.is_file():
        parsed, err = _safe_load_yaml(safety_candidate)
        if parsed is not None:
            safety_rules = parsed
            safety_rules_path = safety_candidate
            raw_paths["safety_rules"] = safety_candidate
        if err is not None:
            parse_errors.append(err)

    # --- Test command (JSON) ---
    test_command: Mapping[str, Any] | None = None
    test_command_path: Path | None = None
    test_command_candidate = _candidate("test_command")
    if test_command_candidate.is_file():
        parsed, err = _safe_load_json(test_command_candidate)
        if parsed is not None:
            test_command = parsed
            test_command_path = test_command_candidate
            raw_paths["test_command"] = test_command_candidate
        if err is not None:
            parse_errors.append(err)

    # --- Voicepack override (JSON, non-voicepack-file cadence only) ---
    voicepack_override: Mapping[str, Any] | None = None
    voicepack_override_path: Path | None = None
    voicepack_candidate = _candidate("voicepack_override")
    if voicepack_candidate.is_file():
        parsed, err = _safe_load_json(voicepack_candidate)
        if parsed is not None:
            voicepack_override = parsed
            voicepack_override_path = voicepack_candidate
            raw_paths["voicepack_override"] = voicepack_candidate
        if err is not None:
            parse_errors.append(err)

    # --- Intent triggers (YAML) ---
    intent_triggers: Mapping[str, Any] | None = None
    intent_triggers_path: Path | None = None
    intent_candidate = _candidate("intent_triggers")
    if intent_candidate.is_file():
        parsed, err = _safe_load_yaml(intent_candidate)
        if parsed is not None:
            intent_triggers = parsed
            intent_triggers_path = intent_candidate
            raw_paths["intent_triggers"] = intent_candidate
        if err is not None:
            parse_errors.append(err)

    # --- Hooks (JSON) ---
    hooks: Mapping[str, Any] | None = None
    hooks_path: Path | None = None
    hooks_candidate = _candidate("hooks")
    if hooks_candidate.is_file():
        parsed, err = _safe_load_json(hooks_candidate)
        if parsed is not None:
            hooks = parsed
            hooks_path = hooks_candidate
            raw_paths["hooks"] = hooks_candidate
        if err is not None:
            parse_errors.append(err)

    config = ProjectConfig(
        repo_root=resolved_root,
        config_dir=config_dir,
        discovered_at=time.time(),
        skills_dir=skills_dir,
        setup_script=setup_script,
        pre_commit_script=pre_commit_script,
        identity_override=identity_override,
        identity_override_path=identity_override_path,
        safety_rules=safety_rules,
        safety_rules_path=safety_rules_path,
        test_command=test_command,
        test_command_path=test_command_path,
        voicepack_override=voicepack_override,
        voicepack_override_path=voicepack_override_path,
        intent_triggers=intent_triggers,
        intent_triggers_path=intent_triggers_path,
        hooks=hooks,
        hooks_path=hooks_path,
        raw_paths=raw_paths,
        parse_errors=tuple(parse_errors),
    )

    if use_cache:
        with _CACHE_LOCK:
            fingerprint = _directory_mtime(config_dir)
            _DISCOVERY_CACHE[resolved_root] = (fingerprint, config)

    duration = time.perf_counter() - start
    if duration > 0.1:
        logger.warning(
            "project discovery for %s took %.0f ms (slow)",
            resolved_root,
            duration * 1000.0,
        )
    return config
