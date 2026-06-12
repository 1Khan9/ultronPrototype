"""Tests for :mod:`kenning.coding.important_files`."""

from __future__ import annotations

from kenning.coding.important_files import (
    IMPORTANT_FILENAMES,
    IMPORTANT_RELATIVE_PATHS,
    filter_important,
    is_important,
    promoted_score,
)


def test_classic_markers_match():
    assert is_important("README.md")
    assert is_important("pyproject.toml")
    assert is_important("package.json")
    assert is_important(".gitignore")
    assert is_important("Dockerfile")


def test_kenning_specific_additions():
    """Kenning's own operational files are in the allowlist."""
    assert is_important("CLAUDE.md")
    assert is_important("MEMORY.md")
    assert is_important("SOUL.md")
    assert is_important("THIRD_PARTY_NOTICES.md")
    assert is_important("config.yaml")


def test_modern_python_tooling():
    """Catalog extensions covering uv / ruff / etc."""
    assert is_important("uv.lock")
    assert is_important("ruff.toml")
    assert is_important("conda-lock.yml")


def test_relative_path_match():
    """Full path matches when basename alone is ambiguous."""
    assert is_important("docs/codebase_structure.md")


def test_workflow_files_match_by_path_prefix():
    """Anything under .github/workflows/ is a CI job."""
    assert is_important(".github/workflows/ci.yml")
    assert is_important(".github/workflows/release.yaml")


def test_windows_path_separator_normalised():
    """Windows backslashes are converted before matching."""
    assert is_important(r".github\workflows\ci.yml")


def test_nested_basename_match():
    """The basename match works on deeply nested README.md too."""
    assert is_important("some/deep/path/README.md")


def test_random_source_files_not_important():
    assert not is_important("src/kenning/utils/foo.py")
    assert not is_important("tests/test_random.py")
    assert not is_important("notes.txt")


def test_empty_path_returns_false():
    assert is_important("") is False


def test_filter_preserves_order():
    paths = ["a.py", "README.md", "b.py", "pyproject.toml", "c.py"]
    assert filter_important(paths) == ["README.md", "pyproject.toml"]


def test_promoted_score():
    assert promoted_score("README.md") > 0
    assert promoted_score("src/foo.py") == 0.0
    assert promoted_score("README.md", base=5.0) == 5.0


def test_important_filenames_is_frozenset():
    assert isinstance(IMPORTANT_FILENAMES, frozenset)
    # Sanity-check that we extended the aider catalog meaningfully.
    assert len(IMPORTANT_FILENAMES) > 130


def test_important_relative_paths_is_frozenset():
    assert isinstance(IMPORTANT_RELATIVE_PATHS, frozenset)
    assert "docs/codebase_structure.md" in IMPORTANT_RELATIVE_PATHS
