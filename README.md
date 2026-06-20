# mikraw

A generic command-line **RAW → JPEG / TIFF** converter that applies a fixed,
opinionated "develop" look, built for fast batch conversion. It works with any RAW
format [LibRaw](https://www.libraw.org/) supports (via
[rawpy](https://github.com/letmaik/rawpy)); it is developed and tuned using
**Panasonic Lumix (`.RW2`)** files.

## The look

The look is applied via a **profile** (`--profile NAME`, default: `vibrant`):

| Profile | Description |
| --- | --- |
| `vibrant` | Filmic contrast, local clarity, and vibrant colors **(default)** |
| `neutral` | Minimal processing — faithful to the RAW decode |
| `camera` | Approximates what the camera's own JPEG engine would produce |
| `portrait` | Soft clarity, natural skin tones, gentle contrast — ideal for people |
| `monochrome` | Black and white with punchy contrast and high clarity |
| `landscape` | Maximum clarity and saturation for outdoor/nature shots |

Run `mikraw --list-profiles` for the full list with descriptions.

What `vibrant` does:
- **White balance:** as shot in camera.
- **Exposure:** auto-metered by default (center-weighted, 40th-percentile shadow
  target, 92nd-percentile highlight cap so bright faces never blow). Brightening
  uses a two-decode blend so highlights are always preserved. Pass `--no-autoexp`
  to switch to a fixed **+0.7 EV** baseline lift instead.
- **Color:** vibrance-style saturation boost with **skin-tone protection** so faces
  stay natural rather than going orange.
- **Tone/contrast:** a filmic curve — shadow lift, midtone S-curve, and a smooth
  highlight shoulder.
- **Local contrast ("clarity"):** multi-scale luminance boost for micro-contrast
  and depth (halo-suppressed).

The `--contrast` / `--saturation` / `--clarity` flags override the profile's
values when provided (`1.0` = profile default, `0.0` = that stage off).

## Install

Requires Python 3.10+.

```bash
pip install -e .            # core (rawpy, numpy, Pillow, tqdm)
pip install -e ".[exif]"    # + copy EXIF metadata into the output (pyexiv2)
pip install -e ".[tiff]"    # + 16-bit TIFF output (tifffile)
pip install -e ".[gpu]"     # + OpenCL GPU acceleration (pyopencl)
pip install -e ".[dev]"     # all of the above + pytest
```

## Usage

```bash
# single file, quality 92, into ./out
mikraw -q 92 some.RW2 -o ./out

# bulk: a whole folder, recursive, 8 workers, with auto-exposure
mikraw -r -j 8 --autoexp "C:\photos\lumix" -o ./out

# use a profile
mikraw --profile portrait "C:\photos\family" -o ./out_portraits
mikraw --profile monochrome "C:\photos\lumix" -o ./out_bw
mikraw --profile landscape --clarity 2.0 shot.RW2 -o ./out

# disable auto-exposure (use fixed +0.7 EV baseline)
mikraw --no-autoexp some.RW2 -o ./out

# 16-bit TIFF for further editing in Lightroom / Darktable
mikraw --tiff some.RW2 -o ./out

# GPU-accelerated develop pipeline (requires pip install pyopencl)
mikraw --gpu "C:\photos\lumix" -o ./out

# globs work (mikraw expands them itself on Windows too)
mikraw "*.RW2" -o ./out

# see what would happen, change nothing
mikraw --dry-run -r .
```

### Options

| Option | Meaning |
| --- | --- |
| `-q, --quality N` | JPEG quality percent (default 90) |
| `-o, --output DIR` | output directory (default: current dir) |
| `--profile NAME` | named look preset (default: `vibrant`) |
| `--list-profiles` | print all profiles and exit |
| `--autoexp` / `--no-autoexp` | auto-adjust exposure (default: on) |
| `--tiff` | output 16-bit lossless TIFF instead of JPEG |
| `--gpu` | OpenCL GPU for the develop pipeline (requires pyopencl; implies `-j 1`) |
| `-r, --recursive` | recurse into subdirectories |
| `-j, --jobs N` | parallel workers (default: CPU count) |
| `--overwrite` | overwrite existing output (default: skip) |
| `--suffix TEXT` | text added before the extension |
| `--contrast F` / `--saturation F` / `--clarity F` | override profile multiplier |
| `--no-exif` | don't copy EXIF metadata |
| `--dry-run` | list planned conversions and exit |

Output files are named `<source-stem><suffix>.jpg` (or `.tif` with `--tiff`).
EXIF (camera, lens, date, ISO, exposure) is copied from the RAW and orientation is
baked into the pixels.

## Notes on RW2

RW2 is proprietary and undocumented, so brand-new Lumix bodies released after the
bundled LibRaw version may need a `rawpy`/LibRaw upgrade. The established S-series
(S1 / S1R / S5 / S5II) decode well today. If a file is unreadable, mikraw reports
a clear "unsupported or unreadable RAW file" error rather than a raw LibRaw code.

## Development

```bash
pip install -e ".[dev]"
pytest          # 48 tests, all I/O-free (GPU tests verify fallback without pyopencl)
```

Tests cover the look engine (filmic curve, local contrast, vibrance, monochrome,
16-bit output), auto-exposure heuristic, profiles, GPU fallback, and CLI/discovery
logic. The GPU tests verify the graceful fallback path without requiring pyopencl.
