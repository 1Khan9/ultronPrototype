"""Process-level single-instance guard for ``python -m kenning``.

Two simultaneous Kenning processes both grab the microphone and
double-respond to every utterance; the second also collides on the
embedded Qdrant lock (degrading silently to memory-disabled) and on
the MCP server's port 19761 bind. This module provides a held-open
OS-level file lock acquired by the console entrypoint BEFORE the
Orchestrator (and therefore any model or audio device) is constructed,
so a duplicate launch refuses immediately with a clear message.

Design:

* The lock is a **held byte-range lock** (``msvcrt.locking`` on
  Windows, ``fcntl.flock`` elsewhere) on a small metadata file. An OS
  lock auto-releases when the holding process dies, so there is no
  stale-lock recovery problem -- a crashed Kenning never blocks the
  next launch.
* The locked byte sits at offset :data:`_LOCK_BYTE_OFFSET` (4096),
  far past the JSON metadata at offset 0. On Windows ``msvcrt`` locks
  are *mandatory*, so locking byte 0 would make the metadata
  unreadable by the duplicate process that wants to report the
  holder's PID; locking a byte beyond EOF is legal and keeps offset 0
  readable.
* When neither locking primitive is importable the module degrades to
  a PID-liveness file (psutil probe; assume-dead on probe failure).
* **Fail-open everywhere**: only genuine lock CONTENTION refuses a
  start. A broken lock path, an unwritable directory, or any
  unexpected error logs a warning and returns a no-op "bypass" lock
  so a legitimate launch is never blocked by the guard itself.
* Escape hatch: ``KENNING_ALLOW_MULTIPLE_INSTANCES=1`` bypasses the
  guard entirely (returns a "bypass" lock).

The guard is owned by ``kenning.__main__`` ONLY. ``Orchestrator`` is
deliberately untouched so pytest sweeps, the GPU e2e suite, and
measurement scripts that construct it directly never contend.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kenning.lifecycle.single_instance")

__all__ = [
    "ALLOW_MULTIPLE_ENV",
    "DEFAULT_LOCK_PATH",
    "InstanceLock",
    "acquire_single_instance_lock",
    "is_another_instance_running",
    "read_lock_metadata",
]

# Monkeypatch seams: tests force the pidfile fallback by setting both
# to None. Import failures (non-Windows / non-POSIX) degrade the same
# way at runtime.
try:  # pragma: no cover - platform-dependent import
    import msvcrt as _msvcrt  # type: ignore[import]
except ImportError:  # pragma: no cover
    _msvcrt = None  # type: ignore[assignment]
try:  # pragma: no cover - platform-dependent import
    import fcntl as _fcntl  # type: ignore[import]
except ImportError:  # pragma: no cover
    _fcntl = None  # type: ignore[assignment]


ALLOW_MULTIPLE_ENV = "KENNING_ALLOW_MULTIPLE_INSTANCES"

#: Byte offset of the 1-byte held lock region. Must stay beyond the
#: metadata JSON at offset 0 (Windows msvcrt locks are mandatory --
#: a lock over the metadata bytes would break the duplicate's
#: diagnostic read of the holder PID).
_LOCK_BYTE_OFFSET = 4096

#: O_BINARY on Windows (prevents the CRT's text-mode LF -> CRLF
#: translation on the metadata write); 0 elsewhere.
_O_BINARY = getattr(os, "O_BINARY", 0)


def _default_lock_path() -> Path:
    """Resolve the default lock-file location.

    Anchors at ``PROJECT_ROOT/data`` (stable regardless of the launch
    CWD -- the mic / Qdrant store / MCP port are per-install
    resources, so the guard should be too). Falls back to a
    CWD-relative ``data/`` if the config package cannot be imported.
    """
    try:
        from kenning.config import PROJECT_ROOT

        return Path(PROJECT_ROOT) / "data" / ".kenning_instance.lock"
    except Exception:  # noqa: BLE001 - fail-open to the CWD convention
        return Path("data") / ".kenning_instance.lock"


DEFAULT_LOCK_PATH = _default_lock_path()


class InstanceLock:
    """A held single-instance lock. Release via :meth:`release`.

    Attributes:
        path: the lock-file path.
        mode: how the lock is held -- ``"msvcrt"`` / ``"fcntl"`` /
            ``"pidfile"`` / ``"bypass"`` (env escape hatch or
            fail-open degradation; holds nothing).
        pid: the acquiring process id.
    """

    def __init__(
        self,
        path: Path,
        mode: str,
        pid: int,
        fd: Optional[int] = None,
    ) -> None:
        self.path = Path(path)
        self.mode = mode
        self.pid = int(pid)
        self._fd = fd
        self._released = False

    def release(self) -> None:
        """Release the held lock. Idempotent; never raises."""
        if self._released:
            return
        self._released = True
        fd = self._fd
        self._fd = None
        if fd is None:
            return
        try:
            if self.mode == "msvcrt" and _msvcrt is not None:
                try:
                    os.lseek(fd, _LOCK_BYTE_OFFSET, os.SEEK_SET)
                    _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            elif self.mode == "fcntl" and _fcntl is not None:
                try:
                    _fcntl.flock(fd, _fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            # Deliberately NO unlink: on POSIX, removing the path
            # after LOCK_UN opens a lock-after-unlink race where a
            # process holding the old inode's lock and a process
            # locking a re-created file BOTH believe they are the
            # single instance. The OS lock byte (not the file's
            # existence) is the guard; the ~80-byte metadata file
            # stays behind in gitignored data/ and is overwritten on
            # the next successful acquire.


def _write_metadata(fd: int) -> None:
    """Write holder diagnostics (pid + start time) at offset 0."""
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    ) + "\n"
    os.lseek(fd, 0, os.SEEK_SET)
    # Truncating below the locked offset-4096 byte is legal: region
    # locks beyond EOF persist independently of file length.
    os.ftruncate(fd, 0)
    os.write(fd, payload.encode("utf-8"))


def read_lock_metadata(path: Optional[Path] = None) -> Optional[dict]:
    """Read the holder metadata from ``path``.

    Returns the parsed dict (``{"pid": ..., "started_at": ...}``) or
    None on ANY failure (missing file, locked-region read error,
    corrupt JSON). Diagnostics-only; never raises.

    Uses an UNBUFFERED ``os.read`` of at most 1024 bytes: Python's
    buffered ``open()`` would request a full 8 KiB buffer, which spans
    the mandatory-locked byte at offset 4096 on Windows and fails the
    whole read with EACCES while the holder is alive.
    """
    target = Path(path) if path is not None else DEFAULT_LOCK_PATH
    try:
        fd = os.open(str(target), os.O_RDONLY | _O_BINARY)
        try:
            head = os.read(fd, 1024)
        finally:
            os.close(fd)
        first_line = head.split(b"\n", 1)[0]
        meta = json.loads(first_line.decode("utf-8"))
        return meta if isinstance(meta, dict) else None
    except Exception:  # noqa: BLE001 - diagnostics only
        return None


def _pid_is_running(pid: int) -> bool:
    """Best-effort liveness probe for the pidfile fallback.

    psutil missing or any probe error returns False (assume dead =>
    fail-open: a stale pidfile never blocks a legitimate start).
    """
    try:
        import psutil

        return bool(psutil.pid_exists(int(pid)))
    except Exception:  # noqa: BLE001
        return False


#: errno values that mean "another process holds the lock" (refuse).
#: Anything else from the lock primitive is an environment problem
#: (e.g. ENOLCK: kernel lock table exhausted / lockless filesystem)
#: and must FAIL OPEN per the module contract.
_CONTENTION_ERRNOS = frozenset(
    e for e in (
        getattr(__import__("errno"), name, None)
        for name in ("EACCES", "EAGAIN", "EWOULDBLOCK", "EDEADLK", "EDEADLOCK")
    ) if e is not None
)


def _is_contention(e: OSError) -> bool:
    """True iff ``e`` from the lock primitive means genuine contention."""
    return e.errno in _CONTENTION_ERRNOS


def acquire_single_instance_lock(
    path: Optional[Path] = None,
) -> Optional[InstanceLock]:
    """Try to acquire the single-instance lock.

    Returns an :class:`InstanceLock` on success (or in the bypass /
    fail-open cases). Returns ``None`` ONLY on genuine contention --
    another live process holds the lock.
    """
    target = Path(path) if path is not None else DEFAULT_LOCK_PATH

    if os.environ.get(ALLOW_MULTIPLE_ENV) == "1":
        logger.info(
            "%s=1 set; skipping the single-instance guard.",
            ALLOW_MULTIPLE_ENV,
        )
        return InstanceLock(target, "bypass", os.getpid())

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_RDWR | os.O_CREAT | _O_BINARY, 0o644)

        if _msvcrt is not None:
            os.lseek(fd, _LOCK_BYTE_OFFSET, os.SEEK_SET)
            try:
                _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
            except OSError as e:
                os.close(fd)
                if _is_contention(e):
                    # LK_NBLCK contention raises immediately --
                    # another live process holds the byte.
                    return None
                # Non-contention lock failure (exotic filesystem /
                # environment): refuse-only-on-contention means we
                # fail OPEN here, not block every launch.
                logger.warning(
                    "single-instance lock primitive failed (%s); "
                    "continuing without the guard.", e,
                )
                return InstanceLock(target, "bypass", os.getpid())
            try:
                _write_metadata(fd)
            except Exception as e:  # noqa: BLE001 - diagnostics only
                logger.debug("instance-lock metadata write failed: %s", e)
            return InstanceLock(target, "msvcrt", os.getpid(), fd=fd)

        if _fcntl is not None:
            try:
                _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            except OSError as e:
                os.close(fd)
                if _is_contention(e):
                    return None
                # e.g. ENOLCK (lock table exhausted / NFS without
                # lockd): environment problem, not a duplicate.
                logger.warning(
                    "single-instance lock primitive failed (%s); "
                    "continuing without the guard.", e,
                )
                return InstanceLock(target, "bypass", os.getpid())
            try:
                _write_metadata(fd)
            except Exception as e:  # noqa: BLE001
                logger.debug("instance-lock metadata write failed: %s", e)
            return InstanceLock(target, "fcntl", os.getpid(), fd=fd)

        # Neither locking primitive available: PID-liveness fallback.
        # NOTE: this degraded path is check-then-write without
        # atomicity -- two truly simultaneous launches can both pass.
        # It is essentially unreachable on supported platforms (one of
        # msvcrt/fcntl always imports); accepted for the exotic case.
        meta = read_lock_metadata(target)
        other = meta.get("pid") if isinstance(meta, dict) else None
        if (
            isinstance(other, int)
            and other != os.getpid()
            and _pid_is_running(other)
        ):
            os.close(fd)
            return None
        try:
            _write_metadata(fd)
        except Exception as e:  # noqa: BLE001
            logger.debug("instance-lock metadata write failed: %s", e)
        return InstanceLock(target, "pidfile", os.getpid(), fd=fd)
    except Exception as e:  # noqa: BLE001
        # FAIL-OPEN: a broken lock path must never block a legitimate
        # start. Only contention (handled above) returns None.
        logger.warning(
            "single-instance guard unavailable (%s); continuing without it.",
            e,
        )
        return InstanceLock(target, "bypass", os.getpid())


def is_another_instance_running(
    path: Optional[Path] = None,
) -> Optional[int]:
    """Probe whether another instance currently holds the lock.

    Returns the holder's PID (or ``None`` when no other instance is
    detected). The probe itself never leaves the lock held.

    CAVEAT: the probe works by briefly ACQUIRING the lock, so it must
    not run concurrently with a real launch -- a launch racing the
    probe instant would falsely refuse. Diagnostics / test use only.
    """
    if os.environ.get(ALLOW_MULTIPLE_ENV) == "1":
        return None
    probe = acquire_single_instance_lock(path)
    if probe is not None:
        probe.release()
        return None
    target = Path(path) if path is not None else DEFAULT_LOCK_PATH
    meta = read_lock_metadata(target) or {}
    pid = meta.get("pid")
    return int(pid) if isinstance(pid, int) else None
