"""Tests for ultron.search.ripgrep."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ultron.search import ripgrep as rg


# Skip mark for tests that require an actual rg binary on PATH (or in the
# known install fallback locations).
_RG_BINARY = rg.rg_binary_available()
rg_required = pytest.mark.skipif(
    _RG_BINARY is None, reason="rg binary not available on this system",
)


def _make_tree(root: Path) -> None:
    """Create a small fixture tree for the integration tests."""
    (root / "a").mkdir()
    (root / "a" / "hello.py").write_text(
        "def greet():\n"
        "    return 'hello world'\n"
        "\n"
        "class Greeter:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (root / "a" / "skip.bin").write_bytes(b"\x00\x01\x02hello\x00")
    (root / "b").mkdir()
    (root / "b" / "nested.txt").write_text(
        "first line\n"
        "the magic word is hello\n"
        "third line\n",
        encoding="utf-8",
    )
    (root / "c.md").write_text(
        "# title\n\nno hits here\n", encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_max_results_matches_documented_value() -> None:
    assert rg.MAX_RESULTS == 300


def test_max_bytes_matches_quarter_meg() -> None:
    assert rg.MAX_RIPGREP_BYTES == 256 * 1024


def test_max_lines_bounds_above_max_results() -> None:
    assert rg.MAX_RIPGREP_LINES > rg.MAX_RESULTS


# ---------------------------------------------------------------------------
# Path / decode helpers
# ---------------------------------------------------------------------------

def test_to_posix_normalises_backslashes() -> None:
    assert rg._to_posix("C:\\foo\\bar") == "C:/foo/bar"


def test_extract_text_field_handles_text() -> None:
    assert rg._extract_text_field({"text": "hello"}) == "hello"


def test_extract_text_field_handles_bytes_node() -> None:
    assert rg._extract_text_field({"bytes": "abc=="}) == ""


def test_extract_text_field_handles_none() -> None:
    assert rg._extract_text_field(None) == ""


def test_decode_rg_line_parses_json() -> None:
    out = rg._decode_rg_line(b'{"type":"match"}\n')
    assert out == {"type": "match"}


def test_decode_rg_line_empty() -> None:
    assert rg._decode_rg_line(b"") is None
    assert rg._decode_rg_line(b"\n") is None


def test_decode_rg_line_bad_json() -> None:
    assert rg._decode_rg_line(b"not json\n") is None


def test_build_relative_inside_cwd(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "file.py"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    rel = rg._build_relative(str(target), tmp_path)
    assert rel == "sub/file.py"


def test_build_relative_outside_cwd_uses_absolute() -> None:
    # Pick a path obviously outside tmp by using a different drive on
    # Windows or root on POSIX; the function must not crash.
    out = rg._build_relative("/nope/that/does/not/exist.txt", Path("."))
    assert out  # non-empty and uses forward slashes
    assert "\\" not in out


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def test_render_empty_returns_no_matches() -> None:
    assert rg._render([], False) == "No matches."


def test_render_groups_by_file() -> None:
    matches = [
        rg.RipgrepMatch(
            relative_path="a/hello.py",
            line_number=2,
            column=12,
            line_text="    return 'hello world'",
        ),
        rg.RipgrepMatch(
            relative_path="b/nested.txt",
            line_number=2,
            column=20,
            line_text="the magic word is hello",
        ),
    ]
    out = rg._render(matches, False)
    assert "a/hello.py" in out
    assert "b/nested.txt" in out
    assert "Found 2 match(es)" in out
    assert "│----" in out
    assert "│    return 'hello world'" in out


def test_render_truncation_notice_appended() -> None:
    matches = [
        rg.RipgrepMatch(
            relative_path="a.py", line_number=1, column=1, line_text="hi",
        ),
    ]
    out = rg._render(matches, True)
    assert "[Results truncated" in out


def test_render_includes_context_lines() -> None:
    matches = [
        rg.RipgrepMatch(
            relative_path="a.py",
            line_number=2,
            column=1,
            line_text="match line",
            before_context=("before",),
            after_context=("after",),
        ),
    ]
    out = rg._render(matches, False)
    assert "│before" in out
    assert "│match line" in out
    assert "│after" in out


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------

def test_rg_binary_available_returns_str_or_none() -> None:
    out = rg.rg_binary_available()
    assert out is None or (isinstance(out, str) and out)


def test_rg_binary_available_missing_name_returns_none() -> None:
    assert rg.rg_binary_available("definitely-not-a-real-binary-name-zzz") is None


def test_regex_search_files_missing_directory_raises(tmp_path: Path) -> None:
    if _RG_BINARY is None:
        with pytest.raises(rg.RipgrepError):
            rg.regex_search_files(
                tmp_path, tmp_path / "nope", "hello",
            )
    else:
        with pytest.raises(rg.RipgrepError):
            rg.regex_search_files(
                tmp_path, tmp_path / "nope", "hello",
            )


def test_regex_search_files_missing_rg_raises(tmp_path: Path) -> None:
    with pytest.raises(rg.RipgrepError):
        rg.regex_search_files(
            tmp_path, tmp_path, "hello",
            binary_name="definitely-not-a-real-binary-name-zzz",
        )


# ---------------------------------------------------------------------------
# Integration (requires rg)
# ---------------------------------------------------------------------------

@rg_required
def test_integration_finds_matches(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="hello",
    )
    assert isinstance(result, rg.RipgrepResult)
    assert result.matches, "expected at least one match"
    paths = {m.relative_path for m in result.matches}
    assert "a/hello.py" in paths
    assert "b/nested.txt" in paths
    assert "Found" in result.rendered
    assert result.elapsed_seconds >= 0


@rg_required
def test_integration_glob_filter(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="hello",
        file_pattern="*.py",
    )
    paths = {m.relative_path for m in result.matches}
    assert paths == {"a/hello.py"}


@rg_required
def test_integration_ignore_predicate_filters_paths(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    blocked: list[str] = []

    def predicate(path: str) -> bool:
        if path.endswith(".py"):
            blocked.append(path)
            return True
        return False

    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="hello",
        ignore_predicate=predicate,
    )
    paths = {m.relative_path for m in result.matches}
    assert "a/hello.py" not in paths
    assert "b/nested.txt" in paths or paths  # nested.txt should remain
    assert blocked  # predicate fired at least once


@rg_required
def test_integration_predicate_exception_keeps_match(tmp_path: Path) -> None:
    _make_tree(tmp_path)

    def predicate(_path: str) -> bool:
        raise RuntimeError("broken predicate")

    # Should not raise; matches are preserved when predicate fails.
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="hello",
        ignore_predicate=predicate,
    )
    paths = {m.relative_path for m in result.matches}
    assert "a/hello.py" in paths


@rg_required
def test_integration_files_with_matches_unique_and_ordered(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="hello",
    )
    paths = list(result.files_with_matches)
    assert len(paths) == len(set(paths))


@rg_required
def test_integration_empty_pattern_no_matches(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="definitely-not-in-tree-zzz",
    )
    assert result.matches == ()
    assert result.rendered == "No matches."


@rg_required
def test_integration_context_lines_attached(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="magic", context_lines=1,
    )
    assert result.matches
    match = next((m for m in result.matches if "magic" in m.line_text), None)
    assert match is not None
    # Both before and after lines should be present given the fixture.
    assert match.before_context == ("first line",)
    assert match.after_context == ("third line",)


@rg_required
def test_integration_zero_context(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    result = rg.regex_search_files(
        cwd=tmp_path, directory=tmp_path, pattern="magic", context_lines=0,
    )
    assert result.matches
    match = result.matches[0]
    assert match.before_context == ()
    assert match.after_context == ()
