"""Input discovery and parallel batch execution."""

from __future__ import annotations

import glob
import logging
from dataclasses import dataclass
from pathlib import Path

from mikraw.errors import FileResult, Status
from mikraw.pipeline import Options, convert_one, output_path

log = logging.getLogger("mikraw")

# Common camera RAW extensions. RW2 (Panasonic Lumix) first since it's the focus.
RAW_EXTENSIONS = {
    ".rw2", ".raw", ".dng", ".arw", ".srf", ".sr2", ".cr2", ".cr3", ".crw",
    ".nef", ".nrw", ".orf", ".raf", ".rwl", ".pef", ".ptx", ".srw", ".x3f",
    ".3fr", ".mef", ".mos", ".iiq", ".kdc", ".dcr", ".erf", ".mrw",
}

_GLOB_CHARS = ("*", "?", "[")


def _is_raw(p: Path) -> bool:
    return p.suffix.lower() in RAW_EXTENSIONS


def discover(inputs: list[str], recursive: bool) -> list[str]:
    """Resolve files, directories and globs into a sorted, de-duplicated list."""
    found: list[str] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        key = str(p.resolve()).lower()
        if key not in seen:
            seen.add(key)
            found.append(str(p))

    for item in inputs:
        matches = (
            glob.glob(item, recursive=recursive)
            if any(c in item for c in _GLOB_CHARS)
            else [item]
        )
        if not matches:
            log.warning("no match: %s", item)
            continue
        for m in matches:
            p = Path(m)
            if p.is_dir():
                it = p.rglob("*") if recursive else p.glob("*")
                for f in sorted(it):
                    if f.is_file() and _is_raw(f):
                        add(f)
            elif p.is_file():
                if _is_raw(p):
                    add(p)
                else:
                    log.warning("not a recognized RAW file: %s", m)
            else:
                log.warning("no such file: %s", m)

    return sorted(found)


@dataclass
class Summary:
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[FileResult] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = []


def dry_run(files: list[str], opts: Options) -> None:
    for f in files:
        print(f"{f}  ->  {output_path(f, opts)}")
    print(f"\n{len(files)} file(s) would be converted.")


def run(files: list[str], opts: Options, jobs: int, quiet: bool = False) -> Summary:
    """Convert all files, optionally in parallel. Per-file failures are isolated."""
    summary = Summary()
    if not files:
        return summary

    try:
        from tqdm import tqdm
    except Exception:  # pragma: no cover
        tqdm = None

    jobs = max(1, jobs)

    def record(res: FileResult) -> None:
        summary.results.append(res)
        if res.status is Status.CONVERTED:
            summary.converted += 1
        elif res.status is Status.SKIPPED:
            summary.skipped += 1
        else:
            summary.failed += 1
            log.error("failed: %s (%s)", res.source, res.message)

    if jobs == 1 or len(files) == 1:
        it = files
        if tqdm and not quiet:
            it = tqdm(files, unit="img")
        for f in it:
            record(convert_one(f, opts))
        return summary

    # Parallel path. Pass (file, opts) tuples to a top-level worker so it pickles.
    import multiprocessing as mp

    args = [(f, opts) for f in files]
    with mp.Pool(processes=jobs) as pool:
        results_iter = pool.imap_unordered(_worker, args)
        if tqdm and not quiet:
            results_iter = tqdm(results_iter, total=len(files), unit="img")
        for res in results_iter:
            record(res)
    return summary


def _worker(arg: tuple[str, Options]) -> FileResult:
    src, opts = arg
    return convert_one(src, opts)
