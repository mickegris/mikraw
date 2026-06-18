# mikraw

A generic command-line **RAW → JPEG** converter that applies a fixed, opinionated
"develop" look, built for fast batch conversion. It works with any RAW format
[LibRaw](https://www.libraw.org/) supports (via
[rawpy](https://github.com/letmaik/rawpy)); it is developed and tuned using
**Panasonic Lumix (`.RW2`)** files.

## The look (hardcoded)

- **White balance:** as shot in camera (read from the RAW).
- **Exposure:** a default **+0.7 EV** baseline lift (matching Darktable's
  scene-referred default, which compensates for the tone curve cameras bake into
  their previews). Pass `--autoexp` to instead meter the image and auto-correct
  exposure (center-weighted, with a highlight cap so a bright face never blows).
  Brightening is routed through a two-decode blend so the lift can't clip
  highlights.
- **Color:** vibrant, reasonably high saturation (vibrance-style, so already-
  saturated areas don't posterize), with **skin-tone protection** so faces stay
  natural rather than going orange.
- **Tone/contrast:** a filmic curve — gentle shadow lift, midtone S-curve, and a
  smooth highlight shoulder that rolls off to white instead of clipping.
- **Local contrast ("clarity"):** a multi-scale luminance boost that adds
  micro-contrast and depth (halo-suppressed), approximating a tone-equalizer.

You can nudge the baked-in look per run with `--saturation` / `--contrast` /
`--clarity` multipliers (`1.0` = default look, `0.0` = neutral).

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
| `--autoexp` | analyze + auto-adjust exposure |
| `-r, --recursive` | recurse into subdirectories |
| `-j, --jobs N` | parallel workers (default: CPU count) |
| `--overwrite` | overwrite existing JPEGs (default: skip) |
| `--suffix TEXT` | text added before `.jpg` |
| `--saturation F` / `--contrast F` / `--clarity F` | scale the baked-in look |
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
