from __future__ import annotations

import argparse
import logging
from logging import Logger
from pathlib import Path

from rich.logging import RichHandler

from .config import Config
def _import_run():
    # Lazy import to avoid importing heavy deps just for --help
    from .runner import run  # type: ignore
    return run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="snapsort",
        description="Organize images into blurred/duplicate folders using pHash and blur detection.",
    )
    p.add_argument("--input-dir", required=True, help="Directory containing images to process")
    p.add_argument("--duplicate-threshold", type=int, default=5, help="Hamming distance threshold for near-duplicates")
    p.add_argument("--blur-threshold", type=float, default=100.0, help="Variance of Laplacian threshold for blur detection")
    p.add_argument("--blur-folder", type=str, default="blurred", help="Folder name for blurred images")
    p.add_argument("--partial-blur-folder", type=str, default="partialBlurred", help="Folder name for partially blurred images")
    p.add_argument("--slight-blur-folder", type=str, default="slightlyBlurred", help="Folder name for slightly blurred images")
    p.add_argument("--duplicate-folder", type=str, default="duplicate", help="Folder name for duplicate images")
    p.add_argument(
        "--extensions",
        type=str,
        default=".jpg,.jpeg,.nef",
        help="Comma-separated list of allowed file extensions (e.g., .jpg,.jpeg,.nef)",
    )
    p.add_argument("--recursive", action="store_true", help="Include subdirectories recursively")
    p.add_argument("--dry-run", action="store_true", help="Show planned moves but do not modify files")
    p.add_argument("--max-workers", type=int, default=None, help="Max workers for parallel analysis")
    p.add_argument("--log-level", type=str, default="INFO", help="Logging level: DEBUG/INFO/WARN/ERROR")
    p.add_argument("--output-dir", type=str, default=None, help="Base output directory (defaults to input dir)")
    p.add_argument("--keep-originals", action="store_true", help="Copy instead of move")
    p.add_argument("--blur-on", type=str, choices=["faces", "image"], default="faces", help="Blur classification target: 'faces' or full 'image'")
    p.add_argument("--partial-blur-min-percent", type=float, default=50.0, help="Minimum percent of blurred faces to classify as partially blurred (100%% => fully blurred)")
    p.add_argument("--face-cascade", type=str, default=None, help="Optional custom path to Haar cascade XML for face detection")
    # Reporting helpers
    p.add_argument("--print-scanned", action="store_true", help="Print files scanned successfully (grouped by extension)")
    p.add_argument("--print-ready", action="store_true", help="Print files planned to move/copy (grouped by extension)")
    p.add_argument("--print-format", type=str, choices=["text", "csv"], default="text", help="Output format for printed lists")
    p.add_argument("--print-metrics", action="store_true", help="Print per-file blur metrics and face counts")
    return p


def _setup_logging(level: str) -> Logger:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_time=False, show_level=True)],
    )
    logger = logging.getLogger("snapsort")
    logger.setLevel(lvl)
    # Reduce noise from very chatty libraries like Pillow's TIFF plugin
    try:
        logging.getLogger("PIL").setLevel(logging.WARNING)
        logging.getLogger("PIL.TiffImagePlugin").setLevel(logging.WARNING)
        logging.getLogger("PIL.Image").setLevel(logging.WARNING)
    except Exception:
        pass
    return logger


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cfg = Config.from_args(args)
    _setup_logging(cfg.log_level)
    run = _import_run()
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
