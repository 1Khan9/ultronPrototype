"""Allow-list of well-known root-level files plus ultron-specific
operational files.

The list is informed by aider's ``aider/special.py`` (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Extensions:

  * Modern Python tooling that post-dates aider's snapshot
    (``uv.lock``, ``ruff.toml``, ``conda-lock.yml``).
  * Ultron-internal operational files (``CLAUDE.md``,
    ``docs/codebase_structure.md``, ``MEMORY.md``, ``SOUL.md``,
    ``THIRD_PARTY_NOTICES.md``, ``config.yaml``).

Purpose: when ultron snapshots an arbitrary project on disk
(:mod:`ultron.coding.project_introspect`) or ranks files for a repo
map (:mod:`ultron.coding.repo_map`, batch 2), the README, the manifest,
the linter config and similar "what is this project" files should
always be near the top — even when nobody references them and they
have no inbound edges in the PageRank graph. They tell you what the
project IS.

For ultron's own source tree the operational files extend that idea:
``CLAUDE.md`` is the orientation document, ``docs/codebase_structure.md``
is the authoritative module map, ``MEMORY.md`` is the cross-session
context index. None are referenced by ``__import__`` but all are
load-bearing.

Public surface:

  * :data:`IMPORTANT_FILENAMES` — frozen set of bare filenames.
  * :data:`IMPORTANT_RELATIVE_PATHS` — frozen set of full relative
    paths (e.g. ``docs/codebase_structure.md``).
  * :func:`is_important` — predicate on a single path.
  * :func:`filter_important` — vectorised filter.
  * :func:`promoted_score` — small numeric bonus suitable for adding
    to a downstream ranking score.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import Iterable, List


# Bare filenames that flag a root-level file as important regardless
# of which directory it lives in. Match is case-sensitive on POSIX
# semantics with the existing aider list and extended for modern
# Python + JavaScript tooling.
_IMPORTANT_FILENAMES_LIST = (
    # Version control
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    # Documentation
    "README",
    "README.md",
    "README.rst",
    "README.txt",
    "CONTRIBUTING",
    "CONTRIBUTING.md",
    "CONTRIBUTING.rst",
    "CONTRIBUTING.txt",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "LICENSE.rst",
    "NOTICE",
    "NOTICE.md",
    "NOTICE.txt",
    "CHANGELOG",
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGELOG.txt",
    "HISTORY",
    "HISTORY.md",
    "SECURITY",
    "SECURITY.md",
    "SECURITY.txt",
    "CODEOWNERS",
    "AUTHORS",
    "AUTHORS.md",
    # Python tooling
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements_dev.txt",
    "Pipfile",
    "Pipfile.lock",
    "uv.lock",            # ultron extension (modern)
    "poetry.lock",
    "conda-lock.yml",     # ultron extension
    "environment.yml",
    "environment.yaml",
    "tox.ini",
    "pytest.ini",
    "mypy.ini",
    "ruff.toml",          # ultron extension
    ".python-version",
    "MANIFEST.in",
    # JavaScript / TypeScript tooling
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",     # ultron extension
    "bun.lockb",          # ultron extension
    "npm-shrinkwrap.json",
    "tsconfig.json",
    "jsconfig.json",
    ".babelrc",
    "babel.config.js",
    "babel.config.json",
    "webpack.config.js",
    "rollup.config.js",
    "vite.config.js",     # ultron extension
    "vite.config.ts",     # ultron extension
    "next.config.js",
    "nuxt.config.js",
    "vue.config.js",
    "angular.json",
    "gatsby-config.js",
    "gridsome.config.js",
    # Linting / formatting
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.json",
    ".eslintignore",
    ".prettierrc",
    ".prettierrc.js",
    ".prettierrc.json",
    ".prettierignore",
    ".stylelintrc",
    ".pylintrc",
    ".flake8",
    ".rubocop.yml",
    ".scalafmt.conf",
    ".isort.cfg",
    ".markdownlint.json",
    ".markdownlint.yaml",
    # Rust / Go / JVM / others
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "build.sbt",
    "build.boot",
    "build.xml",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "composer.lock",
    "mix.exs",
    "rebar.config",
    "project.clj",
    "Podfile",
    "Cartfile",
    "Package.swift",
    "dub.json",
    "dub.sdl",
    # Configuration / settings
    ".env",
    ".env.example",
    ".env.sample",
    ".editorconfig",
    ".dockerignore",
    ".gitpod.yml",
    "sonar-project.properties",
    "renovate.json",
    "dependabot.yml",
    ".pre-commit-config.yaml",
    ".pre-commit-config.yml",
    ".yamllint",
    "pyrightconfig.json",
    "tslint.json",
    # Containers
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "docker-compose.override.yml",
    "compose.yaml",
    "compose.yml",
    # Build automation
    "Makefile",
    "Justfile",           # ultron extension
    "Taskfile.yml",       # ultron extension
    "gulpfile.js",
    "Gruntfile.js",
    "parcel.config.js",
    "build.cake",
    # Cloud / infrastructure
    "serverless.yml",
    "firebase.json",
    "now.json",
    "netlify.toml",
    "vercel.json",
    "app.yaml",
    "terraform.tf",
    "main.tf",
    "cloudformation.yaml",
    "cloudformation.json",
    "ansible.cfg",
    "kubernetes.yaml",
    "k8s.yaml",
    "skaffold.yaml",      # ultron extension
    # CI / CD
    ".travis.yml",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    "appveyor.yml",
    "circle.yml",
    "codecov.yml",
    ".coveragerc",
    # Testing
    "phpunit.xml",
    "karma.conf.js",
    "jest.config.js",
    "jest.config.ts",     # ultron extension
    "vitest.config.ts",   # ultron extension
    "cypress.json",
    "cypress.config.js",  # ultron extension
    "playwright.config.ts",
    ".nycrc",
    ".nycrc.json",
    # Database
    "schema.sql",
    "liquibase.properties",
    "flyway.conf",
    "alembic.ini",        # ultron extension
    # API docs
    "swagger.yaml",
    "swagger.json",
    "openapi.yaml",
    "openapi.json",
    # Misc package registries / runtime
    ".nvmrc",
    ".ruby-version",
    ".node-version",      # ultron extension
    "Vagrantfile",
    "_config.yml",
    "mkdocs.yml",
    "book.toml",
    "readthedocs.yml",
    ".readthedocs.yaml",
    ".npmrc",
    ".yarnrc",
    ".bandit",
    ".secrets.baseline",
    ".pypirc",
    ".gitkeep",
    ".npmignore",
    ".codeclimate.yml",
    # Ultron-specific operational files (only relevant when the
    # project on disk IS ultron itself, but harmless elsewhere).
    "CLAUDE.md",
    "MEMORY.md",
    "SOUL.md",
    "THIRD_PARTY_NOTICES.md",
    "config.yaml",
)

IMPORTANT_FILENAMES: frozenset[str] = frozenset(_IMPORTANT_FILENAMES_LIST)


# Full relative paths whose entire path-from-root matters (because the
# bare filename alone is ambiguous — e.g. ``index.html`` could live
# anywhere, but ``docs/index.md`` is the docs landing page).
_IMPORTANT_RELATIVE_PATHS_LIST = (
    "docs/codebase_structure.md",
    "docs/index.md",
    "docs/README.md",
    ".github/dependabot.yml",
    ".github/workflows",   # treat any file under this as important
    ".circleci/config.yml",
)

IMPORTANT_RELATIVE_PATHS: frozenset[str] = frozenset(
    PurePosixPath(p).as_posix() for p in _IMPORTANT_RELATIVE_PATHS_LIST
)


def _to_posix(path: str) -> str:
    """Convert a filesystem path string to POSIX form for matching.

    Accepts Windows-style ``data\\config.yaml``, returns ``data/config.yaml``.
    """
    return path.replace("\\", "/")


def is_important(path: str) -> bool:
    """Return True iff ``path`` is in the always-include allowlist.

    ``path`` may be absolute or project-root-relative. Matching is on:

      * bare filename (basename) in :data:`IMPORTANT_FILENAMES`; OR
      * full relative path in :data:`IMPORTANT_RELATIVE_PATHS`; OR
      * file under ``.github/workflows`` (any name).
    """
    if not path:
        return False
    posix = _to_posix(path)
    basename = os.path.basename(posix)
    if basename in IMPORTANT_FILENAMES:
        return True
    if posix in IMPORTANT_RELATIVE_PATHS:
        return True
    # Special case: anything under .github/workflows is a CI job.
    if "/.github/workflows/" in posix or posix.startswith(".github/workflows/"):
        return True
    return False


def filter_important(paths: Iterable[str]) -> List[str]:
    """Return the subset of ``paths`` that satisfy :func:`is_important`,
    preserving input order."""
    return [p for p in paths if is_important(p)]


def promoted_score(path: str, *, base: float = 1.0) -> float:
    """Numeric bonus to add to a downstream ranking score for important paths.

    Returns ``base`` when ``path`` is important, ``0.0`` otherwise. The
    catalog's PageRank repo map (batch 2) folds this into the
    personalization vector so important files float to the top even
    without inbound references.
    """
    return base if is_important(path) else 0.0


__all__ = [
    "IMPORTANT_FILENAMES",
    "IMPORTANT_RELATIVE_PATHS",
    "filter_important",
    "is_important",
    "promoted_score",
]
