"""Routing-decision JSONL audit log.

Every classified utterance writes one line to
``logs/routing_decisions.jsonl`` for traceability:

  {"timestamp": "...", "utterance": "...", "intent": "BROWSER_AUTOMATION",
   "confidence": "high", "rule_based": true,
   "handler": "OpenClawDispatcher.handle_browser",
   "outcome": "stub", "stub_reason": "OpenClaw integration not yet complete"}

Best-effort writes — never raises. Singleton via :func:`get_routing_log`;
test-only injection via :func:`set_routing_log`.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ultron.config import get_config, resolve_path
from ultron.openclaw_routing.intents import RoutingIntent
from ultron.utils.logging import get_logger

logger = get_logger("openclaw_routing.decision_log")


class RoutingDecisionLog:
    """Append-only JSONL writer for routing decisions."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = (
            Path(path) if path is not None
            else resolve_path(get_config().routing.routing_log_path)
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def record(
        self,
        intent: RoutingIntent,
        *,
        handler: str,
        outcome: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one record. Best-effort; never raises.

        Args:
            intent: the classified routing intent.
            handler: the handler that received the dispatch
                (e.g. ``"OpenClawDispatcher.handle_browser"``,
                ``"CodingTaskRunner.start_task"``,
                ``"voice.respond"``).
            outcome: short label — ``"dispatched"``, ``"stub"``,
                ``"failed"``, ``"deferred_to_clarification"``.
            extra: optional dict merged into the record.
        """
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "utterance": intent.raw_text[:500],
            "intent": intent.kind.value,
            "confidence": intent.confidence,
            "source": intent.source,
            "reason": intent.reason,
            "rule_based": intent.source == "rule",
            "handler": handler,
            "outcome": outcome,
            "needs_clarification": intent.needs_user_clarification,
            "clarification_question": intent.clarification_question,
        }
        if intent.subtasks:
            record["subtasks"] = [
                {"order": s.order, "type": s.type, "subtype": s.subtype,
                 "description": s.description[:200]}
                for s in intent.subtasks
            ]
        if extra:
            record.update(
                {k: v for k, v in extra.items() if k not in record}
            )
        try:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as f:
                    json.dump(record, f, default=str)
                    f.write("\n")
        except OSError as e:
            logger.warning("routing_decisions.jsonl write failed: %s", e)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


_INSTANCE: Optional[RoutingDecisionLog] = None
_INSTANCE_LOCK = threading.Lock()


def get_routing_log() -> RoutingDecisionLog:
    """Lazy-initialized module-level singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = RoutingDecisionLog()
    return _INSTANCE


def set_routing_log(log: RoutingDecisionLog) -> None:
    """Test-only: swap the singleton."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = log


__all__ = ["RoutingDecisionLog", "get_routing_log", "set_routing_log"]
