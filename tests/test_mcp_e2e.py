"""Phase 1 e2e: real AI coding agent subprocess connects to a real running
:class:`UltronMCPServer` over SSE and calls our tools.

This is the spec's "AI coding agent can connect to the worker-facing server
and call all four worker tools" criterion. Slow tier (PYTEST_RUN_GPU_TESTS=1)
because it spawns a real ``claude`` subprocess and burns haiku tokens.
"""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path
from typing import List

import pytest

os.environ.setdefault("ULTRON_CODING_MCP_ALLOW_ANY_ROOT", "1")

from ultron.coding.direct_bridge import DirectClaudeCodeBridge  # noqa: E402
from ultron.coding.bridge import TaskRequest  # noqa: E402
from ultron.coding.mcp_server import UltronMCPServer, write_mcp_config  # noqa: E402
from ultron.coding.session import SessionStatus  # noqa: E402


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
        reason="set PYTEST_RUN_GPU_TESTS=1 to run real AI coding agent e2e",
    ),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _bridge() -> DirectClaudeCodeBridge:
    try:
        return DirectClaudeCodeBridge()
    except FileNotFoundError as e:
        pytest.skip(str(e))


def test_real_claude_calls_report_progress_and_declare_complete(tmp_path: Path):
    """Spawn AI coding agent, hand it a prompt that explicitly directs it to
    call our MCP tools, and verify the session state reflects the calls.

    We tell Claude to call ``report_progress`` once and ``declare_complete``
    once, with a one-line file write in between. The test then asserts:
      * report_progress was received (current_stage populated)
      * declare_complete was received (completion_claim populated, status
        moved to VERIFYING)
      * the file Claude wrote actually exists at the project root
    """
    project = tmp_path / "p"
    project.mkdir()

    server = UltronMCPServer(
        host="127.0.0.1", port=_free_port(),
        log_path=tmp_path / "mcp_calls.jsonl",
    )
    session = server.create_session(
        project_root=project, initial_prompt="say hi via mcp",
    )
    server.store.transition(session.session_id, SessionStatus.EXECUTING)
    server.start(ready_timeout_s=5.0)

    try:
        write_mcp_config(project, sse_url=server.sse_url)
        bridge = _bridge()

        prompt = (
            "Use the ultron_coding MCP tools as follows. "
            "Step 1: call mcp__ultron_coding__report_progress with "
            "stage='scaffolding', summary='greeting file scaffolded', "
            "files_touched=['greeting.txt']. "
            "Step 2: write a single file `greeting.txt` containing the line "
            "'hi from claude' (use the Write tool). "
            "Step 3: call mcp__ultron_coding__report_test_results with "
            "passing=0, failing=0, skipped=0, details='no tests for this '"
            "single-file artifact'. "
            "Step 4: call mcp__ultron_coding__declare_complete with "
            "summary='single-file greeting written', entry_point=null, "
            "run_command=null, files_created=['greeting.txt'], "
            "files_modified=[]. "
            "Do not call any other tools. Do not write more than one file. "
            "Do not run a test framework."
        )

        request = TaskRequest(
            task_prompt=prompt,
            cwd=project,
            model="haiku",
            require_testing=False,
            timeout_s=180.0,
            label="mcp-e2e",
        )
        handle = bridge.submit(request)
        result = handle.wait(timeout=180.0)
        assert result.success, (
            f"claude exit={result.exit_status} error={result.error} "
            f"summary={result.summary[:300]!r}"
        )

        s = server.get_session_state(session.session_id)

        # Tool 1: report_progress
        assert s.current_stage == "scaffolding", (
            f"expected report_progress to land; current_stage={s.current_stage!r}"
        )
        assert any(
            "greeting.txt" == f.path for f in s.files_created
        ), f"files_created from report_progress missing greeting.txt: "\
           f"{[f.path for f in s.files_created]}"

        # Tool 2: report_test_results
        assert s.test_status.last_updated is not None, (
            "expected report_test_results to land in session state"
        )
        assert s.test_status.passing == 0
        assert s.test_status.failing == 0

        # Tool 3: declare_complete
        assert s.completion_claim is not None, (
            "expected declare_complete to record a completion claim"
        )
        assert "greeting" in s.completion_claim.summary.lower()
        assert s.status == SessionStatus.VERIFYING, (
            f"expected status=VERIFYING after declare_complete; got {s.status}"
        )

        # And the actual file Claude wrote exists.
        assert (project / "greeting.txt").is_file()

        # Audit log captured the calls.
        audit_lines = (tmp_path / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        tool_names: List[str] = []
        for line in audit_lines:
            if not line.strip():
                continue
            import json
            rec = json.loads(line)
            if rec.get("kind") == "claude_call":
                tool_names.append(rec.get("tool", ""))
        assert "report_progress" in tool_names
        assert "report_test_results" in tool_names
        assert "declare_complete" in tool_names
    finally:
        server.stop(timeout_s=5.0)
