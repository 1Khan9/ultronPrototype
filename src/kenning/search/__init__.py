"""Direct-search utilities for Kenning (ripgrep wrapper + helpers).

This package exposes the ripgrep-backed regex search surface used by
the voice path ("find files about X"), the supervisor, and any caller
that needs a byte-capped grouped textual search over local files.
"""

from __future__ import annotations

from .ripgrep import (
    DEFAULT_BINARY_NAME,
    MAX_RESULTS,
    MAX_RIPGREP_BYTES,
    MAX_RIPGREP_LINES,
    RipgrepError,
    RipgrepResult,
    RipgrepMatch,
    rg_binary_available,
    regex_search_files,
)

__all__ = [
    "DEFAULT_BINARY_NAME",
    "MAX_RESULTS",
    "MAX_RIPGREP_BYTES",
    "MAX_RIPGREP_LINES",
    "RipgrepError",
    "RipgrepMatch",
    "RipgrepResult",
    "regex_search_files",
    "rg_binary_available",
]
