"""Native desktop automation primitives.

This package replaces the (dormant) OpenClaw ``desktop-control`` and
``windows-control`` plugin paths with native Python implementations.
The user-led decision was to skip ClawHub plugins entirely; we get
the same UI Automation power via ``pywinauto`` and the same screen
capture power via ``mss`` -- with one Python stack to maintain and
one safety enforcement surface (the runtime tool-call validator).

Phase 1 (this file): monitors, capture, windows enumeration.
Phase 2+: launcher, placement, input_control, screen_context,
moondream2 VLM, MCP tool exposure for OpenClaw agents.

Module shape:

    src/ultron/desktop/
    +-- monitors.py        Win32 monitor enumeration
    +-- capture.py         mss-based multi-monitor capture
    +-- windows.py         pywin32 window enumeration + foreground detection
"""

from __future__ import annotations

from ultron.desktop.monitors import (
    Monitor,
    enumerate_monitors,
    find_monitor,
    point_to_monitor,
)
from ultron.desktop.capture import (
    Screenshot,
    ScreenCapture,
    ScreenCaptureError,
    get_screen_capture,
    set_screen_capture,
)
from ultron.desktop.windows import (
    CloseWindowResult,
    WindowInfo,
    close_window,
    enumerate_windows,
    get_active_window_title,
    get_foreground_window,
    find_window,
    wait_for_window,
)
from ultron.desktop.placement import (
    PlacementResult,
    move_window_to_monitor,
    maximize_window,
    minimize_window,
    restore_window,
    focus_window,
    maximize_window_idempotent,
    minimize_window_idempotent,
    restore_window_idempotent,
)
from ultron.desktop.launcher import (
    AppEntry,
    AppLauncher,
    LaunchResult,
    get_app_launcher,
    set_app_launcher,
)
from ultron.desktop.uia import (
    BROWSER_NAMES,
    BrowserContent,
    BrowserLink,
    UIAElement,
    UIAActionResult,
    UIElementInfo,
    collect_window_text,
    extract_browser_content,
    find_browser_window,
    find_element,
    click_element,
    is_browser_window,
    type_text_into_element,
    get_ui_element_inventory,
    wait_for_text_in_window,
)
from ultron.desktop.input_control import (
    InputControlResult,
    InputController,
    get_input_controller,
    set_input_controller,
)
from ultron.desktop.dialog_control import (
    DIALOG_CLASSES,
    DIALOG_CONTROL_TYPES,
    DIALOG_TITLE_KEYWORDS,
    DISMISS_BUTTONS,
    DialogActionResult,
    DialogButton,
    DialogCheckbox,
    DialogContent,
    DialogField,
    DialogInfo,
    click_dialog_button,
    dismiss_dialog,
    find_dialogs,
    read_dialog,
    type_into_dialog_field,
    wait_for_dialog,
)
from ultron.desktop.element_click import (
    CLICKABLE_TYPES,
    ClickResult,
    TextMatch,
    UIElementMatch,
    click_element_by_name,
    find_elements_by_name,
    find_text_in_window,
)
from ultron.desktop.screen_context import (
    ScreenContextSnapshot,
    ScreenContextCache,
    build_screen_context,
    capture_and_cache,
    get_screen_context_cache,
    set_screen_context_cache,
    set_vlm_describe,
    get_vlm_describe,
)
from ultron.desktop.vlm import (
    Moondream2VLM,
    VLMResult,
    VLMLoadError,
    build_vlm_from_config,
    get_vlm,
    set_vlm,
)
from ultron.desktop.voice import (
    AppLaunchVoiceResult,
    ScreenContextVoiceResult,
    handle_app_launch,
    handle_screen_context_query,
)

__all__ = [
    # monitors
    "Monitor",
    "enumerate_monitors",
    "find_monitor",
    "point_to_monitor",
    # capture
    "Screenshot",
    "ScreenCapture",
    "ScreenCaptureError",
    "get_screen_capture",
    "set_screen_capture",
    # windows
    "CloseWindowResult",
    "WindowInfo",
    "close_window",
    "enumerate_windows",
    "get_active_window_title",
    "get_foreground_window",
    "find_window",
    "wait_for_window",
    # placement
    "PlacementResult",
    "move_window_to_monitor",
    "maximize_window",
    "minimize_window",
    "restore_window",
    "focus_window",
    "maximize_window_idempotent",
    "minimize_window_idempotent",
    "restore_window_idempotent",
    # launcher
    "AppEntry",
    "AppLauncher",
    "LaunchResult",
    "get_app_launcher",
    "set_app_launcher",
    # uia
    "UIAElement",
    "UIAActionResult",
    "UIElementInfo",
    "BrowserContent",
    "BrowserLink",
    "BROWSER_NAMES",
    "collect_window_text",
    "find_element",
    "click_element",
    "type_text_into_element",
    "get_ui_element_inventory",
    "wait_for_text_in_window",
    "is_browser_window",
    "find_browser_window",
    "extract_browser_content",
    # input_control
    "InputControlResult",
    "InputController",
    "get_input_controller",
    "set_input_controller",
    # dialog_control (catalog 08 T1)
    "DIALOG_CLASSES",
    "DIALOG_CONTROL_TYPES",
    "DIALOG_TITLE_KEYWORDS",
    "DISMISS_BUTTONS",
    "DialogActionResult",
    "DialogButton",
    "DialogCheckbox",
    "DialogContent",
    "DialogField",
    "DialogInfo",
    "click_dialog_button",
    "dismiss_dialog",
    "find_dialogs",
    "read_dialog",
    "type_into_dialog_field",
    "wait_for_dialog",
    # element_click (catalog 08 T3)
    "CLICKABLE_TYPES",
    "ClickResult",
    "TextMatch",
    "UIElementMatch",
    "click_element_by_name",
    "find_elements_by_name",
    "find_text_in_window",
    # screen_context
    "ScreenContextSnapshot",
    "ScreenContextCache",
    "build_screen_context",
    "capture_and_cache",
    "get_screen_context_cache",
    "set_screen_context_cache",
    "set_vlm_describe",
    "get_vlm_describe",
    # vlm
    "Moondream2VLM",
    "VLMResult",
    "VLMLoadError",
    "build_vlm_from_config",
    "get_vlm",
    "set_vlm",
    # voice (Phase 8 intent handlers)
    "AppLaunchVoiceResult",
    "ScreenContextVoiceResult",
    "handle_app_launch",
    "handle_screen_context_query",
]
