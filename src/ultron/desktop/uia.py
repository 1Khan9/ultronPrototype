"""UI Automation primitives via ``pywinauto``.

What this delivers without ClawHub's ``windows-control`` plugin:

- :func:`collect_window_text` -- walk a window's UIA tree and return the
  visible text strings. Used by the screen-context layer (Phase 5) to
  inject "what's actually written on screen" into Ultron's LLM context.
- :func:`find_element` -- semantic search by name / automation_id within
  a window. Returns a frozen :class:`UIAElement` snapshot.
- :func:`click_element` -- find + invoke a UIA control. Goes through
  the safety validator (Cap-3 action-verb rule, Cap-4 security-window
  rule).
- :func:`type_text_into_element` -- find + type into a UIA edit control.

Design notes:

- COM init: pywinauto's UIA backend uses comtypes; the first call from
  a thread initialises COM lazily. We accept that overhead per-call
  rather than maintain our own COM lifecycle.
- Live wrappers from pywinauto are mutable handles tied to the running
  process; we snapshot to :class:`UIAElement` so callers don't keep
  references that may go stale.
- Tree traversal is depth-limited. Deeply-nested apps (browsers, IDEs)
  can have 10k+ elements; the default cap of 200 elements is enough
  for "what's visible at the top" without blowing time.
- Fail-open at every level: a pywinauto exception logs WARN and
  returns ``None`` / empty list. The orchestrator never crashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ultron.desktop.windows import WindowInfo
from ultron.utils.logging import get_logger

logger = get_logger("desktop.uia")

# Cap on how many elements we visit during a single text-collection walk.
# Browsers and IDEs can expose tens of thousands of elements; we want
# "what's on the surface", not an exhaustive tree dump.
_DEFAULT_MAX_ELEMENTS = 200

# Cap on tree depth. Most UI controls relevant to "what's on screen"
# sit within 8 levels of the window root.
_DEFAULT_MAX_DEPTH = 8


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UIAElement:
    """Snapshot of one UI Automation element.

    Frozen because the underlying pywinauto wrapper handles are mutable
    and may go stale; this dataclass captures the metadata at lookup time.

    Attributes:
        name: element's accessible name (label text).
        control_type: UIA control type (``"Button"``, ``"Edit"``,
            ``"TabItem"``, ``"Window"``, etc.).
        automation_id: AutomationId property (set by app developers; not
            always present).
        class_name: Win32 class name (``"Chrome_WidgetWin_1"``,
            ``"Edit"``, etc.).
        rect: (left, top, right, bottom) in virtual-screen coordinates.
        is_enabled: True iff the element is enabled.
        is_visible: True iff the element is on-screen.
    """

    name: str
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    rect: tuple[int, int, int, int] = (0, 0, 0, 0)
    is_enabled: bool = True
    is_visible: bool = True


@dataclass(frozen=True)
class UIAActionResult:
    """Outcome of a UIA click / type action."""

    success: bool
    element_name: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# pywinauto lazy import
# ---------------------------------------------------------------------------


def _import_pywinauto():
    """Lazy import so ``import ultron.desktop`` doesn't pay the COM cost.

    Returns the ``pywinauto`` module, or None when import fails.
    """
    try:
        import pywinauto  # type: ignore[import]
        return pywinauto
    except Exception as e:  # noqa: BLE001
        logger.warning("pywinauto unavailable: %s", e)
        return None


def _resolve_hwnd(window: object) -> int:
    """Accept a :class:`WindowInfo` or raw hwnd; return integer hwnd."""
    if isinstance(window, WindowInfo):
        return int(window.hwnd)
    return int(window)


def _connect_window(hwnd: int):
    """Open a pywinauto connection to a window. Returns the WindowSpecification or None on failure."""
    pwa = _import_pywinauto()
    if pwa is None:
        return None
    try:
        # backend='uia' uses the modern UI Automation API; 'win32' is the
        # legacy fallback. We always use 'uia' here -- it covers
        # WPF/UWP/WinForms/Electron/Chromium, where 'win32' often returns
        # blank trees.
        app = pwa.Application(backend="uia").connect(handle=hwnd, timeout=2)
        return app.window(handle=hwnd)
    except Exception as e:  # noqa: BLE001
        logger.debug("pywinauto connect hwnd=%d failed: %s", hwnd, e)
        return None


# ---------------------------------------------------------------------------
# Text collection (the load-bearing function for screen context)
# ---------------------------------------------------------------------------


def collect_window_text(
    window: object,
    *,
    max_elements: int = _DEFAULT_MAX_ELEMENTS,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    min_length: int = 2,
) -> list[str]:
    """Walk a window's UIA tree and return visible text strings.

    Args:
        window: :class:`WindowInfo` or raw hwnd.
        max_elements: cap on total elements visited (defense against
            10k-element trees in browsers / IDEs).
        max_depth: cap on tree depth.
        min_length: skip strings shorter than this (drops single
            characters and noise).

    Returns:
        Ordered list of unique strings encountered in tree-walk order.
        Empty list when pywinauto unavailable, window can't be
        connected to, or no text was found.
    """
    hwnd = _resolve_hwnd(window)
    spec = _connect_window(hwnd)
    if spec is None:
        return []

    try:
        # Get the top-level element info for tree walk.
        elem = spec.element_info
    except Exception as e:  # noqa: BLE001
        logger.debug("element_info failed hwnd=%d: %s", hwnd, e)
        return []

    seen: set[str] = set()
    out: list[str] = []
    visited = [0]  # mutable counter to share across recursive calls

    def _walk(node, depth: int) -> None:
        if visited[0] >= max_elements:
            return
        visited[0] += 1
        try:
            name = (node.name or "").strip()
        except Exception:  # noqa: BLE001
            name = ""
        if name and len(name) >= min_length and name not in seen:
            seen.add(name)
            out.append(name)
        if depth >= max_depth:
            return
        try:
            children = node.children()
        except Exception:  # noqa: BLE001
            return
        for child in children:
            if visited[0] >= max_elements:
                return
            _walk(child, depth + 1)

    try:
        _walk(elem, 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("UIA walk hwnd=%d failed: %s", hwnd, e)

    return out


# ---------------------------------------------------------------------------
# Element lookup
# ---------------------------------------------------------------------------


def find_element(
    window: object,
    *,
    query: str = "",
    control_type: Optional[str] = None,
    automation_id: Optional[str] = None,
    exact: bool = False,
) -> Optional[UIAElement]:
    """Find a UIA element within a window.

    Matching:

    - ``automation_id`` -- exact match on AutomationId (most reliable
      when app developers expose it).
    - ``query`` -- case-insensitive substring match on element name.
    - ``control_type`` -- when set, restrict to elements of this type
      (``"Button"``, ``"Edit"``, ``"Hyperlink"``, etc.).
    - ``exact`` -- when True, require exact name match (case-insensitive
      still).

    Returns the first matching :class:`UIAElement` snapshot, or None.
    """
    hwnd = _resolve_hwnd(window)
    spec = _connect_window(hwnd)
    if spec is None:
        return None

    try:
        elem = spec.element_info
    except Exception as e:  # noqa: BLE001
        logger.debug("element_info failed hwnd=%d: %s", hwnd, e)
        return None

    q = (query or "").strip().lower()
    auto_id = (automation_id or "").strip()
    ctype = (control_type or "").strip()

    if not q and not auto_id:
        return None

    found: list[UIAElement] = []
    visited = [0]

    def _matches(node) -> bool:
        try:
            name = (node.name or "")
        except Exception:
            name = ""
        try:
            actype = (node.control_type or "")
        except Exception:
            actype = ""
        try:
            aid = (node.automation_id or "")
        except Exception:
            aid = ""

        if auto_id and aid == auto_id:
            return True
        if q:
            name_l = name.lower()
            ok_name = (name_l == q) if exact else (q in name_l)
            if not ok_name:
                return False
            if ctype and actype.lower() != ctype.lower():
                return False
            return True
        return False

    def _walk(node, depth: int) -> None:
        if visited[0] >= _DEFAULT_MAX_ELEMENTS:
            return
        visited[0] += 1
        try:
            if _matches(node):
                snap = _snapshot(node)
                found.append(snap)
                return
        except Exception:  # noqa: BLE001
            pass
        if depth >= _DEFAULT_MAX_DEPTH:
            return
        try:
            children = node.children()
        except Exception:
            return
        for child in children:
            if found:
                return
            _walk(child, depth + 1)

    try:
        _walk(elem, 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("UIA find_element hwnd=%d failed: %s", hwnd, e)

    return found[0] if found else None


def _snapshot(node) -> UIAElement:
    """Capture a UIA element's relevant fields into a frozen UIAElement."""
    def _safe(attr: str, default: str = "") -> str:
        try:
            v = getattr(node, attr, None)
            return str(v) if v else default
        except Exception:
            return default

    rect = (0, 0, 0, 0)
    try:
        r = node.rectangle
        rect = (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        pass

    is_enabled = True
    is_visible = True
    try:
        is_enabled = bool(getattr(node, "enabled", True))
    except Exception:
        pass
    try:
        is_visible = bool(getattr(node, "visible", True))
    except Exception:
        pass

    return UIAElement(
        name=_safe("name"),
        control_type=_safe("control_type"),
        automation_id=_safe("automation_id"),
        class_name=_safe("class_name"),
        rect=rect,
        is_enabled=is_enabled,
        is_visible=is_visible,
    )


# ---------------------------------------------------------------------------
# Action helpers (click / type) with safety gate
# ---------------------------------------------------------------------------


def _validate_uia_action(
    *,
    action: str,
    window_title: str,
    element_query: str,
    text: str = "",
    user_text: str = "",
) -> object:
    """Run the safety validator against a UIA action.

    The Cap-3 action-verb-click rule, Cap-3 OAuth/payment rules, and
    Cap-4 security-window rules check argument values. Pass the window
    title (often contains a URL for browsers) and the element name in
    the arguments so those patterns can match.
    """
    try:
        from ultron.safety.validator import RuleContext, get_validator

        ctx = RuleContext(
            tool_name=f"desktop.uia.{action}",
            arguments={
                "window_title": window_title,
                "element": f"'{element_query}'",
                "text": text,
            },
            capability="desktop_uia",
            user_text=user_text,
        )
        return get_validator().check(ctx)
    except Exception as e:  # noqa: BLE001
        logger.debug("UIA validator skipped: %s", e)
        from ultron.safety.validator import ValidatorVerdict, Verdict
        return ValidatorVerdict(
            verdict=Verdict.ALLOW, reason="validator unavailable",
        )


def click_element(
    window: object,
    query: str,
    *,
    automation_id: Optional[str] = None,
    control_type: Optional[str] = None,
    exact: bool = False,
    user_text: str = "",
) -> UIAActionResult:
    """Find an element and click (invoke) it.

    Goes through the safety validator first: Cap-3 action-verb-click
    matches words like ``"Submit"``, ``"Pay"``, ``"Send Money"`` and
    returns ``NEEDS_EXPLICIT_INTENT`` -- the explicit-intent matcher
    needs the user's recent utterance to contain a matching
    verb+object, otherwise the click is refused.

    Returns :class:`UIAActionResult` -- ``success=False`` and ``error``
    populated on any failure.
    """
    hwnd = _resolve_hwnd(window)
    spec = _connect_window(hwnd)
    if spec is None:
        return UIAActionResult(success=False, error="couldn't connect to window")

    try:
        win_title = spec.window_text() or ""
    except Exception:
        win_title = ""

    verdict = _validate_uia_action(
        action="click",
        window_title=win_title,
        element_query=query,
        user_text=user_text,
    )
    if not verdict.is_allowed:
        return UIAActionResult(
            success=False, element_name=query,
            error=f"safety: {verdict.reason}",
        )

    snap = find_element(
        window, query=query, control_type=control_type,
        automation_id=automation_id, exact=exact,
    )
    if snap is None:
        return UIAActionResult(
            success=False, element_name=query,
            error=f"no element matching '{query}'",
        )
    if not snap.is_enabled:
        return UIAActionResult(
            success=False, element_name=snap.name,
            error=f"element '{snap.name}' is disabled",
        )

    # Re-find the live wrapper to perform the click (the snapshot is
    # data-only).
    try:
        # Try by automation_id first (most precise), then by title.
        if snap.automation_id:
            target = spec.child_window(
                auto_id=snap.automation_id,
                control_type=snap.control_type or None,
            )
        else:
            target = spec.child_window(
                title=snap.name,
                control_type=snap.control_type or None,
            )
        target.click_input()
    except Exception as e:  # noqa: BLE001
        return UIAActionResult(
            success=False, element_name=snap.name,
            error=f"click failed: {e}",
        )

    return UIAActionResult(success=True, element_name=snap.name)


def type_text_into_element(
    window: object,
    query: str,
    text: str,
    *,
    automation_id: Optional[str] = None,
    control_type: Optional[str] = None,
    exact: bool = False,
    clear_first: bool = True,
    user_text: str = "",
) -> UIAActionResult:
    """Find a UIA edit control and type ``text`` into it.

    Args:
        clear_first: when True, the target's existing content is
            cleared (Ctrl+A, Delete) before typing.
    """
    hwnd = _resolve_hwnd(window)
    spec = _connect_window(hwnd)
    if spec is None:
        return UIAActionResult(success=False, error="couldn't connect to window")

    try:
        win_title = spec.window_text() or ""
    except Exception:
        win_title = ""

    verdict = _validate_uia_action(
        action="type",
        window_title=win_title,
        element_query=query,
        text=text,
        user_text=user_text,
    )
    if not verdict.is_allowed:
        return UIAActionResult(
            success=False, element_name=query,
            error=f"safety: {verdict.reason}",
        )

    snap = find_element(
        window, query=query, control_type=control_type or "Edit",
        automation_id=automation_id, exact=exact,
    )
    if snap is None:
        return UIAActionResult(
            success=False, element_name=query,
            error=f"no edit element matching '{query}'",
        )
    if not snap.is_enabled:
        return UIAActionResult(
            success=False, element_name=snap.name,
            error=f"element '{snap.name}' is disabled",
        )

    try:
        if snap.automation_id:
            target = spec.child_window(
                auto_id=snap.automation_id,
                control_type=snap.control_type or "Edit",
            )
        else:
            target = spec.child_window(
                title=snap.name,
                control_type=snap.control_type or "Edit",
            )
        target.set_focus()
        if clear_first:
            target.type_keys("^a{DEL}", with_spaces=True)
        # type_keys escapes special chars when set_text mode isn't usable.
        # For arbitrary user input we want literal characters, so use
        # set_text where possible (supported on EditWrapper).
        if hasattr(target, "set_text"):
            target.set_text(text)
        else:
            # Fallback: type_keys with with_spaces=True. Note: special
            # characters like {, }, ^, +, %, ~, (, ) get interpreted by
            # type_keys; consumers should use set_text for arbitrary text.
            target.type_keys(text, with_spaces=True)
    except Exception as e:  # noqa: BLE001
        return UIAActionResult(
            success=False, element_name=snap.name,
            error=f"type failed: {e}",
        )

    return UIAActionResult(success=True, element_name=snap.name)


__all__ = [
    "UIAElement",
    "UIAActionResult",
    "collect_window_text",
    "find_element",
    "click_element",
    "type_text_into_element",
]
