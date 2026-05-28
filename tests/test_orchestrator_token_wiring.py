"""Tests for the openclaw-clawhub T7 short-lived-token wiring in the
orchestrator (Batch B of the deferred-primitive wiring pass).

Uses Orchestrator.__new__ to exercise _mint_forensic_token without
the heavy voice-stack init. The real round-trip redirects
ultron.config.PROJECT_ROOT to a tmp_path so nothing touches the repo
data/ dir (R9). Per docs/test_sweep_binding_rules.md: R1, R4, R7,
R9, R11.
"""

from __future__ import annotations

from typing import Any

import pytest


def _bare_orchestrator() -> Any:
    from ultron.pipeline.orchestrator import Orchestrator

    return Orchestrator.__new__(Orchestrator)


# ---------------------------------------------------------------------------
# Wiring-logic tests (token functions mocked; no disk)
# ---------------------------------------------------------------------------


class TestMintForensicTokenWiring:
    def test_registers_when_caller_unknown_then_mints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.identity.short_lived_token as slt

        registered: list = []
        mint_calls: list = []
        monkeypatch.setattr(slt, "load_trusted_caller", lambda cid, *, project_root: None)
        monkeypatch.setattr(
            slt, "register_trusted_caller",
            lambda caller, *, project_root, **k: registered.append(caller) or caller,
        )
        monkeypatch.setattr(
            slt, "mint_token",
            lambda **kw: mint_calls.append(kw) or "fake.jwt.token",
        )
        o = _bare_orchestrator()
        token = o._mint_forensic_token(
            caller_id="mcp:tools",
            audience="ultron-mcp",
            scope=("mcp.tools.read", "mcp.tools.invoke"),
            ttl_seconds=3600,
            extra_claims={"sse_url": "http://x"},
        )
        assert token == "fake.jwt.token"
        assert len(registered) == 1
        assert registered[0].caller_id == "mcp:tools"
        assert registered[0].allowed_scopes == (
            "mcp.tools.read", "mcp.tools.invoke",
        )
        assert len(mint_calls) == 1
        kw = mint_calls[0]
        assert kw["caller_id"] == "mcp:tools"
        assert kw["audience"] == "ultron-mcp"
        assert kw["scope"] == ("mcp.tools.read", "mcp.tools.invoke")
        assert kw["ttl_seconds"] == 3600
        # pid is auto-added; extra claim preserved.
        assert "pid" in kw["extra_claims"]
        assert kw["extra_claims"]["sse_url"] == "http://x"

    def test_skips_register_when_caller_known(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.identity.short_lived_token as slt

        registered: list = []
        existing = slt.TrustedCaller(caller_id="mcp:tools")
        monkeypatch.setattr(
            slt, "load_trusted_caller", lambda cid, *, project_root: existing
        )
        monkeypatch.setattr(
            slt, "register_trusted_caller",
            lambda caller, *, project_root, **k: registered.append(caller) or caller,
        )
        monkeypatch.setattr(slt, "mint_token", lambda **kw: "tok")
        o = _bare_orchestrator()
        token = o._mint_forensic_token(
            caller_id="mcp:tools",
            audience="ultron-mcp",
            scope=("mcp.tools.read",),
            ttl_seconds=3600,
        )
        assert token == "tok"
        # Already-known caller -> no re-register.
        assert registered == []

    def test_fail_open_on_mint_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.identity.short_lived_token as slt

        monkeypatch.setattr(slt, "load_trusted_caller", lambda cid, *, project_root: None)
        monkeypatch.setattr(
            slt, "register_trusted_caller", lambda caller, *, project_root, **k: caller
        )

        def boom(**kw: Any) -> Any:
            raise RuntimeError("mint failed")

        monkeypatch.setattr(slt, "mint_token", boom)
        o = _bare_orchestrator()
        # Must swallow the error and return None.
        assert o._mint_forensic_token(
            caller_id="x", audience="y", scope=(), ttl_seconds=60
        ) is None


# ---------------------------------------------------------------------------
# Real round-trip (PROJECT_ROOT redirected to tmp_path; no repo writes)
# ---------------------------------------------------------------------------


class TestMintForensicTokenRoundTrip:
    def test_real_mint_writes_audit_under_tmp(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod

        # Redirect PROJECT_ROOT so the token + audit files land under
        # tmp_path, never the repo data/ dir.
        monkeypatch.setattr(cfgmod, "PROJECT_ROOT", tmp_path)
        o = _bare_orchestrator()
        token = o._mint_forensic_token(
            caller_id="voice:gaming-engage",
            audience="ultron-llm",
            scope=("llm.preset.swap",),
            ttl_seconds=3600,
            extra_claims={"action": "gaming_engage"},
        )
        assert isinstance(token, str)
        assert token.count(".") == 2  # header.payload.signature
        # The mint audit log + trusted-caller registry land under tmp.
        identity_dir = tmp_path / "data" / "identity"
        assert (identity_dir / "short_lived_tokens.jsonl").exists()
        assert (identity_dir / "trusted_callers.jsonl").exists()

    def test_real_mint_verifies(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod
        from ultron.identity.short_lived_token import verify_token

        monkeypatch.setattr(cfgmod, "PROJECT_ROOT", tmp_path)
        o = _bare_orchestrator()
        token = o._mint_forensic_token(
            caller_id="mcp:tools",
            audience="ultron-mcp",
            scope=("mcp.tools.read",),
            ttl_seconds=3600,
        )
        assert token is not None
        # The minted token verifies against the auto-registered caller.
        claims = verify_token(
            token,
            project_root=tmp_path,
            expected_audience="ultron-mcp",
        )
        assert claims.caller_id == "mcp:tools"
        assert "mcp.tools.read" in claims.scope
