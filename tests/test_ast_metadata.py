"""Tests for the AST metadata extractor (Track 1f).

Pure stdlib-ast parsing; verifies that the structural fields
(functions_defined, functions_called, classes_defined, imports,
syntax_valid, has_main_guard, line_count) populate correctly across
clean Python, broken Python, classes-with-methods, BOM-prefixed
sources, and non-Python text. The contract this module ships is
"never raises, always returns AstMetadata" -- every error path is
covered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.coding.ast_metadata import (
    AstMetadata,
    extract_metadata_from_path,
    extract_python_metadata,
    is_python_file,
    is_syntax_valid,
)


# ---------------------------------------------------------------------------
# extract_python_metadata -- happy path
# ---------------------------------------------------------------------------


def test_extract_clean_module_with_function_definitions():
    source = (
        "def hello():\n"
        "    return 'world'\n"
        "\n"
        "def goodbye(name):\n"
        "    return f'bye {name}'\n"
    )
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is True
    assert meta.error == ""
    assert meta.functions_defined == ["hello", "goodbye"]
    assert meta.classes_defined == []
    assert meta.imports == []
    assert meta.functions_called == []


def test_extract_captures_function_calls_at_module_level():
    source = (
        "print('hello')\n"
        "len([1, 2, 3])\n"
        "sorted([3, 1, 2])\n"
    )
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is True
    # Sorted output for stable comparison.
    assert meta.functions_called == ["len", "print", "sorted"]


def test_extract_captures_attribute_call_leftmost_name():
    source = (
        "import os.path\n"
        "result = os.path.join('a', 'b')\n"
        "data = json.loads('{}')\n"
    )
    meta = extract_python_metadata(source)
    assert "os" in meta.functions_called
    assert "json" in meta.functions_called


def test_extract_captures_imports():
    source = (
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from concurrent.futures import ThreadPoolExecutor\n"
    )
    meta = extract_python_metadata(source)
    assert meta.imports == ["concurrent", "os", "pathlib", "sys"]


def test_extract_handles_class_with_methods():
    source = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "\n"
        "    def baz(self):\n"
        "        return 2\n"
        "\n"
        "    class Inner:\n"
        "        def deep(self):\n"
        "            return 3\n"
    )
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is True
    assert meta.classes_defined == ["Foo", "Foo.Inner"]
    # Methods are qualified with the enclosing class.
    assert meta.functions_defined == [
        "Foo.bar", "Foo.baz", "Foo.Inner.deep",
    ]


def test_extract_detects_main_guard():
    source = (
        "def main():\n"
        "    return 0\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    meta = extract_python_metadata(source)
    assert meta.has_main_guard is True


def test_extract_main_guard_reversed_order():
    """``'__main__' == __name__`` is the same gate, just reversed."""
    source = (
        "if '__main__' == __name__:\n"
        "    pass\n"
    )
    meta = extract_python_metadata(source)
    assert meta.has_main_guard is True


def test_extract_async_function_def():
    source = (
        "async def fetch(url):\n"
        "    return None\n"
    )
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is True
    assert meta.functions_defined == ["fetch"]


def test_extract_dotted_import_keeps_top_level():
    """``import os.path`` binds the name ``os``; we record only that."""
    source = "import os.path.something.deep\n"
    meta = extract_python_metadata(source)
    assert meta.imports == ["os"]


# ---------------------------------------------------------------------------
# extract_python_metadata -- error paths
# ---------------------------------------------------------------------------


def test_extract_syntax_error_returns_invalid():
    source = "def broken(:\n    pass\n"  # missing close paren / arg
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is False
    assert "SyntaxError" in meta.error
    assert meta.functions_defined == []


def test_extract_empty_source_is_valid_empty():
    meta = extract_python_metadata("")
    assert meta.syntax_valid is True
    assert meta.functions_defined == []
    assert meta.classes_defined == []
    assert meta.imports == []


def test_extract_none_source():
    meta = extract_python_metadata(None)  # type: ignore[arg-type]
    assert meta.syntax_valid is False
    assert "None" in meta.error


def test_extract_non_python_text():
    """Random prose isn't valid Python; the extractor returns
    invalid + a SyntaxError-shaped error message."""
    meta = extract_python_metadata("This is just some prose text.\n")
    assert meta.syntax_valid is False


def test_extract_handles_utf8_bom():
    """A BOM-prefixed source should parse cleanly (BOM stripped)."""
    source = "﻿def hello(): return 'world'\n"
    meta = extract_python_metadata(source)
    assert meta.syntax_valid is True
    assert meta.functions_defined == ["hello"]


# ---------------------------------------------------------------------------
# Line counting
# ---------------------------------------------------------------------------


def test_line_count_with_trailing_newline():
    source = "x = 1\ny = 2\nz = 3\n"
    meta = extract_python_metadata(source)
    assert meta.line_count == 3


def test_line_count_without_trailing_newline():
    source = "x = 1\ny = 2\nz = 3"
    meta = extract_python_metadata(source)
    assert meta.line_count == 3


# ---------------------------------------------------------------------------
# extract_metadata_from_path
# ---------------------------------------------------------------------------


def test_extract_from_path_reads_and_parses(tmp_path: Path):
    p = tmp_path / "sample.py"
    p.write_text("def hello(): return 'world'\n", encoding="utf-8")
    meta = extract_metadata_from_path(p)
    assert meta.syntax_valid is True
    assert meta.functions_defined == ["hello"]


def test_extract_from_path_missing_file(tmp_path: Path):
    meta = extract_metadata_from_path(tmp_path / "does_not_exist.py")
    assert meta.syntax_valid is False
    assert "file not found" in meta.error


def test_extract_from_path_non_python_file(tmp_path: Path):
    """A .txt file containing non-Python text should still return
    a result (syntax_valid=False, parser error)."""
    p = tmp_path / "notes.txt"
    p.write_text("Just some plain notes\n", encoding="utf-8")
    meta = extract_metadata_from_path(p)
    assert meta.syntax_valid is False


# ---------------------------------------------------------------------------
# is_python_file / is_syntax_valid (lightweight helpers)
# ---------------------------------------------------------------------------


def test_is_python_file_recognises_extensions(tmp_path: Path):
    assert is_python_file(tmp_path / "foo.py") is True
    assert is_python_file(tmp_path / "foo.pyi") is True
    assert is_python_file(tmp_path / "foo.PY") is True  # case-insensitive
    assert is_python_file(tmp_path / "foo.js") is False
    assert is_python_file(tmp_path / "foo.md") is False
    assert is_python_file(tmp_path / "foo") is False


def test_is_syntax_valid_fast_check():
    assert is_syntax_valid("x = 1\n") is True
    assert is_syntax_valid("def hello(): return 'world'\n") is True
    assert is_syntax_valid("def broken(:\n") is False
    assert is_syntax_valid("") is True  # empty module is valid
    assert is_syntax_valid(None) is False  # type: ignore[arg-type]
