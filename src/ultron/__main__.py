"""Console entrypoint: ``python -m ultron``."""

from __future__ import annotations

import signal
import sys

from ultron.pipeline import Orchestrator
from ultron.utils.logging import configure_logging, get_logger


def _ensure_utf8_stdio() -> None:
    """Reconfigure stdout / stderr to UTF-8 with ``errors='replace'``.

    2026-05-19 fix: on Windows the default console encoding is cp1252
    which cannot encode many characters that show up in source titles
    / URLs (smart quotes, em-dashes, Unicode glyphs). A printed source
    list crashed the entire response pipeline with::

        UnicodeEncodeError: 'charmap' codec can't encode characters in
        position 160-161: character maps to <undefined>

    Forcing UTF-8 with ``errors='replace'`` makes every ``print()``
    call resilient: unencodable code points become ``?`` in the
    console instead of throwing. The audio pipeline is unaffected
    (TTS uses its own pipeline); only console output changes.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # Best-effort: a non-reconfigurable stream (rare; tests
            # sometimes wrap stdio) keeps its existing settings.
            pass


def main() -> int:
    _ensure_utf8_stdio()
    configure_logging()
    logger = get_logger("main")

    print("\n" + "=" * 60)
    print("  ULTRON")
    print("  Local voice-first AI assistant — prototype")
    print("=" * 60)
    print("  Loading models — this can take 1–3 minutes on first run.")

    try:
        orchestrator = Orchestrator()
    except FileNotFoundError as e:
        logger.error("Missing model: %s", e)
        print(f"\n[!] {e}")
        print("    Run: python scripts/download_models.py\n")
        return 2
    except Exception as e:
        logger.exception("Startup failed: %s", e)
        print(f"\n[!] Startup failed: {e}")
        return 1

    def _sigint(_sig, _frm):
        print("\n  shutting down…")
        orchestrator.shutdown()

    signal.signal(signal.SIGINT, _sigint)

    try:
        with orchestrator:
            orchestrator.run()
    except Exception as e:
        logger.exception("Run loop failed: %s", e)
        return 1

    print("  goodbye.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
