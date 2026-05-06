"""Console entrypoint: ``python -m ultron``."""

from __future__ import annotations

import signal
import sys

from ultron.pipeline import Orchestrator
from ultron.utils.logging import configure_logging, get_logger


def main() -> int:
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
