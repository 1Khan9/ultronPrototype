"""Cross-cutting utilities (logging, caches, text transforms, etc.)."""

from ultron.utils.logging import configure_logging, get_logger
from ultron.utils.mtime_cache import MtimeCache, MtimeCacheError, open_mtime_cache
from ultron.utils.relative_indent import (
    RelativeIndenter,
    absolute_indent,
    relative_indent,
)
from ultron.utils.snapshot_guard import (
    SnapshotGuard,
    StaleSnapshotError,
    matches as snapshot_matches,
    take as snapshot_take,
)
from ultron.utils.token_budget import (
    BudgetTooSmallError,
    PackResult,
    char_count_tokens,
    pack_to_budget,
)

__all__ = [
    "BudgetTooSmallError",
    "MtimeCache",
    "MtimeCacheError",
    "PackResult",
    "RelativeIndenter",
    "SnapshotGuard",
    "StaleSnapshotError",
    "absolute_indent",
    "char_count_tokens",
    "configure_logging",
    "get_logger",
    "open_mtime_cache",
    "pack_to_budget",
    "relative_indent",
    "snapshot_matches",
    "snapshot_take",
]
