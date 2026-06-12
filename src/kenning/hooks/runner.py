"""Hook runner — subprocess execution + JSON stdin/stdout protocol.

One :class:`HookRunner` per :class:`HookScript`. The runner picks the
appropriate interpreter based on the script suffix:

* ``.py`` → the venv ``python.exe`` (or ``sys.executable``).
* ``.ps1`` → ``powershell.exe -NoProfile -ExecutionPolicy Bypass -File``.
* ``.sh`` → ``bash``.
* ``.bat`` / ``.cmd`` → ``cmd.exe /c``.
* No suffix → executed directly (shebang must be present and the file
  must be executable on POSIX).

Subprocess output is parsed by extracting the LAST JSON object from
stdout so noisy debug ``print`` calls don't break the protocol.
Anything that fails to parse degrades to an outcome with
``error_message`` set; the registry then logs WARN and continues.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .discovery import HookScript
from .lifecycle import (
    DEFAULT_CONTEXT_MOD_CAP_CHARS,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    HookKind,
    HookOutcome,
    HookPayload,
)

LOGGER = logging.getLogger(__name__)

# Suppress phantom-console windows on Windows.
_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)

#: Regex picking out balanced JSON objects from stdout (last match wins).
_JSON_OBJECT_PATTERN: re.Pattern[str] = re.compile(r"\{[\s\S]*?\}")


class HookExecutionError(RuntimeError):
    """Raised on catastrophic spawn failure (e.g. interpreter missing).

    Routine errors (timeout, non-zero exit, malformed JSON) are folded
    into a :class:`HookRunResult` with ``error_message`` set instead.
    """


@dataclass(frozen=True)
class HookRunResult:
    """Outcome of a single :meth:`HookRunner.run` invocation.

    Attributes:
        script: the script that was executed.
        outcome: parsed :class:`HookOutcome` (defaults populated when
            the script failed to return a JSON envelope).
        elapsed_seconds: wall-clock duration of the execution.
        exit_code: subprocess exit code (None when the runner had to
            kill the process for timeout).
        stdout_preview: first ~400 chars of stdout (helpful for the
            audit log when the parse failed).
        stderr_preview: first ~400 chars of stderr.
        timed_out: True when the runner had to kill the process.
        parse_error: short description of a JSON parse failure (or
            empty when parsing succeeded).
    """

    script: HookScript
    outcome: HookOutcome
    elapsed_seconds: float
    exit_code: Optional[int]
    stdout_preview: str = ""
    stderr_preview: str = ""
    timed_out: bool = False
    parse_error: str = ""


class HookRunner:
    """Spawn one hook script and parse its JSON response.

    Args:
        timeout_seconds: per-execution wall-clock timeout.
        context_mod_cap_chars: cap on the ``context_modification``
            field of the parsed outcome.
        python_executable: optional override of the Python interpreter
            used for ``.py`` hooks (defaults to ``sys.executable``).
        powershell_executable: optional override of the PowerShell
            interpreter used for ``.ps1`` hooks. Defaults to
            ``"powershell.exe"`` on Windows, ``"pwsh"`` elsewhere.
        env_overrides: optional environment overrides applied to every
            spawned hook (the parent's environment is the base).
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_HOOK_TIMEOUT_SECONDS,
        context_mod_cap_chars: int = DEFAULT_CONTEXT_MOD_CAP_CHARS,
        python_executable: Optional[str] = None,
        powershell_executable: Optional[str] = None,
        env_overrides: Optional[dict[str, str]] = None,
    ) -> None:
        self._timeout = max(0.5, float(timeout_seconds))
        self._context_cap = max(0, int(context_mod_cap_chars))
        self._python = python_executable or sys.executable
        if powershell_executable is not None:
            self._powershell = powershell_executable
        else:
            self._powershell = "powershell.exe" if sys.platform == "win32" else "pwsh"
        self._env_overrides = dict(env_overrides or {})

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def run(self, script: HookScript, payload: HookPayload) -> HookRunResult:
        """Execute ``script`` with ``payload`` over stdin.

        Args:
            script: the hook script to execute.
            payload: the :class:`HookPayload` JSON-serialised on stdin.

        Returns:
            :class:`HookRunResult` describing the outcome (never raises
            on routine failures — see :class:`HookExecutionError` for
            spawn-time errors).

        Raises:
            HookExecutionError: when the subprocess cannot be spawned
                at all (interpreter missing, etc.).
        """
        command = self._build_command(script)
        env = dict(os.environ)
        env.update(self._env_overrides)
        stdin_text = json.dumps(payload.to_json(), separators=(",", ":"))
        start = time.monotonic()
        timed_out = False
        try:
            process = subprocess.Popen(  # noqa: S603 - controlled inputs
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=_CREATE_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise HookExecutionError(
                f"interpreter or script not found: {exc}"
            ) from exc
        except OSError as exc:
            raise HookExecutionError(f"failed to spawn hook: {exc}") from exc

        try:
            stdout_bytes, stderr_bytes = process.communicate(
                input=stdin_text.encode("utf-8"),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=2.0)
            except Exception:  # noqa: BLE001
                stdout_bytes, stderr_bytes = b"", b""
        elapsed = time.monotonic() - start
        stdout_text = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace")
        outcome, parse_error = self._parse_outcome(stdout_text, timed_out, stderr_text)
        return HookRunResult(
            script=script,
            outcome=outcome,
            elapsed_seconds=elapsed,
            exit_code=process.returncode if not timed_out else None,
            stdout_preview=_preview(stdout_text),
            stderr_preview=_preview(stderr_text),
            timed_out=timed_out,
            parse_error=parse_error,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(self, script: HookScript) -> list[str]:
        suffix = (script.suffix or "").lower()
        path = str(script.path)
        if suffix == ".py":
            return [self._python, path]
        if suffix == ".ps1":
            return [
                self._powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                path,
            ]
        if suffix == ".sh":
            return ["bash", path]
        if suffix in (".bat", ".cmd"):
            return ["cmd.exe", "/c", path]
        return [path]

    def _parse_outcome(
        self, stdout_text: str, timed_out: bool, stderr_text: str,
    ) -> tuple[HookOutcome, str]:
        """Parse the JSON envelope from a hook's stdout."""
        if timed_out:
            return (
                HookOutcome(
                    cancel=False,
                    context_modification="",
                    error_message=(
                        f"hook timed out after {self._timeout:.1f}s "
                        "(no envelope parsed)"
                    ),
                ),
                "timeout",
            )
        text = stdout_text.strip()
        if not text:
            return (
                HookOutcome(
                    cancel=False,
                    context_modification="",
                    error_message=(stderr_text.strip()[:400] if stderr_text else ""),
                ),
                "empty stdout",
            )
        envelope, parse_error = self._extract_envelope(text)
        if envelope is None:
            return (
                HookOutcome(
                    cancel=False,
                    context_modification="",
                    error_message=(stderr_text.strip()[:400] if stderr_text else ""),
                ),
                parse_error,
            )
        cancel = bool(envelope.get("cancel", False))
        context_mod = envelope.get("context_modification") or envelope.get(
            "contextModification", "",
        )
        if not isinstance(context_mod, str):
            context_mod = ""
        if self._context_cap and len(context_mod) > self._context_cap:
            context_mod = (
                context_mod[: self._context_cap].rstrip() + "\n... (truncated)"
            )
        error_message = envelope.get("error_message") or envelope.get(
            "errorMessage", "",
        )
        if not isinstance(error_message, str):
            error_message = ""
        extra_keys = {"cancel", "context_modification", "contextModification",
                      "error_message", "errorMessage"}
        extra = {
            k: v for k, v in envelope.items() if k not in extra_keys
        }
        return (
            HookOutcome(
                cancel=cancel,
                context_modification=context_mod,
                error_message=error_message,
                extra=extra,
            ),
            "",
        )

    @staticmethod
    def _extract_envelope(text: str) -> tuple[Optional[dict[str, Any]], str]:
        """Return the LAST balanced JSON object in ``text``.

        Useful when the hook script printed debug noise + a final JSON
        line. The walk attempts strict ``json.loads`` first; on failure
        it iterates regex matches in reverse, picks the first that
        parses, and returns it.
        """
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value, ""
        except json.JSONDecodeError:
            pass
        matches = list(_JSON_OBJECT_PATTERN.finditer(text))
        for match in reversed(matches):
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value, ""
        return None, "no parseable JSON object in stdout"


def _preview(text: str, *, cap: int = 400) -> str:
    """Truncate ``text`` for storage in :class:`HookRunResult` previews."""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= cap:
        return stripped
    return stripped[:cap] + "... (truncated)"


__all__ = [
    "HookExecutionError",
    "HookRunResult",
    "HookRunner",
]
