"""Shared fixtures for routing tests."""

from __future__ import annotations

import pytest

from kenning.openclaw_routing import (
    RoutingDecisionLog,
    set_routing_log,
)


@pytest.fixture
def routing_log(tmp_path):
    log = RoutingDecisionLog(path=tmp_path / "routing_decisions.jsonl")
    set_routing_log(log)
    yield log
    set_routing_log(RoutingDecisionLog())


@pytest.fixture
def read_routing(routing_log):
    import json

    def _read():
        if not routing_log.path.is_file():
            return []
        records = []
        with routing_log.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records
    return _read
