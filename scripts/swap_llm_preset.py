"""Switch the active LLM preset by editing config.yaml in place.

A safer one-shot alternative to manually editing config.yaml: validates
that the target preset's GGUFs exist on disk, prints the diff, edits
the file (preserving comments via a regex over the ``preset:`` line),
re-validates the resulting config, and prints next steps.

Usage:
    python scripts/swap_llm_preset.py qwen3.5-4b
    python scripts/swap_llm_preset.py qwen3.5-9b
    python scripts/swap_llm_preset.py --list           # show presets + paths
    python scripts/swap_llm_preset.py --status         # show current preset

Note: the env var ``ULTRON_LLM_PRESET`` is an even faster path that
doesn't touch the file at all — set it in your shell before running
``python -m ultron``.

This script does NOT restart Ultron. After swapping, restart any
running ``python -m ultron`` and ``scripts/start_llamacpp_server.py``
processes to pick up the new model. Hot-swap inside a running process
is not supported (the GGUF is loaded into VRAM at startup).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Make ``ultron`` importable when running from any cwd.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE / "src") not in sys.path:
    sys.path.insert(0, str(_HERE / "src"))


def _config_path() -> Path:
    """Find config.yaml — env override or default location."""
    import os
    env = os.environ.get("ULTRON_CONFIG_PATH")
    if env:
        return Path(env)
    return _HERE / "config.yaml"


def _list_presets() -> int:
    from ultron.config import LLM_PRESETS
    print("Available presets (from src/ultron/config.py:LLM_PRESETS):\n")
    for name, fields in LLM_PRESETS.items():
        print(f"  {name}")
        for k, v in fields.items():
            print(f"      {k}: {v}")
    print("\n  custom")
    print("      (no auto-fill; specify model_path / draft_model_path / n_ctx by hand)")
    return 0


def _show_status() -> int:
    from ultron.config import get_config, current_config_path
    cfg = get_config()
    print(f"config: {current_config_path()}")
    print(f"preset: {cfg.llm.preset}")
    print(f"model_path: {cfg.llm.model_path}")
    print(f"draft_model_path: {cfg.llm.draft_model_path}")
    print(f"n_ctx: {cfg.llm.n_ctx}")
    return 0


def _validate_preset_files(preset: str) -> int:
    """Confirm the GGUFs the preset points at exist on disk."""
    from ultron.config import LLM_PRESETS, resolve_path
    if preset == "custom":
        print(
            f"preset 'custom': skipping path validation (you manage "
            f"model_path / draft_model_path / n_ctx by hand)."
        )
        return 0
    fields = LLM_PRESETS.get(preset)
    if fields is None:
        print(f"error: unknown preset {preset!r}", file=sys.stderr)
        return 2
    missing: list[Path] = []
    for key in ("model_path", "draft_model_path"):
        v = fields.get(key)
        if v is None:
            continue
        p = resolve_path(v)
        if not p.is_file():
            missing.append(p)
    if missing:
        print("error: preset files missing:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        print(
            "\nFix: run `python scripts/download_models.py` from the main "
            "checkout to fetch any missing GGUFs.",
            file=sys.stderr,
        )
        return 2
    return 0


_PRESET_RE = re.compile(r"^(\s*preset:\s*)\"([^\"]*)\"\s*(#.*)?$")


def _rewrite_preset(text: str, new_preset: str) -> tuple[str, str]:
    """Find and rewrite the ``preset: "..."`` line. Returns
    ``(new_text, old_preset_value)``. Raises ``ValueError`` if the
    line is missing."""
    out_lines: list[str] = []
    old_value: str | None = None
    rewritten = False
    for line in text.splitlines(keepends=True):
        m = _PRESET_RE.match(line.rstrip("\n").rstrip("\r"))
        if m and old_value is None:
            old_value = m.group(2)
            comment = m.group(3) or ""
            new_line = f'{m.group(1)}"{new_preset}"'
            if comment:
                new_line += f"  {comment}"
            new_line += "\n"
            out_lines.append(new_line)
            rewritten = True
        else:
            out_lines.append(line)
    if not rewritten or old_value is None:
        raise ValueError(
            "Could not find a 'preset: \"...\"' line in config.yaml. "
            "Either the file shape changed or the preset key is on a "
            "non-string scalar — edit the file by hand or restore from "
            "git history."
        )
    return "".join(out_lines), old_value


def _swap(preset: str, *, dry_run: bool) -> int:
    cfg_path = _config_path()
    if not cfg_path.is_file():
        print(f"error: {cfg_path} does not exist", file=sys.stderr)
        return 2

    rc = _validate_preset_files(preset)
    if rc != 0:
        return rc

    text = cfg_path.read_text(encoding="utf-8")
    try:
        new_text, old = _rewrite_preset(text, preset)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if old == preset:
        print(f"already on preset {preset!r}; no changes needed.")
        return 0

    print(f"swapping config preset: {old!r} -> {preset!r}")
    if dry_run:
        print("[dry-run] not writing.")
        return 0

    # Atomic write: write to .tmp, validate, then rename.
    tmp = cfg_path.with_suffix(".yaml.tmp")
    tmp.write_text(new_text, encoding="utf-8")
    # Re-validate the new file before committing the swap.
    from ultron.config import load_config
    try:
        load_config(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        print(f"error: new config failed validation: {e}", file=sys.stderr)
        return 2
    tmp.replace(cfg_path)

    print(f"  wrote {cfg_path}")
    print(
        f"\nNext: restart any running `python -m ultron` and "
        f"`scripts/start_llamacpp_server.py` processes to pick up "
        f"the new model. The swap does NOT hot-reload."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "preset", nargs="?",
        help="Target preset (qwen3.5-9b / qwen3.5-4b / custom). "
             "Required unless --list / --status.",
    )
    parser.add_argument("--list", action="store_true", help="List presets and exit.")
    parser.add_argument(
        "--status", action="store_true",
        help="Show the active preset (from config.yaml) and exit.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change but don't edit the file.",
    )
    args = parser.parse_args(argv)

    if args.list:
        return _list_presets()
    if args.status:
        return _show_status()
    if not args.preset:
        parser.print_help()
        return 2
    return _swap(args.preset, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
