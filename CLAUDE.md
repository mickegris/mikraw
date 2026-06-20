# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Overview
`mikraw` is a cross-platform **CLI** that bulk-converts camera **RAW** files to
**JPEG** (or 16-bit **TIFF**) with a fixed, opinionated "develop" look. Built in
**Python** on **rawpy** (LibRaw) + **numpy** + **Pillow**. Primary target: fast
batch conversion of **Panasonic Lumix S-series (`.RW2`)** files.

The look is hardcoded by design (see "Develop pipeline") and selected via
`--profile` (default: `vibrant`). Per-run multipliers `--saturation` /
`--contrast` / `--clarity` override the profile value when provided.

## Commands
Run from the repo root (`C:\Users\mikae\mikraw`). The dev interpreter lives in
`.venv`; a `mikraw.bat` launcher wraps `python -m mikraw`.

```powershell
.\.venv\Scripts\python.exe -m pytest          # run the test suite (48 tests, I/O-free)
.\.venv\Scripts\python.exe -m pytest -q -k autoexp   # subset
.\mikraw --help                               # run the CLI via the venv launcher
.\mikraw --overwrite -o .\out path\to\file.RW2         # convert (autoexp on by default)
.\mikraw --no-autoexp --overwrite -o .\out path\to\file.RW2  # fixed +0.7 EV baseline
.\mikraw --list-profiles                      # show all profiles
.\mikraw --profile portrait -o .\out path\to\file.RW2 # use a profile
.\mikraw --tiff -o .\out path\to\file.RW2    # 16-bit TIFF output
.\mikraw --gpu -o .\out path\to\file.RW2     # OpenCL GPU develop pipeline
pip install -e ".[dev]"                       # editable install + dev deps
pip install tifffile                          # needed for --tiff output
pip install pyopencl                          # needed for --gpu
```

- Tests are pure-logic `tests/test_*.py` (look engine incl. local contrast,
  autoexp heuristic, CLI/discovery). They do **not** need rawpy or a RAW file.
- A real end-to-end RAW conversion can only be verified by the user running the
  CLI on actual `.RW2` files — Claude cannot decode RAW here. Make principled
  changes and have the user test.

## Tech stack
- Python 3.10+ (dev machine runs 3.14)
- `rawpy` — RAW decode/demosaic (bundles LibRaw)
- `numpy` — the develop math
- `Pillow` — JPEG encode
- `tqdm` — bulk progress bar
- `tifffile` — optional, 16-bit TIFF output (`[tiff]` extra)
- `pyopencl` — optional, OpenCL GPU develop pipeline (`[gpu]` extra)
- `pyexiv2` — optional, copies EXIF from RAW into the output (`[exif]` extra)
- stdlib `argparse` + `multiprocessing` — CLI and parallel batch

## Project structure
```
src/mikraw/
  __main__.py    python -m mikraw entry
  cli.py         argparse, input discovery, builds Options, dispatches to batch
  batch.py       discover files, multiprocessing pool, tqdm, skip/overwrite, summary
  pipeline.py    convert_one(): decode -> (blend) -> develop -> JPEG/TIFF -> EXIF
  develop.py     the hardcoded look: filmic tone curve + vibrance + skin protection
  gpu.py         OpenCL develop path (optional, falls back to numpy automatically)
  profiles.py    named look presets (Profile dataclass + PROFILES dict)
  autoexp.py     analyze() -> exp_shift (center-weighted metering + highlight cap)
  exif.py        copy_metadata() via pyexiv2, bakes orientation = normal
  errors.py      FileResult + Status enum
tests/           pure-logic unit tests
mikraw.bat       venv launcher (python -m mikraw)
```

## Profiles (`profiles.py`)
Named presets that bundle look multipliers. Resolved in `cli.main()`; explicit
`--contrast`/`--saturation`/`--clarity` CLI flags override the profile's value.

| Profile      | contrast | saturation | clarity | monochrome |
|-------------|----------|------------|---------|------------|
| `vibrant`   | 1.0      | 1.0        | 1.0     | no (default) |
| `neutral`   | 0.0      | 0.0        | 0.0     | no |
| `camera`    | 0.4      | 0.3        | 0.1     | no |
| `portrait`  | 0.7      | 0.8        | 0.3     | no |
| `monochrome`| 1.5      | 0.0        | 2.0     | yes |
| `landscape` | 1.2      | 1.5        | 1.8     | no |

Adding a profile: add a `Profile(...)` entry to `PROFILES` in `profiles.py`.
No other file needs to change.

## Auto-exposure is now the default

`Options.autoexp = True` and `--autoexp` is on by default in the CLI. Use
`--no-autoexp` to revert to the fixed `BASE_EXPOSURE = 2**0.7` (+0.7 EV)
baseline. `BooleanOptionalAction` provides both flags automatically.

## OpenCL GPU acceleration (`--gpu`)

`--gpu` routes the develop pipeline through `gpu.try_apply_look()` (OpenCL kernels
in `gpu.py`). If pyopencl is unavailable or no platform is found it falls back to
numpy silently. Requires `pip install pyopencl`.

Architecture notes:
- `--gpu` forces `jobs=1` (multiple processes competing for one GPU would be slower
  than CPU parallelism).
- The OpenCL context, queue, and compiled program are cached thread-locally in
  `gpu._local` so they're initialised once per process.
- Blur kernels use a brute-force per-pixel approach (each work-item sums 2r+1
  inputs). For typical radii (r≤120) on a modern GPU this is fast enough, but a
  shared-memory sliding-window approach would be ~10× more efficient.
- `develop.py` has no knowledge of GPU — the split is in `pipeline.convert_one`.

## TIFF output (`--tiff`)
Saves a 16-bit-per-channel RGB TIFF (LZW compressed) using `tifffile`. The full
develop look is applied at 16-bit precision so shadows/highlights keep full range.
Requires `pip install tifffile` (or `pip install -e ".[tiff]"`). EXIF copy works
the same as JPEG. Output extension is `.tif`.

## Develop pipeline (the look)
Per file, `pipeline.convert_one`:

1. **Exposure decision**
   - `--autoexp`: `autoexp.analyze(raw)` returns a linear `exp_shift`.
   - otherwise: `BASE_EXPOSURE = 2**0.7` (+0.7 EV). This matches Darktable's
     documented scene-referred default — a midtone lift that compensates for the
     tone curve cameras bake into previews (LibRaw's decode does not). Without it
     the output looks dark/dull.
2. **Decode** with rawpy: `use_camera_wb=True` (WB as shot), `no_auto_bright=True`,
   `output_bps=16`, sRGB, `gamma=(2.222, 4.5)`, AHD demosaic.
3. **Two-decode highlight blend** (`_blend_exposures`, only when `exp_shift > 1.01`):
   decode at `1.0` (highlights intact) and at `exp_shift` (subject bright), then
   blend by luminance with a smoothstep over `_BLEND_DARK=0.40`.._BLEND_LIGHT=0.90`.
   Shadows/midtones come from the bright decode; highlights from the base decode,
   so brightening can't blow highlights. Avoids the blown-shoulder failure mode.
4. **`develop.apply_look`** (numpy, on the 16-bit array):
   - `_filmic_curve`: shadow lift (`SHADOW_LIFT`), midtone S-curve
     (`CONTRAST_STRENGTH`), sine highlight shoulder above `HIGHLIGHT_ROLLOFF`.
   - `_local_contrast`: multi-scale luminance "clarity" (`LOCAL_CONTRAST`). Detail
     = mid-frequency luminance variation at a fine + coarse scale (separable box
     blur, `_blur`), tanh soft-clipped (`LOCAL_CONTRAST_CLIP`) to avoid edge
     halos, added equally to all channels (preserves chroma). This is the
     micro-contrast/depth that Darktable's tone-equalizer gives.
   - `_vibrance` (color) or grayscale conversion (monochrome profile): luma-
     preserving saturation boost with skin-tone protection, **or** for monochrome:
     luminance-weighted grayscale expanded back to 3 channels (vibrance skipped).
   - `bits` parameter: 8 → uint8 for JPEG; 16 → uint16 for TIFF.
5. **Encode**: JPEG at `quality` (4:4:4 subsampling when `quality >= 90`), or
   16-bit LZW TIFF via `tifffile` when `--tiff` was passed.
6. **EXIF**: `exif.copy_metadata` copies tags from the RAW and sets Orientation =
   normal (pixels are already upright). Skipped with `--no-exif`.

## Auto-exposure (`autoexp.py`)
- Fast half-res display-gamma thumb at `exp_shift=1.0`.
- **Center-weighted**: only the center `_CW_X`×`_CW_Y` crop is analyzed (excludes
  peripheral hot-spots like lit floors/windows).
- Two references, smaller shift wins:
  - shadow metering: bring the `_PCTILE` (40th) up to `_TARGET` (0.55);
  - highlight cap: the `_HI_PCTILE` (92nd, lands on a face) must not exceed
    `_HI_CEILING` (0.74). This stops the "dark clothing drags the meter down ->
    over-brighten -> blow the face" trap.
- The cap may only *limit* brightening, never darken a scene the shadow meter
  wants brighter. Returns a value clamped to `[EXP_SHIFT_MIN, EXP_SHIFT_MAX]`.

## Where to tune the look
All knobs are named module-level constants:
- Tone/contrast/highlights: `develop.SHADOW_LIFT`, `CONTRAST_STRENGTH`,
  `HIGHLIGHT_ROLLOFF`.
- Local contrast: `develop.LOCAL_CONTRAST`, `LOCAL_CONTRAST_RADIUS`,
  `LOCAL_CONTRAST_CLIP` (CLI `--clarity` scales the strength).
- Saturation + skin: `develop.SATURATION_BASE`, `SATURATION_VIBRANCE`,
  `SKIN_PROTECT`, `SKIN_HUE_CENTER`, `SKIN_HUE_WIDTH`.
- Exposure: `pipeline.BASE_EXPOSURE`, `_BLEND_DARK`, `_BLEND_LIGHT`.
- Metering: `autoexp._PCTILE`, `_TARGET`, `_HI_PCTILE`, `_HI_CEILING`, `_CW_X/Y`.

When changing the look, also update the matching `tests/test_*.py` assertions and
keep the README "look" section accurate.

## Reference: matching Darktable
The look was tuned against the user's Darktable edits of Lumix RW2 files. Their
recipe (from the `.xmp` sidecars) is: camera WB, **+0.7 EV default exposure**, a
**sigmoid** tone map (contrast ~1.5), and a "compress shadows/highlights" tone
equalizer. mikraw approximates this globally; the tone-equalizer's local
micro-contrast is approximated by `_local_contrast` (v0.2). It is a multi-scale
unsharp, not a true edge-aware guided filter, so very high-contrast edges rely on
the tanh soft-clip rather than a guide image to stay halo-free.

## Common pitfalls
- **Edit requires prior Read** in a session.
- **Run pytest/CLI via `.venv\Scripts\python.exe`** — the bare `python` on PATH is
  the system interpreter and lacks the deps.
- **Glob on Windows**: pass the directory as `path`, filename as `pattern`.
- **multiprocessing**: `convert_one` and `Options` must stay picklable (workers
  are spawned). Keep heavy imports (rawpy, PIL) lazy inside the function.
- **Can't preview RAW here** — Claude has no RAW files/rawpy at hand; rely on the
  user to visually confirm conversions.

## Current version
`0.4.0` — see `pyproject.toml`.
