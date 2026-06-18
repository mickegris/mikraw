"""Command-line interface for mikraw."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from mikraw import __version__
from mikraw import batch
from mikraw.pipeline import Options


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mikraw",
        description="Bulk-convert camera RAW files to JPEG with a fixed vibrant look "
        "(good Panasonic Lumix S-series support).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("inputs", nargs="+", metavar="INPUT",
                   help="RAW files, directories, or glob patterns")
    p.add_argument("-q", "--quality", type=int, default=90, metavar="1-100",
                   help="JPEG quality percent (default: 90)")
    p.add_argument("-o", "--output", default=".", metavar="DIR",
                   help="output directory (created if missing)")
    p.add_argument("--autoexp", "-autoexp", action="store_true",
                   help="analyze the image and auto-adjust exposure")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="recurse into subdirectories")
    p.add_argument("-j", "--jobs", type=int, default=0,
                   help="parallel workers (0 = CPU count)")
    p.add_argument("--overwrite", action="store_true",
                   help="overwrite existing JPEGs (default: skip)")
    p.add_argument("--suffix", default="",
                   help="suffix added before .jpg (e.g. _conv)")
    p.add_argument("--saturation", type=float, default=1.0,
                   help="multiplier over the baked-in saturation (0 = neutral)")
    p.add_argument("--contrast", type=float, default=1.0,
                   help="multiplier over the baked-in contrast (0 = neutral)")
    p.add_argument("--clarity", type=float, default=1.0,
                   help="multiplier over the baked-in local contrast (0 = neutral)")
    p.add_argument("--no-exif", action="store_true",
                   help="do not copy EXIF metadata into the JPEG")
    p.add_argument("--dry-run", action="store_true",
                   help="list what would be converted, then exit")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    p.add_argument("--quiet", action="store_true", help="suppress progress bar")
    p.add_argument("--version", action="version", version=f"mikraw {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if not (1 <= args.quality <= 100):
        print("error: --quality must be between 1 and 100", file=sys.stderr)
        return 2

    jobs = args.jobs if args.jobs > 0 else (os.cpu_count() or 1)

    opts = Options(
        output_dir=args.output,
        quality=args.quality,
        autoexp=args.autoexp,
        overwrite=args.overwrite,
        suffix=args.suffix,
        contrast=args.contrast,
        saturation=args.saturation,
        clarity=args.clarity,
        copy_exif=not args.no_exif,
    )

    files = batch.discover(args.inputs, args.recursive)
    if not files:
        print("No RAW files found.", file=sys.stderr)
        return 1

    if args.dry_run:
        batch.dry_run(files, opts)
        return 0

    summary = batch.run(files, opts, jobs=jobs, quiet=args.quiet)

    print(
        f"\n{summary.converted} converted, "
        f"{summary.skipped} skipped, "
        f"{summary.failed} failed."
    )
    return 1 if summary.failed and not summary.converted else 0


if __name__ == "__main__":
    raise SystemExit(main())
