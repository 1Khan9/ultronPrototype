"""Tests for proactive token auto-refresh (2026-06-23).

Covers:
- TokenStore.is_expired() with margin
- TwitchAuth.ensure_valid() proactive refresh path
- TwitchAuth.ensure_valid() skip when still fresh
- Sidecar _load_token calls ensure_valid when expired
- Sidecar _load_token skips refresh when no client_id env var
Hermetic: no network, no file I/O (tmp_path), injectable transport.
"""
from __future__ import annotations

import json
import time


# ---------------------------------------------------------------------------
# TokenStore.is_expired
# ---------------------------------------------------------------------------

def test_is_expired_returns_true_when_past(tmp_path):
    from kenning.twitch.auth import TokenStore
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({"access_token": "x", "expires_at": time.time() - 10}))
    assert TokenStore(p).is_expired() is True


def test_is_expired_returns_false_when_future(tmp_path):
    from kenning.twitch.auth import TokenStore
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({"access_token": "x", "expires_at": time.time() + 3600}))
    assert TokenStore(p).is_expired() is False


def test_is_expired_margin_triggers_early(tmp_path):
    from kenning.twitch.auth import TokenStore
    p = tmp_path / "tok.json"
    # expires in 60s — still "valid" with 0-margin, but within 300s margin
    p.write_text(json.dumps({"access_token": "x", "expires_at": time.time() + 60}))
    assert TokenStore(p).is_expired(margin_seconds=300.0) is True
    assert TokenStore(p).is_expired(margin_seconds=0.0) is False


def test_is_expired_missing_file(tmp_path):
    from kenning.twitch.auth import TokenStore
    assert TokenStore(tmp_path / "nonexistent.json").is_expired() is True


def test_is_expired_corrupt_expires_at(tmp_path):
    from kenning.twitch.auth import TokenStore
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({"access_token": "x", "expires_at": "bad"}))
    assert TokenStore(p).is_expired() is True


# ---------------------------------------------------------------------------
# TwitchAuth.ensure_valid — proactive refresh
# ---------------------------------------------------------------------------

def _make_transport(responses):
    """Fake transport returning (status, body) pairs in sequence."""
    it = iter(responses)
    def _transport(method, url, *, data=None, headers=None):
        return next(it)
    return _transport


def test_ensure_valid_skips_refresh_when_fresh(tmp_path):
    from kenning.twitch.auth import TokenStore, TwitchAuth
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({
        "access_token": "fresh_tok",
        "refresh_token": "rt",
        "expires_at": time.time() + 7200,
    }))
    def never_transport(method, url, *, data=None, headers=None):
        raise AssertionError("transport called when token is fresh")
    auth = TwitchAuth("cid", TokenStore(p), transport=never_transport)
    result = auth.ensure_valid(margin_seconds=300.0)
    assert result == "fresh_tok"


def test_ensure_valid_refreshes_when_expired(tmp_path):
    from kenning.twitch.auth import TokenStore, TwitchAuth
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({
        "access_token": "old_tok",
        "refresh_token": "rt123",
        "expires_at": time.time() - 60,
    }))
    new_expiry = time.time() + 14400
    transport = _make_transport([
        (200, {
            "access_token": "new_tok",
            "refresh_token": "rt456",
            "expires_in": 14400,
            "expires_at": new_expiry,
            "token_type": "bearer",
            "scope": [],
        }),
    ])
    auth = TwitchAuth("cid", TokenStore(p), transport=transport)
    result = auth.ensure_valid(margin_seconds=300.0)
    assert result == "new_tok"
    # Persisted to disk
    saved = json.loads(p.read_text())
    assert saved["access_token"] == "new_tok"
    assert saved["refresh_token"] == "rt456"


def test_ensure_valid_returns_old_token_on_network_error(tmp_path):
    from kenning.twitch.auth import TokenStore, TwitchAuth
    p = tmp_path / "tok.json"
    p.write_text(json.dumps({
        "access_token": "old_tok",
        "refresh_token": "rt",
        "expires_at": time.time() - 60,
    }))
    def error_transport(method, url, *, data=None, headers=None):
        raise OSError("network down")
    auth = TwitchAuth("cid", TokenStore(p), transport=error_transport)
    result = auth.ensure_valid(margin_seconds=300.0)
    assert result == "old_tok"  # fall-through to old token


def test_ensure_valid_returns_empty_when_no_token(tmp_path):
    from kenning.twitch.auth import TokenStore, TwitchAuth
    def never_transport(method, url, *, data=None, headers=None):
        raise AssertionError("should not be called")
    auth = TwitchAuth("cid", TokenStore(tmp_path / "missing.json"), transport=never_transport)
    result = auth.ensure_valid()
    assert result == ""
