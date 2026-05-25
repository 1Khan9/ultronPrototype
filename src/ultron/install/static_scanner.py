"""Install-time Python static-analysis scanner (T5).

T5 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Pre-install
content scan for Python skill / plugin / config files. The OpenClaw
TS scanner walks JS / TS source via a hand-rolled comment stripper;
the Python equivalent uses :mod:`tokenize` stdlib + targeted regex
to detect:

* :class:`LineFindingKind.DANGEROUS_EXEC` (critical) — calls to
  ``subprocess.run / .Popen / .call / .check_output`` AND
  ``os.system / os.popen / pty.spawn`` in files that import
  ``subprocess`` or ``os``.
* :class:`LineFindingKind.DYNAMIC_CODE_EXECUTION` (critical) — ``eval``,
  ``exec``, ``compile``, ``__import__`` of dynamic strings.
* :class:`LineFindingKind.CRYPTO_MINING` (critical) — ``stratum+tcp``,
  ``coinhive``, ``xmrig``, ``cpuminer``, ``ethminer`` substrings.
* :class:`LineFindingKind.SUSPICIOUS_NETWORK` (warn) — WebSocket /
  raw-socket connections to non-standard ports (excludes
  80/443/8080/8443/3000/3306/5432/6379/27017).
* :class:`SourceFindingKind.POTENTIAL_EXFILTRATION` (warn) — file
  read primitives + outbound HTTP / socket in the same source file.
* :class:`SourceFindingKind.OBFUSCATED_CODE` (warn) — long hex-escape
  sequences (``\\xNN\\xNN...``); large base64 strings passed to
  ``base64.b64decode``.
* :class:`SourceFindingKind.ENV_HARVESTING` (critical) — ``os.environ``
  access within 8 lines of a ``requests.post`` / ``http.client`` /
  ``urllib.request.urlopen`` call.

Hard caps mirror the TS scanner: 500 files per install, 1 MB per
file. The scanner's findings list is the input to the gating decision:
any critical finding blocks install unless an explicit
``--force-unsafe-install`` override is passed (logged loudly).

Source comments are stripped via :func:`tokenize.tokenize` (token-aware,
so strings containing ``#`` are preserved). Detection runs on the
de-commented source.

Gating: this is the input to Category L (rules L1-L8) which encodes
the per-finding allow/deny policy. The scanner is pure analysis; the
gating decision lives in :mod:`ultron.safety.rules.category_l`.
"""

from __future__ import annotations

import io
import logging
import re
import tokenize
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

LOGGER = logging.getLogger(__name__)

#: Max files inspected per install. Mirrors OpenClaw.
DEFAULT_MAX_FILES: int = 500

#: Max bytes per file. Files larger are skipped with a finding.
DEFAULT_MAX_FILE_BYTES: int = 1 * 1024 * 1024

#: Default Python source extensions scanned.
DEFAULT_PYTHON_SUFFIXES: tuple[str, ...] = (".py", ".pyi")


class FindingSeverity(str, Enum):
    """Severity tier for a finding."""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class LineFindingKind(str, Enum):
    """Per-line finding kinds."""

    DANGEROUS_EXEC = "dangerous_exec"
    DYNAMIC_CODE_EXECUTION = "dynamic_code_execution"
    CRYPTO_MINING = "crypto_mining"
    SUSPICIOUS_NETWORK = "suspicious_network"


class SourceFindingKind(str, Enum):
    """Per-source (whole-file) finding kinds."""

    POTENTIAL_EXFILTRATION = "potential_exfiltration"
    OBFUSCATED_CODE = "obfuscated_code"
    ENV_HARVESTING = "env_harvesting"
    FILE_TOO_LARGE = "file_too_large"
    DECODE_ERROR = "decode_error"


@dataclass(frozen=True)
class Finding:
    """One scanner finding."""

    path: str
    severity: FindingSeverity
    kind: str
    line: int = 0
    snippet: str = ""
    detail: str = ""


@dataclass(frozen=True)
class ScanReport:
    """Aggregated outcome of one install scan."""

    files_scanned: int = 0
    files_skipped: int = 0
    findings: tuple[Finding, ...] = ()

    @property
    def has_critical(self) -> bool:
        return any(f.severity == FindingSeverity.CRITICAL for f in self.findings)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARN)


def canonical_code_for_finding(finding: "Finding") -> Optional[str]:
    """Return the canonical T3 reason code for ``finding`` (or None).

    Lazy-imports :mod:`ultron.install.reason_codes` so the static
    scanner stays usable without the reason-code catalogue (the
    catalogue depends on ``FindingSeverity`` from this module; the
    helper closes the loop without re-introducing a cycle).

    Returns ``None`` for finding kinds not in
    :data:`ultron.install.reason_codes.KIND_TO_CODE` — callers that
    require strict mapping should raise on ``None`` themselves.
    """
    from ultron.install.reason_codes import code_for_kind

    return code_for_kind(finding.kind)


def canonical_codes_for_report(report: "ScanReport") -> tuple[str, ...]:
    """Return all canonical reason codes referenced by ``report.findings``.

    Result is deduplicated + alphabetically sorted via the
    :mod:`ultron.install.reason_codes` ``normalize_reason_codes``
    helper, so consumers get a stable per-report code list suitable
    for audit-log enrichment.

    Findings whose ``kind`` is not in the catalogue are silently
    skipped (the underlying Finding is preserved; only the canonical
    code mapping is absent).
    """
    from ultron.install.reason_codes import normalize_reason_codes

    raw: list[str] = []
    for f in report.findings:
        code = canonical_code_for_finding(f)
        if code is not None:
            raw.append(code)
    return normalize_reason_codes(raw)


# ----------------------------------------------------------------------
# Pattern catalogue

#: Whitelist of "standard" ports the suspicious-network rule allows.
_STANDARD_PORTS: frozenset[int] = frozenset({
    21, 22, 25, 53, 80, 110, 143, 443, 465, 587, 993, 995,
    3000, 3306, 5432, 6379, 8000, 8080, 8443, 9000, 27017,
})

_DANGEROUS_EXEC_RE = re.compile(
    r"\b(?:subprocess\.(?:Popen|run|call|check_call|check_output)|"
    r"os\.(?:system|popen|exec[lv]p?e?|spawn[lv]p?e?)|"
    r"pty\.spawn|shutil\.copyfileobj)\s*\(",
)

_DYNAMIC_CODE_RE = re.compile(
    r"\b(?:eval|exec|compile|__import__)\s*\(",
)

_CRYPTO_MINING_KEYWORDS: tuple[str, ...] = (
    "stratum+tcp",
    "coinhive",
    "xmrig",
    "cpuminer",
    "ethminer",
    "minerd",
    "minergate",
)

_SUSPICIOUS_NETWORK_RE = re.compile(
    r"\b(?:websocket|ws|wss|socket\.socket|aiohttp\.ClientSession|"
    r"http\.client\.HTTPConnection)\b.*?[:\s]([0-9]{2,5})",
    re.DOTALL,
)

_HEX_ESCAPE_SEQ_RE = re.compile(r"(?:\\x[0-9A-Fa-f]{2}){8,}")

_BASE64_DECODE_RE = re.compile(
    r"(?:base64\.b64decode|codecs\.decode\(.*?,\s*['\"]base64['\"]\)).*?['\"]([A-Za-z0-9+/=]{40,})['\"]",
    re.DOTALL,
)

_FILE_READ_PRIMS: tuple[str, ...] = (
    "open(",
    "pathlib.Path",
    "shutil.copy",
    "shutil.move",
    "io.open(",
    "os.read(",
)

_NETWORK_PRIMS: tuple[str, ...] = (
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.get",
    "urllib.request.urlopen",
    "urllib.urlopen",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
    "socket.create_connection",
    "aiohttp.ClientSession",
)

_ENV_ACCESS_RE = re.compile(r"\bos\.(?:environ|getenv)\b")
_NETWORK_CALL_RE = re.compile(
    r"\b(?:requests\.(?:get|post|put|patch|delete)|"
    r"urllib\.request\.urlopen|http\.client\.HTTPS?Connection|"
    r"socket\.create_connection|aiohttp\.ClientSession)\b",
)


def _strip_comments(source: str) -> str:
    """Return ``source`` with comments removed (string literals preserved).

    Uses :func:`tokenize.tokenize` for token-aware stripping; falls
    back to the raw source on tokenize errors (better to over-scan
    than miss a finding).
    """
    try:
        tokens = list(tokenize.tokenize(io.BytesIO(source.encode("utf-8")).readline))
    except (tokenize.TokenizeError, IndentationError, ValueError):
        return source
    keep: list[str] = []
    last_end_row, last_end_col = 1, 0
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.ENCODING:
            continue
        if tok.string == "" and tok.type in (tokenize.NEWLINE, tokenize.NL):
            keep.append("\n")
            continue
        keep.append(tok.string)
        if tok.type in (tokenize.NEWLINE, tokenize.NL):
            keep.append("\n")
    return "".join(keep)


def _read_source(path: Path, *, max_bytes: int) -> tuple[Optional[str], Optional[Finding]]:
    """Read + decode + strip comments. Returns (source, error_finding)."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, Finding(
            path=str(path),
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.DECODE_ERROR.value,
            detail=f"stat failed: {exc}",
        )
    if size > max_bytes:
        return None, Finding(
            path=str(path),
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.FILE_TOO_LARGE.value,
            detail=f"file size {size} exceeds {max_bytes}",
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, Finding(
            path=str(path),
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.DECODE_ERROR.value,
            detail="non-UTF-8 source",
        )
    except OSError as exc:
        return None, Finding(
            path=str(path),
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.DECODE_ERROR.value,
            detail=f"read failed: {exc}",
        )
    return _strip_comments(raw), None


def _scan_line_rules(path: str, source: str) -> list[Finding]:
    """Run per-line rules. Returns the list of findings."""
    findings: list[Finding] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if _DANGEROUS_EXEC_RE.search(line):
            findings.append(Finding(
                path=path,
                severity=FindingSeverity.CRITICAL,
                kind=LineFindingKind.DANGEROUS_EXEC.value,
                line=lineno,
                snippet=line.strip()[:200],
                detail="subprocess / os.system / pty.spawn call",
            ))
        if _DYNAMIC_CODE_RE.search(line):
            findings.append(Finding(
                path=path,
                severity=FindingSeverity.CRITICAL,
                kind=LineFindingKind.DYNAMIC_CODE_EXECUTION.value,
                line=lineno,
                snippet=line.strip()[:200],
                detail="eval / exec / compile / __import__ on dynamic source",
            ))
        lower = line.lower()
        for keyword in _CRYPTO_MINING_KEYWORDS:
            if keyword in lower:
                findings.append(Finding(
                    path=path,
                    severity=FindingSeverity.CRITICAL,
                    kind=LineFindingKind.CRYPTO_MINING.value,
                    line=lineno,
                    snippet=line.strip()[:200],
                    detail=f"crypto-mining keyword: {keyword}",
                ))
                break
        net_match = _SUSPICIOUS_NETWORK_RE.search(line)
        if net_match:
            try:
                port = int(net_match.group(1))
            except (TypeError, ValueError):
                port = -1
            if port > 0 and port not in _STANDARD_PORTS:
                findings.append(Finding(
                    path=path,
                    severity=FindingSeverity.WARN,
                    kind=LineFindingKind.SUSPICIOUS_NETWORK.value,
                    line=lineno,
                    snippet=line.strip()[:200],
                    detail=f"WebSocket / raw socket to non-standard port {port}",
                ))
    return findings


def _scan_source_rules(path: str, source: str) -> list[Finding]:
    """Run whole-source rules."""
    findings: list[Finding] = []
    # Potential exfiltration: file-read primitive + network call same file.
    has_file_read = any(prim in source for prim in _FILE_READ_PRIMS)
    has_network = any(prim in source for prim in _NETWORK_PRIMS)
    if has_file_read and has_network:
        findings.append(Finding(
            path=path,
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.POTENTIAL_EXFILTRATION.value,
            detail="file-read primitive + outbound network call coexist",
        ))
    # Obfuscated code: long hex-escape sequences.
    if _HEX_ESCAPE_SEQ_RE.search(source):
        findings.append(Finding(
            path=path,
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.OBFUSCATED_CODE.value,
            detail="long \\xNN hex-escape sequence",
        ))
    if _BASE64_DECODE_RE.search(source):
        findings.append(Finding(
            path=path,
            severity=FindingSeverity.WARN,
            kind=SourceFindingKind.OBFUSCATED_CODE.value,
            detail="base64.b64decode of large string literal",
        ))
    # Env harvesting: os.environ within 8 lines of a network call.
    lines = source.splitlines()
    env_lines = [i for i, ln in enumerate(lines) if _ENV_ACCESS_RE.search(ln)]
    net_lines = [i for i, ln in enumerate(lines) if _NETWORK_CALL_RE.search(ln)]
    flagged = False
    for env_i in env_lines:
        for net_i in net_lines:
            if abs(env_i - net_i) <= 8:
                flagged = True
                break
        if flagged:
            break
    if flagged:
        findings.append(Finding(
            path=path,
            severity=FindingSeverity.CRITICAL,
            kind=SourceFindingKind.ENV_HARVESTING.value,
            detail="os.environ access within 8 lines of outbound network call",
        ))
    return findings


def scan_python_text(path: str, source: str) -> list[Finding]:
    """Run every rule against ``source`` (comments stripped first)."""
    stripped = _strip_comments(source)
    findings: list[Finding] = []
    findings.extend(_scan_line_rules(path, stripped))
    findings.extend(_scan_source_rules(path, stripped))
    return findings


def scan_install_directory(
    install_root: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    suffixes: tuple[str, ...] = DEFAULT_PYTHON_SUFFIXES,
    skip_directories: Iterable[str] = (".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"),
) -> ScanReport:
    """Walk ``install_root`` for Python files; produce a scan report.

    Args:
        install_root: directory to scan.
        max_files: cap on files inspected (excess files counted as skipped).
        max_file_bytes: cap on per-file size (oversized files surface as
            FILE_TOO_LARGE finding instead of being inspected).
        suffixes: file extensions inspected.
        skip_directories: directory names skipped during the walk.

    Returns:
        :class:`ScanReport`.
    """
    if not install_root.exists() or not install_root.is_dir():
        return ScanReport()
    skip = set(skip_directories)
    files_scanned = 0
    files_skipped = 0
    findings: list[Finding] = []
    for path in sorted(install_root.rglob("*")):
        if path.is_dir():
            continue
        # Skip directories in skip-set.
        if any(part in skip for part in path.parts):
            continue
        if path.suffix not in suffixes:
            continue
        if files_scanned >= max_files:
            files_skipped += 1
            continue
        source, err = _read_source(path, max_bytes=max_file_bytes)
        if err is not None:
            findings.append(err)
            files_skipped += 1
            continue
        files_scanned += 1
        findings.extend(scan_python_text(str(path), source))
    return ScanReport(
        files_scanned=files_scanned,
        files_skipped=files_skipped,
        findings=tuple(findings),
    )


# ----------------------------------------------------------------------
# Dependency denylist (T5 companion)


#: Default denylist of package names known to be malicious / dangerous
#: when installed without scrutiny. Conservative starter set; operators
#: extend via :func:`scan_dependencies`.
DEFAULT_DENYLISTED_PACKAGES: frozenset[str] = frozenset({
    "colorama" + "x",  # known typosquat
    "crossenv",  # historical compromise
    "djangosearch",  # known typosquat
    "easyinstall",  # known typosquat
    "expressjs",  # known typosquat
    "jdb-bigquery",  # known typosquat
    "matplotlib3d",  # known typosquat
    "nim-lang",  # known typosquat
    "openpyxl3",  # known typosquat
    "pytestrunner",  # known typosquat
    "torchwheel",  # known typosquat
    "urllib2",  # typosquat for urllib3
    "request-lib",  # typosquat for requests
    "xmrig",
    "coinhive",
    "minerd",
})


@dataclass(frozen=True)
class DependencyFinding:
    """One denylist hit."""

    package: str
    source_file: str
    reason: str = "denylisted package"


def scan_dependencies(
    manifest_paths: Iterable[Path],
    *,
    extra_denylist: Iterable[str] = (),
) -> tuple[DependencyFinding, ...]:
    """Scan ``requirements.txt`` / ``pyproject.toml`` for denylisted packages.

    Args:
        manifest_paths: paths to dependency manifest files.
        extra_denylist: additional package names to deny beyond the defaults.

    Returns:
        Tuple of :class:`DependencyFinding` entries (one per hit).
    """
    deny = set(DEFAULT_DENYLISTED_PACKAGES) | set(name.lower() for name in extra_denylist)
    findings: list[DependencyFinding] = []
    for path in manifest_paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Coarse line-by-line scan looking for package names (handles
        # both requirements.txt and pyproject.toml dependency arrays).
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Extract a likely package-name token.
            token = re.split(r"[<>=!~\s\"'\[]", stripped, maxsplit=1)[0].strip()
            token = token.lstrip("-")  # handle requirements.txt "-r" lines
            if not token:
                continue
            if token.lower() in deny:
                findings.append(DependencyFinding(
                    package=token,
                    source_file=str(path),
                ))
    return tuple(findings)


__all__ = [
    "DEFAULT_DENYLISTED_PACKAGES",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_PYTHON_SUFFIXES",
    "DependencyFinding",
    "Finding",
    "FindingSeverity",
    "LineFindingKind",
    "ScanReport",
    "SourceFindingKind",
    "scan_dependencies",
    "scan_install_directory",
    "scan_python_text",
]
