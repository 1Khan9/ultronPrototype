"""Tests for :mod:`kenning.coding.tree_sitter_tags`."""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.coding.tree_sitter_tags import (
    Tag,
    extract_tags,
    extract_tags_for_files,
    supported_languages,
)
from kenning.utils.mtime_cache import MtimeCache


PY_SAMPLE = """\
import os


CONST_VALUE = 42


class Greeter:
    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        return f"hello {self.name}"


def helper():
    g = Greeter("world")
    return g.greet()
"""


def test_supported_languages_includes_python():
    langs = supported_languages()
    assert "python" in langs
    # Sanity-check we shipped the documented set.
    expected = {"python", "javascript", "bash", "go", "rust", "c", "cpp", "java", "ruby", "csharp"}
    assert expected.issubset(set(langs))


def test_extract_tags_python_definitions(tmp_path: Path):
    target = tmp_path / "mod.py"
    target.write_text(PY_SAMPLE)
    tags = extract_tags(target, root=tmp_path)
    # Should have at least: class Greeter, function helper, methods.
    names = {t.name for t in tags if t.kind == "def"}
    assert "Greeter" in names
    assert "helper" in names
    # Also has refs from the helper body's `Greeter("world")` and `g.greet()`.
    ref_names = {t.name for t in tags if t.kind == "ref"}
    assert "Greeter" in ref_names or "greet" in ref_names


def test_extract_tags_rel_fname_posix(tmp_path: Path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    target = sub / "mod.py"
    target.write_text("def foo(): pass\n")
    tags = extract_tags(target, root=tmp_path)
    assert tags, "expected at least one tag from a one-line module"
    # rel_fname is POSIX with forward slashes even on Windows.
    assert tags[0].rel_fname == "pkg/mod.py"


def test_unsupported_extension_returns_empty(tmp_path: Path):
    target = tmp_path / "data.bin"
    target.write_bytes(b"\x00\x01\x02")
    assert extract_tags(target, root=tmp_path) == []


def test_missing_file_returns_empty(tmp_path: Path):
    target = tmp_path / "does_not_exist.py"
    assert extract_tags(target, root=tmp_path) == []


def test_empty_file_returns_empty(tmp_path: Path):
    target = tmp_path / "empty.py"
    target.write_text("")
    assert extract_tags(target, root=tmp_path) == []


def test_syntax_error_doesnt_crash(tmp_path: Path):
    """Tree-sitter is fault-tolerant; partial parses still yield tags
    when possible. We mostly assert it doesn't crash."""
    target = tmp_path / "broken.py"
    target.write_text("def : pass\n")
    tags = extract_tags(target, root=tmp_path)
    assert isinstance(tags, list)


def test_cache_returns_same_tags(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    src = tmp_path / "mod.py"
    src.write_text(PY_SAMPLE)
    first = extract_tags(src, root=tmp_path, cache=cache)
    second = extract_tags(src, root=tmp_path, cache=cache)
    assert first == second
    # Cache should have an entry now.
    assert len(cache) >= 1


def test_cache_invalidated_on_mtime_change(tmp_path: Path):
    import time
    cache = MtimeCache(tmp_path / "cache")
    src = tmp_path / "mod.py"
    src.write_text("def foo(): pass\n")
    first = extract_tags(src, root=tmp_path, cache=cache)
    foo_in_first = any(t.name == "foo" for t in first)
    assert foo_in_first
    time.sleep(0.01)
    src.write_text("def bar(): pass\n")
    # On Windows mtime resolution can be coarse — force a different mtime.
    import os
    st = src.stat()
    if st.st_mtime == first[0].fname:
        os.utime(src, (st.st_atime, st.st_mtime + 1))
    second = extract_tags(src, root=tmp_path, cache=cache)
    bar_in_second = any(t.name == "bar" for t in second)
    assert bar_in_second


def test_extract_tags_for_files_bulk(tmp_path: Path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def alpha(): pass\n")
    b.write_text("def beta(): pass\n")
    tags = extract_tags_for_files([a, b], root=tmp_path)
    names = {t.name for t in tags if t.kind == "def"}
    assert "alpha" in names
    assert "beta" in names


def test_tag_is_namedtuple():
    t = Tag(rel_fname="x.py", fname="/abs/x.py", line=10, name="foo", kind="def")
    assert t.kind == "def"
    assert t.line == 10
    # Iterable like a tuple.
    assert list(t)[:2] == ["x.py", "/abs/x.py"]


def test_javascript_extraction(tmp_path: Path):
    target = tmp_path / "module.js"
    target.write_text(
        "class Widget {\n"
        "  constructor(x) { this.x = x; }\n"
        "  doStuff() { return this.x; }\n"
        "}\n"
        "function helper() { return new Widget(1); }\n"
    )
    tags = extract_tags(target, root=tmp_path)
    defs = {t.name for t in tags if t.kind == "def"}
    assert "Widget" in defs
    assert "helper" in defs


def test_bash_extraction(tmp_path: Path):
    target = tmp_path / "script.sh"
    target.write_text(
        "#!/bin/bash\n"
        "MY_VAR=42\n"
        "my_fn() { echo hi; }\n"
        "my_fn\n"
    )
    tags = extract_tags(target, root=tmp_path)
    defs = {t.name for t in tags if t.kind == "def"}
    assert "my_fn" in defs
