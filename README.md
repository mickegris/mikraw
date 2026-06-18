# mikraw

Bulk-convert camera **RAW** files to **JPEG** with a fixed, opinionated "develop"
look. Built for fast batch conversion with good **Panasonic Lumix S-series
(`.RW2`)** support, powered by [LibRaw](https://www.libraw.org/) via
[rawpy](https://github.com/letmaik/rawpy).

## The look (hardcoded)

- **White balance:** as shot in camera (read from the RAW).
- **Exposure:** straight from the RAW. Pass `--autoexp` to analyze the image and
  auto-correct exposure (brighten/darken toward a good midtone without clipping
  highlights).
- **Color:** vibrant, reasonably high saturation (vibrance-style, so already-
  saturated areas don't posterize).
- **Tone/contrast:** a gentle, non-clipping S-curve for a clean, punchy baseline.

You can nudge the baked-in look per run with `--saturation` / `--contrast`
multipliers (`1.0` = default look, `0.0` = neutral).

## Install

Requires Python 3.10+.

```bash
pip install -e .            # core (rawpy, numpy, Pillow, tqdm)
pip install -e ".[exif]"    # also copy EXIF metadata into the JPEGs (pyexiv2)
```

## Usage

```bash
# single file, quality 92, into ./out
mikraw -q 92 some.RW2 -o ./out

# bulk: a whole folder, recursive, 8 workers, with auto-exposure
mikraw -r -j 8 --autoexp "C:\photos\lumix" -o ./out

# globs work (mikraw expands them itself on Windows too)
mikraw "*.RW2"

# see what would happen, change nothing
mikraw --dry-run -r .
```

### Options

| Option | Meaning |
| --- | --- |
| `-q, --quality N` | JPEG quality percent (default 90) |
| `-o, --output DIR` | output directory (default: current dir) |
| `--autoexp` / `-autoexp` | analyze + auto-adjust exposure |
| `-r, --recursive` | recurse into subdirectories |
| `-j, --jobs N` | parallel workers (default: CPU count) |
| `--overwrite` | overwrite existing JPEGs (default: skip) |
| `--suffix TEXT` | text added before `.jpg` |
| `--saturation F` / `--contrast F` | scale the baked-in look |
| `--no-exif` | don't copy EXIF metadata |
| `--dry-run` | list planned conversions and exit |

Output files are named `<source-stem><suffix>.jpg`. EXIF (camera, lens, date,
ISO, exposure) is copied from the RAW and orientation is baked into the pixels.

## Notes on RW2

RW2 is proprietary and undocumented, so brand-new Lumix bodies released after the
bundled LibRaw version may need a `rawpy`/LibRaw upgrade. The established S-series
(S1 / S1R / S5 / S5II) decode well today.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests cover the look engine, auto-exposure heuristic, and CLI/discovery logic
(all I/O-free). The end-to-end RAW test runs only if rawpy and a fixture are
present.
