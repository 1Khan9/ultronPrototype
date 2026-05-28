"""``browser-use`` CLI wrapper -- CDP-backed browser automation tier.

Catalog 10 batch 1 (GREEN read foundation): T1 indexed state
enumeration, T2 DOM-native CSS/HTML/text/attribute/value/bbox
extraction, T5 wait-for-element/text synchronisation, T6 tab lifecycle
management. Plus the navigation helpers (``open`` / ``back`` /
``scroll`` / ``close``) needed to drive the read primitives.

Why a new tier on top of the existing :func:`ultron.desktop.uia.extract_browser_content`:

* UIA walks the accessibility tree -- fast, zero-GPU, but limited to
  what Windows exposes. It cannot query CSS selectors, execute JS,
  read cookies, or wait for DOM mutations.
* The ``browser-use`` CLI talks Chrome DevTools Protocol via Playwright.
  Indexed elements + CSS selectors + JS eval + cookie management +
  multi-session isolation -- all the things the UIA tier cannot do.
* Integration pattern (wired in batch 9): UIA stays the first tier in
  :func:`ultron.desktop.screen_context.build_screen_context`;
  ``browser-use`` slots in as a second tier when the UIA tree returns
  empty/sparse results; the Moondream2 VLM remains the third tier.

The plugin source under ``F:\\reference_repos\\quarantine\\plugins\\clawhub-browser-use``
is documentation-only (``SKILL.md`` + two recipe markdowns; no Python
source). This module wraps the documented public API of the external
``browser-use`` open-source CLI -- it does NOT import or vendor any
upstream code. See ``THIRD_PARTY_NOTICES.md`` for attribution.

Fail-open contract (matches every other ``desktop/`` module):

* When the CLI binary is missing OR the subprocess fails OR the daemon
  reports an error, every public method returns its result dataclass
  with ``success=False`` and ``error`` populated. Callers can treat
  every method as if it might no-op.
* No exception ever escapes a public method on the happy or sad path.
  Construction does not load anything; the binary is discovered lazily
  on first call via :func:`shutil.which`.

Security tiering for this batch (all GREEN per catalog 10):

* Read-only state enumeration (T1) -- no credential surface.
* Read-only extraction (T2) -- HTML / text / attributes / bbox / value.
  ``get_value`` can expose unmasked form-field values; password-type
  inputs are skipped by the upstream CLI but this module's caller
  should not log the result without filtering.
* Synchronisation (T5) -- pure blocking wait. No side effect.
* Tab lifecycle (T6) -- ``tab close`` is destructive but the operation
  is bounded to the daemon's own browser instance; no Cap-3 gate
  because the user must explicitly invoke this via voice intent.

Later batches (3-7) add YELLOW techniques (JS eval, cookies, session
isolation, profile connect, CDP passthrough) that require Cap-3 +
two-phase approval + static analysis gating. Batch 8 adds the
``BrowserSequenceRunner`` creative extension. Batch 9 wires this tier
into :mod:`ultron.desktop.screen_context`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from ultron.utils.logging import get_logger

logger = get_logger("desktop.browser_use")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Binary names the upstream registers as aliases. Tried in order when
# no explicit ``binary_path`` is configured. ``bu`` is the shortest;
# ``browseruse`` is the no-hyphen variant some PATH conventions prefer.
BROWSER_USE_BINARY_CANDIDATES: tuple[str, ...] = (
    "browser-use",
    "bu",
    "browseruse",
)

# CREATE_NO_WINDOW on Windows suppresses the console flash that
# otherwise pops every time the CLI subprocess spawns. Matches the
# convention in :mod:`ultron.desktop.windows` and every subprocess
# site in :mod:`ultron.transcription.parakeet_engine`.
_CREATE_NO_WINDOW: int = 0x08000000 if sys.platform == "win32" else 0

# Default per-call subprocess wall-clock timeout. The upstream daemon
# documents ~50 ms per call when warm; cold-start is bounded by
# daemon-startup latency (~200-500 ms). 30 s headroom accommodates
# slow page-loads on ``open`` + ``wait_*`` commands.
DEFAULT_TIMEOUT_S: float = 30.0

# Default wait timeout for ``wait_selector`` / ``wait_text``. Matches
# the upstream CLI default of 30 s expressed in ms so the value passes
# straight to the ``--timeout`` flag without conversion.
DEFAULT_WAIT_TIMEOUT_MS: int = 30_000

# Allowed ``--state`` values for ``wait selector``. The upstream CLI
# documents these four; anything else is rejected at our boundary so
# typos surface as a clear error rather than an unhelpful CLI usage.
WAIT_SELECTOR_STATES: frozenset[str] = frozenset(
    {"visible", "hidden", "attached", "detached"}
)

# Allowed scroll directions. The upstream documents up/down; left/right
# are not exposed by the CLI surface we wrap so we reject them at our
# boundary.
SCROLL_DIRECTIONS: frozenset[str] = frozenset({"up", "down"})

# Environment variables that we strip from every subprocess call so
# ambient global state cannot silently change which session a call
# targets. ``BROWSER_USE_SESSION`` is the upstream env-var default for
# the session name; the catalog 10 "deliberately skip" list flags it
# explicitly because relying on it makes session boundaries unauditable.
_ENV_VARS_TO_SCRUB: tuple[str, ...] = (
    "BROWSER_USE_SESSION",
)

# Sentinel returned by ``state --json`` parsers when the CLI emitted
# non-JSON. Treated as a soft failure -- the raw text is preserved on
# the result so callers can fall back to substring matching.
_JSON_PARSE_FAILED: str = "__json_parse_failed__"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserUseResult:
    """Generic outcome of a CLI call.

    Every public method returns either this base type or a subclass
    that adds typed fields parsed out of the CLI's JSON or stdout.
    ``success=False`` is the universal sad-path signal; ``error`` is a
    short human-readable description (logged but never spoken verbatim
    without sanitisation).

    Attributes:
        success: True iff the CLI returned exit code 0 AND any expected
            parsing step succeeded.
        action: short label for the action performed (``"state"``,
            ``"open"``, ``"wait_selector"`` etc.); useful for the
            audit log and per-action telemetry.
        stdout: raw subprocess stdout (truncated to ``stdout_cap``).
            Always present so callers can fall back to substring
            matching when JSON parsing failed.
        stderr: raw subprocess stderr (truncated). Useful for surfacing
            the upstream daemon's actual error message.
        error: short failure reason when ``success=False``. None on
            happy path. Populated even when ``success=True`` if a
            partial-failure surfaced (e.g. JSON parse failed but exit
            code was 0).
        elapsed_ms: wall-clock time of the subprocess call, including
            spawn overhead. Useful for the latency dashboard.
        exit_code: subprocess exit code. None when the subprocess
            could not be spawned at all.
    """

    success: bool
    action: str
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    exit_code: Optional[int] = None


@dataclass(frozen=True)
class BrowserElement:
    """One element in the indexed-state enumeration.

    The upstream emits a numbered list of clickable / interactive
    elements; this dataclass captures the per-element record. Fields
    are best-effort: when the upstream output cannot be parsed (custom
    JSON shape, non-JSON output), the element list collapses to one
    entry with ``index=-1`` and the raw text in ``label`` so the caller
    can fall back to text-based matching.
    """

    index: int
    label: str = ""
    type: str = ""  # element type (button / link / input / ...)
    enabled: bool = True


@dataclass(frozen=True)
class BrowserState(BrowserUseResult):
    """T1 -- indexed state enumeration of the current page."""

    url: str = ""
    title: str = ""
    elements: tuple[BrowserElement, ...] = ()


@dataclass(frozen=True)
class BrowserHtmlResult(BrowserUseResult):
    """T2 -- ``get html [--selector]`` outcome."""

    html: str = ""
    selector: Optional[str] = None


@dataclass(frozen=True)
class BrowserTextResult(BrowserUseResult):
    """T2 -- ``get text <index>`` outcome."""

    text: str = ""
    index: int = -1


@dataclass(frozen=True)
class BrowserAttributesResult(BrowserUseResult):
    """T2 -- ``get attributes <index>`` outcome.

    ``attributes`` is best-effort parsed from the CLI output. JSON
    output yields a mapping; plain-text output yields one record with
    ``__raw__`` -> stdout so the caller can attempt their own parse.
    """

    attributes: Mapping[str, str] = field(default_factory=dict)
    index: int = -1


@dataclass(frozen=True)
class BrowserValueResult(BrowserUseResult):
    """T2 -- ``get value <index>`` outcome."""

    value: str = ""
    index: int = -1


@dataclass(frozen=True)
class BrowserBbox:
    """Bounding box for a single element. All four fields are physical
    pixels matching pyautogui's coordinate space. ``center_x`` /
    ``center_y`` are derived; callers can hand them directly to
    :meth:`ultron.desktop.input_control.InputController.click` to
    bridge protocol-level extraction with the safety-validated click
    gate stack.
    """

    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def center(self) -> tuple[int, int]:
        return (self.center_x, self.center_y)


@dataclass(frozen=True)
class BrowserBboxResult(BrowserUseResult):
    """T2 -- ``get bbox <index>`` outcome."""

    bbox: Optional[BrowserBbox] = None
    index: int = -1


@dataclass(frozen=True)
class BrowserTitleResult(BrowserUseResult):
    """``get title`` outcome -- thin convenience type."""

    title: str = ""


@dataclass(frozen=True)
class BrowserWaitResult(BrowserUseResult):
    """T5 -- ``wait selector`` / ``wait text`` outcome.

    ``matched=True`` when the condition was satisfied within the
    timeout. The CLI exits non-zero on timeout, so ``matched`` and
    ``success`` track together except in pathological cases (binary
    missing, CLI subprocess crashed).
    """

    matched: bool = False
    target: str = ""  # selector or text being waited on
    state: str = ""  # visible / hidden / attached / detached / text


@dataclass(frozen=True)
class BrowserTabInfo:
    """One open tab in the daemon's browser instance."""

    index: int
    url: str = ""
    title: str = ""
    active: bool = False


@dataclass(frozen=True)
class BrowserTabsResult(BrowserUseResult):
    """T6 -- ``tab list`` outcome."""

    tabs: tuple[BrowserTabInfo, ...] = ()


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


class BrowserUseTool:
    """Subprocess wrapper around the upstream ``browser-use`` CLI.

    The constructor is cheap: it does NOT discover or validate the
    binary, NOT spawn anything, NOT touch the network. Binary
    discovery runs lazily on the first :meth:`_invoke` call. This
    matches the rest of :mod:`ultron.desktop` -- constructed at
    orchestrator startup, lazy-resolves expensive dependencies.

    Args:
        binary_path: explicit path to the ``browser-use`` executable.
            ``None`` triggers PATH-based discovery against
            :data:`BROWSER_USE_BINARY_CANDIDATES`. An invalid path is
            tolerated -- :meth:`is_available` reflects the actual
            state and every invocation fails-open with a clear error.
        session: named session for this tool's calls. ``None`` means
            "no session flag" (the upstream defaults to ``default``).
            Multi-session orchestration arrives in batch 5 via
            :class:`ultron.desktop.browser_sessions.BrowserSessionManager`.
        default_timeout_s: per-call subprocess wall-clock timeout when
            an explicit ``timeout_s`` argument is omitted.
        headed: when True, every ``open`` call appends ``--headed``.
            Useful for debugging; the production default is headless.
        env_overrides: extra environment variables to set on each
            subprocess. The scrub list (:data:`_ENV_VARS_TO_SCRUB`)
            ALWAYS takes precedence -- callers cannot override
            ambient state through this kwarg.
    """

    def __init__(
        self,
        *,
        binary_path: Optional[str] = None,
        session: Optional[str] = None,
        default_timeout_s: float = DEFAULT_TIMEOUT_S,
        headed: bool = False,
        env_overrides: Optional[Mapping[str, str]] = None,
    ) -> None:
        if default_timeout_s <= 0:
            raise ValueError(
                f"default_timeout_s must be positive, got {default_timeout_s!r}"
            )
        if session is not None and not _is_valid_session_name(session):
            raise ValueError(
                f"session name must match [a-zA-Z0-9_-]{{1,32}}, got {session!r}"
            )
        self._binary_path_override: Optional[str] = binary_path
        self._resolved_binary: Optional[str] = None
        self._resolution_attempted: bool = False
        self._session: Optional[str] = session
        self._default_timeout_s: float = float(default_timeout_s)
        self._headed: bool = bool(headed)
        self._env_overrides: dict[str, str] = dict(env_overrides or {})

    # -- discovery -----------------------------------------------------

    def resolve_binary(self) -> Optional[str]:
        """Resolve the CLI binary, caching the result.

        Returns the absolute path on success, ``None`` when no
        candidate is on PATH. The cache survives until the next
        explicit :meth:`reset_binary_cache` call so PATH changes
        between calls do not surface (matches the upstream's own
        binary-cache pattern).
        """
        if self._resolution_attempted:
            return self._resolved_binary
        self._resolution_attempted = True
        # Explicit override wins, but is still validated against the
        # filesystem so a broken override is a clear None rather than
        # a deferred FileNotFoundError on subprocess spawn.
        if self._binary_path_override:
            candidate = shutil.which(self._binary_path_override) or (
                self._binary_path_override
                if _looks_like_existing_executable(self._binary_path_override)
                else None
            )
            if candidate:
                self._resolved_binary = candidate
                return candidate
            logger.warning(
                "browser_use: explicit binary path %r is not executable",
                self._binary_path_override,
            )
            return None
        for name in BROWSER_USE_BINARY_CANDIDATES:
            found = shutil.which(name)
            if found:
                self._resolved_binary = found
                return found
        return None

    def reset_binary_cache(self) -> None:
        """Forget the cached binary path so the next call re-discovers."""
        self._resolved_binary = None
        self._resolution_attempted = False

    def is_available(self) -> bool:
        """True iff the CLI binary is discoverable + executable."""
        return self.resolve_binary() is not None

    # -- session control (batch 5 builds on this) ---------------------

    @property
    def session(self) -> Optional[str]:
        return self._session

    def with_session(self, session: Optional[str]) -> "BrowserUseTool":
        """Return a new tool instance bound to ``session``.

        Used by :class:`BrowserSessionManager` (batch 5) to hand each
        managed session its own tool. Constructing a new instance is
        cheap because binary discovery is lazy.
        """
        if session is not None and not _is_valid_session_name(session):
            raise ValueError(
                f"session name must match [a-zA-Z0-9_-]{{1,32}}, got {session!r}"
            )
        return BrowserUseTool(
            binary_path=self._binary_path_override,
            session=session,
            default_timeout_s=self._default_timeout_s,
            headed=self._headed,
            env_overrides=self._env_overrides,
        )

    # -- navigation helpers (needed for read primitives to be useful) --

    def open(
        self,
        url: str,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """Navigate to ``url``. Returns a generic result.

        ``--headed`` is appended when the tool was constructed with
        ``headed=True``; otherwise the upstream's default (headless
        Chromium) applies.
        """
        url = (url or "").strip()
        if not url:
            return BrowserUseResult(
                success=False, action="open", error="empty url"
            )
        args: list[str] = []
        if self._headed:
            args.append("--headed")
        args.extend(["open", url])
        return self._invoke(args, action="open", timeout_s=timeout_s)

    def back(self, *, timeout_s: Optional[float] = None) -> BrowserUseResult:
        """Navigate back one entry in the tab's history."""
        return self._invoke(["back"], action="back", timeout_s=timeout_s)

    def scroll(
        self,
        direction: str = "down",
        *,
        amount: Optional[int] = None,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """Scroll the page. ``direction`` must be one of
        :data:`SCROLL_DIRECTIONS`. ``amount`` is the pixel delta when
        given; the CLI's default applies when ``None``."""
        direction = (direction or "").strip().lower()
        if direction not in SCROLL_DIRECTIONS:
            return BrowserUseResult(
                success=False,
                action="scroll",
                error=f"direction must be one of {sorted(SCROLL_DIRECTIONS)}, "
                f"got {direction!r}",
            )
        args: list[str] = ["scroll", direction]
        if amount is not None:
            if amount <= 0:
                return BrowserUseResult(
                    success=False,
                    action="scroll",
                    error=f"amount must be positive, got {amount!r}",
                )
            args.extend(["--amount", str(amount)])
        return self._invoke(args, action="scroll", timeout_s=timeout_s)

    def close(
        self,
        *,
        all_sessions: bool = False,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """Close the active browser + stop the daemon. With
        ``all_sessions=True`` closes every named session's daemon."""
        args: list[str] = ["close"]
        if all_sessions:
            args.append("--all")
        return self._invoke(args, action="close", timeout_s=timeout_s)

    # -- T1 state enumeration ------------------------------------------

    def state(self, *, timeout_s: Optional[float] = None) -> BrowserState:
        """T1 -- enumerate URL + title + indexed clickable elements.

        The upstream emits JSON when ``--json`` is passed; we always
        request it for parseability. On JSON parse failure the result
        still returns ``success=True`` (the CLI succeeded) but with
        ``elements`` empty and ``error="json parse failed"`` so
        callers can fall back to ``stdout`` substring matching.
        """
        result = self._invoke(["state", "--json"], action="state", timeout_s=timeout_s)
        if not result.success:
            return BrowserState(
                success=False,
                action="state",
                stdout=result.stdout,
                stderr=result.stderr,
                error=result.error,
                elapsed_ms=result.elapsed_ms,
                exit_code=result.exit_code,
            )
        parsed = _try_parse_state_json(result.stdout)
        if parsed is None:
            return BrowserState(
                success=True,
                action="state",
                stdout=result.stdout,
                stderr=result.stderr,
                error="json parse failed",
                elapsed_ms=result.elapsed_ms,
                exit_code=result.exit_code,
            )
        return BrowserState(
            success=True,
            action="state",
            stdout=result.stdout,
            stderr=result.stderr,
            error=None,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            url=parsed["url"],
            title=parsed["title"],
            elements=parsed["elements"],
        )

    # -- T2 DOM-native extraction -------------------------------------

    def get_html(
        self,
        selector: Optional[str] = None,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserHtmlResult:
        """T2 -- raw page HTML or selector-scoped subtree."""
        args: list[str] = ["get", "html"]
        if selector is not None:
            selector = selector.strip()
            if not selector:
                return BrowserHtmlResult(
                    success=False,
                    action="get_html",
                    error="empty selector",
                )
            args.extend(["--selector", selector])
        result = self._invoke(args, action="get_html", timeout_s=timeout_s)
        return BrowserHtmlResult(
            success=result.success,
            action="get_html",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            html=result.stdout if result.success else "",
            selector=selector,
        )

    def get_text(
        self,
        index: int,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserTextResult:
        """T2 -- element text by index."""
        if index < 0:
            return BrowserTextResult(
                success=False,
                action="get_text",
                error=f"index must be non-negative, got {index!r}",
                index=index,
            )
        result = self._invoke(
            ["get", "text", str(index)],
            action="get_text",
            timeout_s=timeout_s,
        )
        return BrowserTextResult(
            success=result.success,
            action="get_text",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            text=result.stdout.strip() if result.success else "",
            index=index,
        )

    def get_value(
        self,
        index: int,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserValueResult:
        """T2 -- input / textarea current value by index.

        Caller responsibility: the returned value may include
        autofilled secrets (passwords are excluded by the upstream
        CLI for password-type inputs but other secret-bearing fields
        are not). Do not log the value verbatim without filtering.
        """
        if index < 0:
            return BrowserValueResult(
                success=False,
                action="get_value",
                error=f"index must be non-negative, got {index!r}",
                index=index,
            )
        result = self._invoke(
            ["get", "value", str(index)],
            action="get_value",
            timeout_s=timeout_s,
        )
        return BrowserValueResult(
            success=result.success,
            action="get_value",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            value=result.stdout.rstrip("\n") if result.success else "",
            index=index,
        )

    def get_attributes(
        self,
        index: int,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserAttributesResult:
        """T2 -- element attributes by index.

        JSON output is preferred; on parse failure the raw stdout is
        forwarded under the ``__raw__`` key so callers can attempt
        their own structured parse.
        """
        if index < 0:
            return BrowserAttributesResult(
                success=False,
                action="get_attributes",
                error=f"index must be non-negative, got {index!r}",
                index=index,
            )
        result = self._invoke(
            ["get", "attributes", str(index), "--json"],
            action="get_attributes",
            timeout_s=timeout_s,
        )
        attrs: dict[str, str] = {}
        parse_error: Optional[str] = result.error
        if result.success:
            try:
                payload = json.loads(result.stdout) if result.stdout else {}
                if isinstance(payload, Mapping):
                    attrs = {str(k): str(v) for k, v in payload.items()}
                else:
                    attrs = {"__raw__": result.stdout}
                    parse_error = "non-mapping json"
            except (ValueError, json.JSONDecodeError):
                attrs = {"__raw__": result.stdout}
                parse_error = "json parse failed"
        return BrowserAttributesResult(
            success=result.success,
            action="get_attributes",
            stdout=result.stdout,
            stderr=result.stderr,
            error=parse_error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            attributes=attrs,
            index=index,
        )

    def get_bbox(
        self,
        index: int,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserBboxResult:
        """T2 -- bounding box by index.

        Returns physical pixel coordinates in pyautogui's coordinate
        space. The bridge to safety-gated clicks is:
        ``InputController.click(*result.bbox.center, user_text=...)``.
        """
        if index < 0:
            return BrowserBboxResult(
                success=False,
                action="get_bbox",
                error=f"index must be non-negative, got {index!r}",
                index=index,
            )
        result = self._invoke(
            ["get", "bbox", str(index), "--json"],
            action="get_bbox",
            timeout_s=timeout_s,
        )
        bbox: Optional[BrowserBbox] = None
        parse_error: Optional[str] = result.error
        if result.success:
            bbox, parse_error = _try_parse_bbox(result.stdout)
        return BrowserBboxResult(
            success=result.success and bbox is not None,
            action="get_bbox",
            stdout=result.stdout,
            stderr=result.stderr,
            error=parse_error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            bbox=bbox,
            index=index,
        )

    def get_title(
        self, *, timeout_s: Optional[float] = None
    ) -> BrowserTitleResult:
        """``get title`` -- page title convenience method."""
        result = self._invoke(
            ["get", "title"], action="get_title", timeout_s=timeout_s
        )
        return BrowserTitleResult(
            success=result.success,
            action="get_title",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            title=result.stdout.strip() if result.success else "",
        )

    # -- T5 synchronisation barriers -----------------------------------

    def wait_selector(
        self,
        selector: str,
        *,
        state: str = "visible",
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        timeout_s: Optional[float] = None,
    ) -> BrowserWaitResult:
        """T5 -- block until a CSS selector matches the requested state.

        ``state`` must be one of :data:`WAIT_SELECTOR_STATES`.
        ``timeout_ms`` bounds the page-level wait; ``timeout_s``
        bounds the subprocess (the latter defaults to
        ``(timeout_ms / 1000) + 5`` so the subprocess always outlives
        the page-level wait by a small margin).
        """
        selector = (selector or "").strip()
        if not selector:
            return BrowserWaitResult(
                success=False,
                action="wait_selector",
                error="empty selector",
                target=selector,
                state=state,
            )
        if state not in WAIT_SELECTOR_STATES:
            return BrowserWaitResult(
                success=False,
                action="wait_selector",
                error=f"state must be one of {sorted(WAIT_SELECTOR_STATES)}, "
                f"got {state!r}",
                target=selector,
                state=state,
            )
        if timeout_ms <= 0:
            return BrowserWaitResult(
                success=False,
                action="wait_selector",
                error=f"timeout_ms must be positive, got {timeout_ms!r}",
                target=selector,
                state=state,
            )
        effective_subprocess_timeout = (
            timeout_s if timeout_s is not None else (timeout_ms / 1000.0 + 5.0)
        )
        args = [
            "wait",
            "selector",
            selector,
            "--state",
            state,
            "--timeout",
            str(int(timeout_ms)),
        ]
        result = self._invoke(
            args, action="wait_selector", timeout_s=effective_subprocess_timeout
        )
        return BrowserWaitResult(
            success=result.success,
            action="wait_selector",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            matched=result.success,
            target=selector,
            state=state,
        )

    def wait_text(
        self,
        text: str,
        *,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        timeout_s: Optional[float] = None,
    ) -> BrowserWaitResult:
        """T5 -- block until literal text appears on the page."""
        text = text or ""
        if not text:
            return BrowserWaitResult(
                success=False,
                action="wait_text",
                error="empty text",
                target=text,
                state="text",
            )
        if timeout_ms <= 0:
            return BrowserWaitResult(
                success=False,
                action="wait_text",
                error=f"timeout_ms must be positive, got {timeout_ms!r}",
                target=text,
                state="text",
            )
        effective_subprocess_timeout = (
            timeout_s if timeout_s is not None else (timeout_ms / 1000.0 + 5.0)
        )
        args = [
            "wait",
            "text",
            text,
            "--timeout",
            str(int(timeout_ms)),
        ]
        result = self._invoke(
            args, action="wait_text", timeout_s=effective_subprocess_timeout
        )
        return BrowserWaitResult(
            success=result.success,
            action="wait_text",
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            matched=result.success,
            target=text,
            state="text",
        )

    # -- T6 tab lifecycle ----------------------------------------------

    def tab_list(self, *, timeout_s: Optional[float] = None) -> BrowserTabsResult:
        """T6 -- enumerate open tabs."""
        result = self._invoke(
            ["tab", "list", "--json"],
            action="tab_list",
            timeout_s=timeout_s,
        )
        tabs: tuple[BrowserTabInfo, ...] = ()
        parse_error: Optional[str] = result.error
        if result.success:
            tabs, parse_error = _try_parse_tabs(result.stdout)
        return BrowserTabsResult(
            success=result.success,
            action="tab_list",
            stdout=result.stdout,
            stderr=result.stderr,
            error=parse_error,
            elapsed_ms=result.elapsed_ms,
            exit_code=result.exit_code,
            tabs=tabs,
        )

    def tab_new(
        self,
        url: Optional[str] = None,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """T6 -- open a new tab. ``url`` is optional; blank tab when None."""
        args: list[str] = ["tab", "new"]
        if url is not None:
            url = url.strip()
            if not url:
                return BrowserUseResult(
                    success=False, action="tab_new", error="empty url"
                )
            args.append(url)
        return self._invoke(args, action="tab_new", timeout_s=timeout_s)

    def tab_switch(
        self,
        index: int,
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """T6 -- switch the agent's active tab to ``index``.

        Note: this only changes the agent's logical focus -- it does
        NOT change which tab the USER sees in their browser window.
        For user-visible tab switching, see batch 7's
        ``cdp_python(...)`` with ``Target.activateTarget``.
        """
        if index < 0:
            return BrowserUseResult(
                success=False,
                action="tab_switch",
                error=f"index must be non-negative, got {index!r}",
            )
        return self._invoke(
            ["tab", "switch", str(index)],
            action="tab_switch",
            timeout_s=timeout_s,
        )

    def tab_close(
        self,
        indices: Sequence[int],
        *,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """T6 -- close one or more tabs by index."""
        if not indices:
            return BrowserUseResult(
                success=False,
                action="tab_close",
                error="at least one index required",
            )
        for idx in indices:
            if idx < 0:
                return BrowserUseResult(
                    success=False,
                    action="tab_close",
                    error=f"all indices must be non-negative, got {idx!r}",
                )
        args = ["tab", "close", *(str(i) for i in indices)]
        return self._invoke(args, action="tab_close", timeout_s=timeout_s)

    # -- core subprocess invocation ------------------------------------

    def _invoke(
        self,
        args: Sequence[str],
        *,
        action: str,
        timeout_s: Optional[float] = None,
    ) -> BrowserUseResult:
        """Run a subprocess call and package the result.

        All public methods funnel through here. The shape is:

        1. Lazy-resolve the binary; fail-open with a clear error when
           it isn't on PATH.
        2. Prepend ``--session NAME`` when this instance is session-
           bound. Session goes BEFORE the subcommand per upstream
           convention; this is enforced by the order assembled here,
           not by callers.
        3. Build the env dict by scrubbing
           :data:`_ENV_VARS_TO_SCRUB` from the parent's env and
           layering ``env_overrides`` on top.
        4. Run via :func:`subprocess.run` with
           ``creationflags=_CREATE_NO_WINDOW`` on Windows.
        5. Bound stdout / stderr to ``_OUTPUT_CAP_BYTES`` so a runaway
           CLI cannot OOM the orchestrator. Larger payloads are
           truncated head + tail with an elision marker mirroring
           :func:`ultron.coding.observation_format.truncate_observation`.
        """
        binary = self.resolve_binary()
        if binary is None:
            return BrowserUseResult(
                success=False,
                action=action,
                error="browser-use binary not found on PATH",
            )
        cmd: list[str] = [binary]
        if self._session is not None:
            cmd.extend(["--session", self._session])
        cmd.extend(str(a) for a in args)
        effective_timeout = float(
            timeout_s if timeout_s is not None else self._default_timeout_s
        )
        if effective_timeout <= 0:
            return BrowserUseResult(
                success=False,
                action=action,
                error=f"timeout_s must be positive, got {effective_timeout!r}",
            )
        env = _build_scrubbed_env(self._env_overrides)
        # Use the safer subprocess.run flag tuple. CREATE_NO_WINDOW
        # is a no-op on non-Windows platforms.
        start = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 -- trusted binary lookup
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                creationflags=_CREATE_NO_WINDOW,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000.0
            return BrowserUseResult(
                success=False,
                action=action,
                error=f"subprocess timeout after {effective_timeout:.1f}s",
                elapsed_ms=elapsed,
            )
        except (FileNotFoundError, PermissionError) as exc:
            elapsed = (time.monotonic() - start) * 1000.0
            return BrowserUseResult(
                success=False,
                action=action,
                error=f"subprocess spawn failed: {type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
            )
        except OSError as exc:
            elapsed = (time.monotonic() - start) * 1000.0
            return BrowserUseResult(
                success=False,
                action=action,
                error=f"subprocess os error: {exc}",
                elapsed_ms=elapsed,
            )
        elapsed = (time.monotonic() - start) * 1000.0
        stdout = _truncate(completed.stdout or "")
        stderr = _truncate(completed.stderr or "")
        if completed.returncode != 0:
            return BrowserUseResult(
                success=False,
                action=action,
                stdout=stdout,
                stderr=stderr,
                error=_extract_cli_error(stderr, stdout)
                or f"non-zero exit code {completed.returncode}",
                elapsed_ms=elapsed,
                exit_code=completed.returncode,
            )
        return BrowserUseResult(
            success=True,
            action=action,
            stdout=stdout,
            stderr=stderr,
            elapsed_ms=elapsed,
            exit_code=completed.returncode,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_tool_singleton: Optional[BrowserUseTool] = None


def get_browser_use_tool() -> Optional[BrowserUseTool]:
    """Return the module-level singleton, or ``None`` if unset.

    Matches the pattern used by :mod:`ultron.desktop.vlm` (lazy
    construction is the orchestrator's job; readers degrade gracefully).
    """
    return _tool_singleton


def set_browser_use_tool(tool: Optional[BrowserUseTool]) -> None:
    """Set or clear the module-level singleton. Tests / orchestrator
    init use this to install a configured instance."""
    global _tool_singleton
    _tool_singleton = tool


def reset_browser_use_tool_for_testing() -> None:
    """Clear the singleton. Tests should call this in teardown."""
    set_browser_use_tool(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Max bytes of stdout / stderr we capture per call. Large enough for
# typical state JSON + HTML snippets; small enough that a runaway CLI
# cannot OOM the orchestrator.
_OUTPUT_CAP_BYTES: int = 256 * 1024  # 256 KB

# Session names: alphanumeric / underscore / hyphen, 1-32 chars. Same
# shape the catalog 10 T8 plan recommends for :class:`BrowserSessionManager`
# (batch 5). Validated at both construction and ``with_session`` time
# so an invalid name can never become a subprocess argument.
_SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def _is_valid_session_name(name: str) -> bool:
    return bool(_SESSION_NAME_RE.match(name))


def _looks_like_existing_executable(path_str: str) -> bool:
    """Cheap "is this path executable" probe used only as a fallback
    when :func:`shutil.which` returns nothing for an explicit override.
    Avoids importing :mod:`pathlib` for a one-shot OS check."""
    try:
        import os

        return os.path.isfile(path_str) and os.access(path_str, os.X_OK)
    except OSError:
        return False


def _build_scrubbed_env(
    overrides: Mapping[str, str],
) -> dict[str, str]:
    """Build the subprocess env: start from parent env, drop the
    scrub list, layer overrides on top. Overrides cannot reintroduce
    the scrubbed keys (defensive against caller misuse)."""
    import os

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in _ENV_VARS_TO_SCRUB
    }
    for k, v in overrides.items():
        if k in _ENV_VARS_TO_SCRUB:
            continue
        env[str(k)] = str(v)
    return env


def _truncate(text: str) -> str:
    """Cap large stdout / stderr payloads. Head + tail preservation
    is the readable shape; the elision marker matches
    :func:`ultron.coding.observation_format.truncate_observation`'s
    convention so existing log viewers handle it."""
    if not text:
        return ""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= _OUTPUT_CAP_BYTES:
        return text
    head = raw[: _OUTPUT_CAP_BYTES // 2]
    tail = raw[-(_OUTPUT_CAP_BYTES // 2):]
    elided = len(raw) - len(head) - len(tail)
    marker = f"\n... [{elided} bytes elided] ...\n".encode("utf-8")
    return (head + marker + tail).decode("utf-8", errors="replace")


def _extract_cli_error(stderr: str, stdout: str) -> Optional[str]:
    """Pull a short error description out of CLI output for the
    result ``error`` field. Prefers stderr first non-blank line; falls
    back to stdout when stderr is empty (some daemons emit errors on
    stdout for piping convenience)."""
    for source in (stderr, stdout):
        for raw in source.splitlines():
            line = raw.strip()
            if line:
                # Cap the surfaced error message length so a verbose
                # CLI cannot dominate the audit log.
                return line[:512]
    return None


def _try_parse_state_json(stdout: str) -> Optional[dict[str, Any]]:
    """Parse the JSON document the upstream emits for ``state --json``.

    The exact shape is daemon-version-dependent; this parser tolerates
    common variations:

    * ``{"url": ..., "title": ..., "elements": [{"index": N, "label": ..., "type": ..., "enabled": ...}, ...]}``
    * ``{"url": ..., "title": ..., "interactive_elements": [...]}``
    * Element entries may use ``text`` / ``name`` / ``label`` interchangeably.

    Returns ``None`` on irrecoverable parse failure.
    """
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    url = str(payload.get("url", "") or "")
    title = str(payload.get("title", "") or "")
    raw_elements = (
        payload.get("elements")
        or payload.get("interactive_elements")
        or payload.get("clickable_elements")
        or []
    )
    elements: list[BrowserElement] = []
    if isinstance(raw_elements, Sequence) and not isinstance(raw_elements, str):
        for i, entry in enumerate(raw_elements):
            if not isinstance(entry, Mapping):
                continue
            try:
                index = int(entry.get("index", i))
            except (TypeError, ValueError):
                index = i
            label = str(
                entry.get("label")
                or entry.get("text")
                or entry.get("name")
                or entry.get("title")
                or ""
            )
            element_type = str(
                entry.get("type")
                or entry.get("kind")
                or entry.get("role")
                or ""
            )
            enabled_raw = entry.get("enabled", True)
            enabled = bool(enabled_raw) if enabled_raw is not None else True
            elements.append(
                BrowserElement(
                    index=index,
                    label=label,
                    type=element_type,
                    enabled=enabled,
                )
            )
    return {
        "url": url,
        "title": title,
        "elements": tuple(elements),
    }


def _try_parse_bbox(stdout: str) -> tuple[Optional[BrowserBbox], Optional[str]]:
    """Parse ``get bbox --json`` output. Tolerates:

    * ``{"x": N, "y": N, "width": N, "height": N}``
    * ``{"left": N, "top": N, "width": N, "height": N}``
    * ``{"x": N, "y": N, "w": N, "h": N}``

    Returns ``(bbox, None)`` on success, ``(None, error_string)`` on
    parse failure.
    """
    if not stdout:
        return None, "empty bbox output"
    try:
        payload = json.loads(stdout)
    except (ValueError, json.JSONDecodeError):
        return None, "json parse failed"
    if not isinstance(payload, Mapping):
        return None, "non-mapping bbox output"
    try:
        x = int(payload.get("x", payload.get("left", 0)) or 0)
        y = int(payload.get("y", payload.get("top", 0)) or 0)
        width = int(payload.get("width", payload.get("w", 0)) or 0)
        height = int(payload.get("height", payload.get("h", 0)) or 0)
    except (TypeError, ValueError):
        return None, "bbox fields not integral"
    if width < 0 or height < 0:
        return None, "bbox dimensions negative"
    return BrowserBbox(x=x, y=y, width=width, height=height), None


def _try_parse_tabs(
    stdout: str,
) -> tuple[tuple[BrowserTabInfo, ...], Optional[str]]:
    """Parse ``tab list --json`` output. Returns a tuple of tabs +
    optional parse error. Tolerates:

    * ``[{"index": N, "url": ..., "title": ..., "active": bool}, ...]``
    * ``{"tabs": [...]}``
    * Missing ``active`` flag (defaults to False)
    """
    if not stdout:
        return (), "empty tabs output"
    try:
        payload = json.loads(stdout)
    except (ValueError, json.JSONDecodeError):
        return (), "json parse failed"
    if isinstance(payload, Mapping):
        candidates = payload.get("tabs")
        if candidates is None:
            return (), "no 'tabs' key in mapping"
    elif isinstance(payload, Sequence) and not isinstance(payload, str):
        candidates = payload
    else:
        return (), "unexpected tabs payload shape"
    tabs: list[BrowserTabInfo] = []
    for i, entry in enumerate(candidates):
        if not isinstance(entry, Mapping):
            continue
        try:
            index = int(entry.get("index", i))
        except (TypeError, ValueError):
            index = i
        url = str(entry.get("url", "") or "")
        title = str(entry.get("title", "") or "")
        active = bool(entry.get("active", False))
        tabs.append(
            BrowserTabInfo(index=index, url=url, title=title, active=active)
        )
    return tuple(tabs), None


__all__ = [
    "BROWSER_USE_BINARY_CANDIDATES",
    "BrowserAttributesResult",
    "BrowserBbox",
    "BrowserBboxResult",
    "BrowserElement",
    "BrowserHtmlResult",
    "BrowserState",
    "BrowserTabInfo",
    "BrowserTabsResult",
    "BrowserTextResult",
    "BrowserTitleResult",
    "BrowserUseResult",
    "BrowserUseTool",
    "BrowserValueResult",
    "BrowserWaitResult",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_WAIT_TIMEOUT_MS",
    "SCROLL_DIRECTIONS",
    "WAIT_SELECTOR_STATES",
    "get_browser_use_tool",
    "reset_browser_use_tool_for_testing",
    "set_browser_use_tool",
]
