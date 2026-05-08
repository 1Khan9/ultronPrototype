"""Validate ``config.yaml`` against the pydantic schema without starting Ultron.

Exits 0 if the config loads cleanly; non-zero with a clear error message
otherwise. Useful for CI / pre-commit + for confirming a hand-edit of
config.yaml didn't introduce a typo or a range violation.

Usage:
    python scripts/validate_config.py                 # validates ./config.yaml
    python scripts/validate_config.py path/to.yaml    # explicit file
    python scripts/validate_config.py --print         # print resolved config
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make ultron.* importable when this script is run from the worktree.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate config.yaml.")
    parser.add_argument(
        "path", nargs="?", type=Path, default=None,
        help="path to config.yaml (default: ./config.yaml or "
             "$ULTRON_CONFIG_PATH)",
    )
    parser.add_argument(
        "--print", dest="print_resolved", action="store_true",
        help="print the resolved configuration as JSON after validation",
    )
    args = parser.parse_args(argv)

    # Lazy imports so a config-only error doesn't pull in heavy deps.
    try:
        from ultron.config import load_config
        from ultron.errors import ConfigurationError
    except ImportError as e:
        print(f"failed to import ultron.config: {e}", file=sys.stderr)
        print("Run from the project root with the venv active.", file=sys.stderr)
        return 1

    try:
        cfg = load_config(args.path)
    except ConfigurationError as e:
        print("CONFIGURATION INVALID")
        print(f"  message: {e.message}")
        if e.context:
            for k, v in e.context.items():
                print(f"  {k}: {v}")
        return 1
    except Exception as e:
        # Unexpected error type — surface for debug.
        print(f"unexpected error type {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print("Configuration is valid.")
    if args.print_resolved:
        print()
        print(json.dumps(cfg.model_dump(mode="json"), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
