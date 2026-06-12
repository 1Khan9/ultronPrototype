"""Shared fixtures for error-recovery tests.

Each test gets:
  - A tmp-path-backed ``errors.jsonl`` (no leakage between tests)
  - Reset circuit breakers (no cross-test state from a prior trip)
  - A reset phrase-source cache (each test gets a fresh shuffle cycle)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from kenning.resilience import (
    CircuitState,
    ErrorLog,
    set_error_log,
)
from kenning.resilience.phrases import reset_phrase_cache


@pytest.fixture
def errors_log(tmp_path) -> ErrorLog:
    """Tmp-backed ErrorLog; replaces the singleton for the test duration."""
    log_path = tmp_path / "errors.jsonl"
    log = ErrorLog(path=log_path)
    set_error_log(log)
    yield log
    set_error_log(ErrorLog())  # restore default


@pytest.fixture
def read_errors(errors_log) -> "callable":
    """Helper: read all error records from the test's errors.jsonl."""
    def _read() -> List[dict]:
        if not errors_log.path.is_file():
            return []
        records = []
        with errors_log.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records
    return _read


@pytest.fixture(autouse=True)
def _reset_phrase_cache():
    reset_phrase_cache()
    yield
    reset_phrase_cache()


@pytest.fixture(autouse=True)
def _reset_brave_breaker():
    """Reset the module-level Brave breaker so tests don't see stale failures."""
    from kenning.web_search import brave as _brave_mod
    _brave_mod._BRAVE_BREAKER.reset()
    yield
    _brave_mod._BRAVE_BREAKER.reset()


@pytest.fixture(autouse=True)
def _reset_jina_breaker():
    from kenning.web_search import jina as _jina_mod
    _jina_mod._JINA_BREAKER.reset()
    yield
    _jina_mod._JINA_BREAKER.reset()
