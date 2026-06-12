"""Tests for the filenames-only search primitives (catalog T3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.coding.search_primitives import (
    DEFAULT_DIR_SEARCH_CAP,
    DEFAULT_FILE_SEARCH_CAP,
    DEFAULT_SKIP_DIRECTORIES,
    DEFAULT_TIERED_CAPS,
    FileMatch,
    LineMatch,
    SearchResult,
    SearchTooBroadError,
    find_file_by_pattern,
    search_dir_filenames_only,
    search_in_file_with_cap,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_caps_match_swe_agent():
    assert DEFAULT_DIR_SEARCH_CAP == 100
    assert DEFAULT_FILE_SEARCH_CAP == 100


def test_tiered_caps_are_increasing():
    assert list(DEFAULT_TIERED_CAPS) == sorted(set(DEFAULT_TIERED_CAPS))


def test_skip_directories_includes_common_noise():
    for d in ("node_modules", "__pycache__", ".git", ".venv"):
        assert d in DEFAULT_SKIP_DIRECTORIES


# ---------------------------------------------------------------------------
# search_dir_filenames_only basics
# ---------------------------------------------------------------------------


def test_empty_term_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        search_dir_filenames_only("", tmp_path)


def test_missing_directory_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        search_dir_filenames_only("hi", tmp_path / "nope")


def test_basic_search_returns_file_matches(tmp_path: Path):
    (tmp_path / "a.py").write_text("hello world\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("hello world\nhello again\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("nothing here\n", encoding="utf-8")
    r = search_dir_filenames_only("hello", tmp_path, use_ripgrep=False)
    assert isinstance(r, SearchResult)
    assert r.total_matches == 3
    paths = {m.path for m in r.matches}
    assert any("a.py" in p for p in paths)
    assert any("b.py" in p for p in paths)
    assert all("c.txt" not in p for p in paths)


def test_results_sorted_by_count_desc(tmp_path: Path):
    (tmp_path / "low.py").write_text("hello\n", encoding="utf-8")
    (tmp_path / "high.py").write_text("hello\n" * 5, encoding="utf-8")
    (tmp_path / "mid.py").write_text("hello\n" * 2, encoding="utf-8")
    r = search_dir_filenames_only("hello", tmp_path, use_ripgrep=False)
    counts = [m.count for m in r.matches]  # type: ignore[union-attr]
    assert counts == sorted(counts, reverse=True)


def test_skip_directories_honoured(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("needle\n", encoding="utf-8")
    skipped = tmp_path / "node_modules"
    skipped.mkdir()
    (skipped / "b.py").write_text("needle\n" * 100, encoding="utf-8")
    r = search_dir_filenames_only("needle", tmp_path, use_ripgrep=False)
    paths = {m.path for m in r.matches}
    assert any("src" in p for p in paths)
    assert all("node_modules" not in p for p in paths)


def test_hidden_directories_skipped(tmp_path: Path):
    hidden = tmp_path / ".secret"
    hidden.mkdir()
    (hidden / "a.py").write_text("needle\n" * 50, encoding="utf-8")
    visible = tmp_path / "visible"
    visible.mkdir()
    (visible / "b.py").write_text("needle\n", encoding="utf-8")
    r = search_dir_filenames_only("needle", tmp_path, use_ripgrep=False)
    paths = {m.path for m in r.matches}
    assert all(".secret" not in p for p in paths)
    assert any("visible" in p for p in paths)


# ---------------------------------------------------------------------------
# Hard cap + overflow message
# ---------------------------------------------------------------------------


def test_overflow_raises_search_too_broad(tmp_path: Path):
    # Create more than the cap.
    for i in range(15):
        (tmp_path / f"f{i}.py").write_text("common\n", encoding="utf-8")
    with pytest.raises(SearchTooBroadError) as exc_info:
        search_dir_filenames_only(
            "common", tmp_path, max_files=10, use_ripgrep=False
        )
    err = exc_info.value
    assert err.cap == 10
    assert err.actual == 15
    assert "More than 10 files matched" in str(err)
    assert ".py=" in str(err)  # top-extensions hint


def test_overflow_includes_narrowing_tier_hint(tmp_path: Path):
    for i in range(50):
        (tmp_path / f"f{i}.py").write_text("common\n", encoding="utf-8")
    with pytest.raises(SearchTooBroadError) as exc_info:
        search_dir_filenames_only(
            "common", tmp_path, max_files=20, use_ripgrep=False
        )
    assert "narrow" in str(exc_info.value).lower()


def test_no_matches_returns_empty_result(tmp_path: Path):
    (tmp_path / "a.py").write_text("hello\n", encoding="utf-8")
    r = search_dir_filenames_only(
        "missing-term", tmp_path, use_ripgrep=False
    )
    assert r.matches == []
    assert r.total_matches == 0
    assert r.truncated is False


# ---------------------------------------------------------------------------
# search_in_file_with_cap
# ---------------------------------------------------------------------------


def test_search_in_file_returns_line_matches(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text(
        "alpha\nbeta\nalpha\nzeta\nalpha\n", encoding="utf-8"
    )
    r = search_in_file_with_cap("alpha", p)
    assert r.total_matches == 3
    assert len(r.matches) == 3
    assert isinstance(r.matches[0], LineMatch)
    assert r.matches[0].line_number == 1
    assert r.matches[1].line_number == 3
    assert r.matches[2].line_number == 5


def test_search_in_file_caps_output(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text("hit\n" * 50, encoding="utf-8")
    r = search_in_file_with_cap("hit", p, max_lines=10)
    assert len(r.matches) == 10
    assert r.total_matches == 50
    assert r.truncated is True
    assert "more selective" in r.cap_message.lower() or "refine" in r.cap_message.lower()


def test_search_in_file_empty_term_raises(tmp_path: Path):
    p = tmp_path / "x.py"
    p.write_text("body", encoding="utf-8")
    with pytest.raises(ValueError):
        search_in_file_with_cap("", p)


def test_search_in_file_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        search_in_file_with_cap("x", tmp_path / "missing.py")


def test_search_in_file_directory_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        search_in_file_with_cap("x", tmp_path)


# ---------------------------------------------------------------------------
# find_file_by_pattern
# ---------------------------------------------------------------------------


def test_find_file_by_pattern_glob(tmp_path: Path):
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "c.txt").write_text("", encoding="utf-8")
    out = find_file_by_pattern("*.py", tmp_path)
    names = [Path(p).name for p in out]
    assert "a.py" in names
    assert "b.py" in names
    assert "c.txt" not in names


def test_find_file_by_pattern_recursive(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.py").write_text("", encoding="utf-8")
    out = find_file_by_pattern("deep.py", tmp_path)
    assert any("deep.py" in p for p in out)


def test_find_file_by_pattern_skip_hidden(tmp_path: Path):
    (tmp_path / ".hidden.py").write_text("", encoding="utf-8")
    (tmp_path / "visible.py").write_text("", encoding="utf-8")
    out = find_file_by_pattern("*.py", tmp_path)
    names = [Path(p).name for p in out]
    assert ".hidden.py" not in names
    assert "visible.py" in names


def test_find_file_by_pattern_empty_pattern_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        find_file_by_pattern("", tmp_path)


def test_find_file_by_pattern_overflow(tmp_path: Path):
    for i in range(15):
        (tmp_path / f"f{i}.py").write_text("", encoding="utf-8")
    with pytest.raises(SearchTooBroadError):
        find_file_by_pattern("*.py", tmp_path, max_files=10)


# ---------------------------------------------------------------------------
# Dataclass invariants
# ---------------------------------------------------------------------------


def test_file_match_is_frozen():
    m = FileMatch(path="/x", count=1)
    with pytest.raises(Exception):
        m.count = 2  # type: ignore[misc]


def test_line_match_is_frozen():
    m = LineMatch(line_number=1, content="x")
    with pytest.raises(Exception):
        m.line_number = 2  # type: ignore[misc]
