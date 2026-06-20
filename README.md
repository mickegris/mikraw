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

Requires **Python 3.10+**.

### Step 1 — create a virtual environment

```bash
# Windows
python -m venv .venv

# macOS / Linux
python3 -m venv .venv
```

### Step 2 — install mikraw

```bash
# Windows
.venv\Scripts\pip install -e .

# macOS / Linux
.venv/bin/pip install -e .
```

This installs the **required** dependencies:

| Package | Version | Why |
| --- | --- | --- |
| `rawpy` | ≥ 0.21 | RAW decoding (bundles LibRaw) |
| `numpy` | ≥ 1.24 | develop pipeline math |
| `Pillow` | ≥ 10.0 | JPEG encoding |
| `tqdm` | ≥ 4.65 | progress bar |

### Step 3 — install optional features

Each optional feature has its own extra. Install only what you need:

| Extra | Command | What it enables |
| --- | --- | --- |
| `[exif]` | `pip install -e ".[exif]"` | Copy EXIF from RAW into output (pyexiv2) |
| `[tiff]` | `pip install -e ".[tiff]"` | 16-bit TIFF output (tifffile + imagecodecs for LZW) |
| `[gpu]` | `pip install -e ".[gpu]"` | OpenCL GPU acceleration (pyopencl) |
| `[dev]` | `pip install -e ".[dev]"` | All of the above + pytest |

> **EXIF copy** (`[exif]`): without this, EXIF metadata (camera model, focal
> length, ISO, date, etc.) is not copied into the output file. Strongly recommended
> for real photo workflows.
>
> **TIFF output** (`[tiff]`): required for `--tiff`. Includes `imagecodecs` so
> that LZW compression works out of the box. If imagecodecs is missing, mikraw
> warns and saves an uncompressed TIFF automatically.
>
> **GPU acceleration** (`[gpu]`): enables OpenCL GPU processing. The GPU path is
> **on by default** — mikraw tries the GPU first and falls back to CPU
> automatically if pyopencl is not installed or no device is found. Install this
> extra to actually use GPU hardware.

### Step 4 — use the launcher

```bash
# Windows — run from the project directory:
mikraw.bat [OPTIONS] INPUTS...

# macOS / Linux — make executable once, then use it:
chmod +x mikraw.sh
./mikraw.sh [OPTIONS] INPUTS...
```

Or call the venv interpreter directly (works everywhere):

```bash
# Windows
.venv\Scripts\python -m mikraw [OPTIONS] INPUTS...

# macOS / Linux
.venv/bin/python -m mikraw [OPTIONS] INPUTS...
```

## Usage

```bash
# single file, quality 92, into ./out
mikraw.bat -q 92 some.RW2 -o ./out

# bulk: whole folder, recursive, 8 workers
mikraw.bat -r -j 8 "C:\photos\lumix" -o ./out

# use a profile
mikraw.bat --profile portrait "C:\photos\family" -o ./out_portraits
mikraw.bat --profile monochrome "C:\photos\lumix" -o ./out_bw
mikraw.bat --profile landscape --clarity 2.0 shot.RW2 -o ./out

# disable auto-exposure (use fixed +0.7 EV baseline)
mikraw.bat --no-autoexp some.RW2 -o ./out

# 16-bit TIFF for further editing in Lightroom / Darktable (requires [tiff])
mikraw.bat --tiff some.RW2 -o ./out

# force CPU-only (disable GPU)
mikraw.bat --no-gpu "C:\photos\lumix" -o ./out

# globs work (mikraw expands them itself on Windows too)
mikraw.bat "*.RW2" -o ./out

# see what would happen, change nothing
mikraw.bat --dry-run -r .
```

### Options

| Option | Meaning |
| --- | --- |
| `-q, --quality N` | JPEG quality percent (default 90) |
| `-o, --output DIR` | output directory (default: current dir) |
| `--profile NAME` | named look preset (default: `vibrant`) |
| `--list-profiles` | print all profiles and exit |
| `--autoexp` / `--no-autoexp` | auto-adjust exposure (default: on) |
| `--tiff` | 16-bit TIFF output instead of JPEG (requires `[tiff]`) |
| `--colorspace srgb\|adobergb` | output color space (default: srgb) |
| `--dpi N` | resolution in file header (default: 300) |
| `--gpu` / `--no-gpu` | GPU acceleration (default: on; falls back to CPU automatically) |
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

## GPU acceleration

mikraw tries **OpenCL GPU** processing for the develop pipeline by default. No
flag needed — it just works if `pyopencl` is installed. If it is not installed or
no compatible device is found (GPU or CPU OpenCL), mikraw falls back to the numpy
CPU path silently.

```bash
# Install GPU support:
pip install -e ".[gpu]"

# Disable GPU (force CPU-only):
mikraw.bat --no-gpu photos/ -o out/
```

The OpenCL context and compiled kernels are cached the first time a device is
found, so the compilation overhead is paid only once per process. When multiple
workers run in parallel (`-j N`), each worker initialises its own OpenCL context.

## Color space and DPI

**Color space** (`--colorspace`): `srgb` (default) covers the web, most displays,
and standard printing. `adobergb` captures a wider gamut from the RAW sensor —
useful for professional printing where the printer and RIP are Adobe RGB-aware. The
sRGB ICC profile is automatically embedded in both JPEG and TIFF output. Adobe RGB
output is saved without an embedded ICC profile because the Adobe RGB 1998
specification is not freely redistributable; embed it manually if needed:

```bash
exiftool -icc_profile<=AdobeRGB1998.icc output.tif
```

**DPI** (`--dpi`): controls the resolution metadata written to the file header
(default 300 DPI, standard for photo printing). For TIFF this is the TIFF
directory tag. For JPEG the camera's own EXIF DPI is used instead when EXIF copy
succeeds; pass `--no-exif` if you want your `--dpi` value to take effect in the
JPEG.

## Notes on RW2

RW2 is proprietary and undocumented, so brand-new Lumix bodies released after the
bundled LibRaw version may need a `rawpy`/LibRaw upgrade. The established S-series
(S1 / S1R / S5 / S5II) decode well today. If a file is unreadable, mikraw reports
a clear "unsupported or unreadable RAW file" error rather than a raw LibRaw code.

## Development

```bash
pip install -e ".[dev]"
pytest          # 52 tests, all I/O-free
```

Tests cover the look engine (filmic curve, local contrast, vibrance, monochrome,
16-bit output), auto-exposure heuristic, profiles, GPU fallback, and CLI/discovery
logic. The GPU tests verify the graceful fallback path without requiring pyopencl.
