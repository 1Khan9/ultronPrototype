"""Tests for the T9 skills marketplace + manifest discovery."""

from __future__ import annotations

import pytest

from kenning.skills.marketplace import (
    DEFAULT_MAX_MANIFEST_BYTES,
    DEFAULT_TRUSTED_GIT_HOSTS,
    InstallPlanEntry,
    MarketplaceManifest,
    MarketplacePluginEntry,
    MarketplaceSource,
    SourceKind,
    build_install_plan,
    host_for_git_url,
    is_trusted_git_host,
    load_manifest_text,
    looks_like_github_shorthand,
    parse_github_shorthand,
    parse_json_with_tolerance,
    resolve_github_archive_url,
)


# ----------------------------------------------------------------------
# parse_json_with_tolerance


def test_parse_strict_json_unchanged() -> None:
    assert parse_json_with_tolerance('{"a": 1}') == {"a": 1}


def test_parse_strips_line_comments() -> None:
    body = '{ "a": 1, // a comment\n "b": 2 }'
    assert parse_json_with_tolerance(body) == {"a": 1, "b": 2}


def test_parse_strips_trailing_comma_in_object() -> None:
    assert parse_json_with_tolerance('{"a": 1,}') == {"a": 1}


def test_parse_strips_trailing_comma_in_array() -> None:
    assert parse_json_with_tolerance('[1, 2, 3,]') == [1, 2, 3]


def test_parse_empty_returns_empty_dict() -> None:
    assert parse_json_with_tolerance("") == {}


def test_parse_raises_on_invalid() -> None:
    with pytest.raises(ValueError):
        parse_json_with_tolerance("{ not json")


# ----------------------------------------------------------------------
# GitHub shorthand


def test_looks_like_shorthand_owner_repo() -> None:
    assert looks_like_github_shorthand("owner/repo")


def test_looks_like_shorthand_with_ref() -> None:
    assert looks_like_github_shorthand("owner/repo#main")


def test_looks_like_shorthand_with_ref_with_slash() -> None:
    assert looks_like_github_shorthand("owner/repo#release/v1")


def test_looks_like_shorthand_rejects_url() -> None:
    assert not looks_like_github_shorthand("https://github.com/owner/repo")


def test_looks_like_shorthand_rejects_git_ssh() -> None:
    assert not looks_like_github_shorthand("git@github.com:owner/repo.git")


def test_looks_like_shorthand_rejects_empty() -> None:
    assert not looks_like_github_shorthand("")


def test_parse_shorthand_no_ref() -> None:
    parsed = parse_github_shorthand("owner/repo")
    assert parsed == ("owner", "repo", "")


def test_parse_shorthand_with_ref() -> None:
    parsed = parse_github_shorthand("owner/repo#branch-name")
    assert parsed == ("owner", "repo", "branch-name")


def test_parse_shorthand_invalid_returns_none() -> None:
    assert parse_github_shorthand("not a thing") is None


# ----------------------------------------------------------------------
# load_manifest_text


def test_load_manifest_empty_returns_default() -> None:
    manifest = load_manifest_text("")
    assert manifest.plugins == ()


def test_load_manifest_oversized_raises() -> None:
    with pytest.raises(ValueError):
        load_manifest_text("x" * (DEFAULT_MAX_MANIFEST_BYTES + 1))


def test_load_manifest_non_object_root_raises() -> None:
    with pytest.raises(ValueError):
        load_manifest_text("[]")


def test_load_manifest_plugins_must_be_array() -> None:
    with pytest.raises(ValueError):
        load_manifest_text('{"plugins": "not array"}')


def test_load_manifest_entry_must_have_name() -> None:
    with pytest.raises(ValueError):
        load_manifest_text('{"plugins": [{"github": "o/r"}]}')


def test_load_manifest_github_shortcut() -> None:
    body = '{"plugins": [{"name": "skill-a", "github": "owner/repo"}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].source.kind == SourceKind.GITHUB
    assert manifest.plugins[0].source.github == "owner/repo"


def test_load_manifest_github_with_ref() -> None:
    body = '{"plugins": [{"name": "x", "github": "owner/repo#v1"}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].source.ref == "v1"


def test_load_manifest_url_shortcut() -> None:
    body = '{"plugins": [{"name": "x", "url": "https://example.com/skill.tar.gz"}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].source.kind == SourceKind.URL


def test_load_manifest_path_shortcut() -> None:
    body = '{"plugins": [{"name": "x", "path": "./local-skill"}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].source.kind == SourceKind.PATH


def test_load_manifest_explicit_source_object() -> None:
    body = '''
    {
        "plugins": [
            {
                "name": "skill",
                "source": {
                    "kind": "git",
                    "url": "https://gitlab.com/group/repo.git",
                    "ref": "main",
                    "subdir": "skills/recipe"
                }
            }
        ]
    }
    '''
    manifest = load_manifest_text(body)
    src = manifest.plugins[0].source
    assert src.kind == SourceKind.GIT_SUBDIR
    assert src.git_url == "https://gitlab.com/group/repo.git"
    assert src.subdir == "skills/recipe"


def test_load_manifest_preserves_top_level_name() -> None:
    body = '{"name": "kenning-skills-pack", "plugins": []}'
    manifest = load_manifest_text(body)
    assert manifest.name == "kenning-skills-pack"


def test_load_manifest_enabled_by_default_flag() -> None:
    body = '{"plugins": [{"name": "x", "path": "/p", "enabled_by_default": true}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].enabled_by_default is True


def test_load_manifest_tags_array() -> None:
    body = '{"plugins": [{"name": "x", "path": "/p", "tags": ["voice", "coding"]}]}'
    manifest = load_manifest_text(body)
    assert manifest.plugins[0].tags == ("voice", "coding")


# ----------------------------------------------------------------------
# host_for_git_url + is_trusted_git_host


def test_host_for_https_url() -> None:
    assert host_for_git_url("https://github.com/owner/repo.git") == "github.com"


def test_host_for_git_ssh_url() -> None:
    assert host_for_git_url("git@github.com:owner/repo.git") == "github.com"


def test_host_for_url_with_port_strips_port() -> None:
    assert host_for_git_url("https://gitlab.local:8443/x/y.git") == "gitlab.local"


def test_host_for_empty_returns_empty() -> None:
    assert host_for_git_url("") == ""


def test_is_trusted_github_default() -> None:
    assert is_trusted_git_host("https://github.com/x/y.git") is True


def test_is_trusted_rejects_unknown_host() -> None:
    assert is_trusted_git_host("https://attacker.local/x/y.git") is False


def test_is_trusted_with_custom_trusted_set() -> None:
    custom = frozenset({"git.internal"})
    assert is_trusted_git_host("https://git.internal/x/y.git", trusted=custom) is True


def test_default_trusted_includes_canonical_hosts() -> None:
    for host in ("github.com", "gitlab.com", "codeberg.org", "bitbucket.org"):
        assert host in DEFAULT_TRUSTED_GIT_HOSTS


# ----------------------------------------------------------------------
# resolve_github_archive_url


def test_resolve_archive_default_tarball() -> None:
    source = MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo")
    url = resolve_github_archive_url(source)
    assert url == "https://api.github.com/repos/owner/repo/tarball"


def test_resolve_archive_with_ref() -> None:
    source = MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo", ref="main")
    url = resolve_github_archive_url(source)
    assert url.endswith("/tarball/main")


def test_resolve_archive_zipball_format() -> None:
    source = MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo")
    url = resolve_github_archive_url(source, archive_format="zipball")
    assert "zipball" in url


def test_resolve_archive_invalid_format_raises() -> None:
    source = MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo")
    with pytest.raises(ValueError):
        resolve_github_archive_url(source, archive_format="rar")


def test_resolve_archive_wrong_kind_raises() -> None:
    source = MarketplaceSource(kind=SourceKind.URL, url="https://x")
    with pytest.raises(ValueError):
        resolve_github_archive_url(source)


def test_resolve_archive_malformed_shorthand_raises() -> None:
    source = MarketplaceSource(kind=SourceKind.GITHUB, github="garbage")
    with pytest.raises(ValueError):
        resolve_github_archive_url(source)


# ----------------------------------------------------------------------
# build_install_plan


def test_build_install_plan_github_entry() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo"),
        ),
    ))
    plan = build_install_plan(manifest)
    assert len(plan) == 1
    assert plan[0].resolved_url.startswith("https://api.github.com/")


def test_build_install_plan_path_entry_uses_path_as_url() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(kind=SourceKind.PATH, path="/local"),
        ),
    ))
    plan = build_install_plan(manifest)
    assert plan[0].resolved_url == "/local"


def test_build_install_plan_trusted_git_passes() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(
                kind=SourceKind.GIT,
                git_url="https://github.com/owner/repo.git",
            ),
        ),
    ))
    plan = build_install_plan(manifest)
    assert plan[0].resolved_url == "https://github.com/owner/repo.git"


def test_build_install_plan_untrusted_git_raises() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(
                kind=SourceKind.GIT,
                git_url="https://attacker.local/x.git",
            ),
        ),
    ))
    with pytest.raises(ValueError):
        build_install_plan(manifest)


def test_build_install_plan_url_passes_through() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(
                kind=SourceKind.URL,
                url="https://example.com/skill.tar.gz",
            ),
        ),
    ))
    plan = build_install_plan(manifest)
    assert plan[0].resolved_url == "https://example.com/skill.tar.gz"


def test_build_install_plan_custom_trusted_hosts() -> None:
    custom = frozenset({"git.internal"})
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(
                kind=SourceKind.GIT,
                git_url="https://git.internal/x.git",
            ),
        ),
    ))
    plan = build_install_plan(manifest, trusted_git_hosts=custom)
    assert plan[0].resolved_url == "https://git.internal/x.git"


def test_build_install_plan_preserves_metadata_fields() -> None:
    manifest = MarketplaceManifest(plugins=(
        MarketplacePluginEntry(
            name="x",
            source=MarketplaceSource(kind=SourceKind.GITHUB, github="owner/repo"),
            enabled_by_default=True,
            tags=("voice",),
        ),
    ))
    plan = build_install_plan(manifest)
    assert plan[0].enabled_by_default is True
    assert plan[0].tags == ("voice",)
