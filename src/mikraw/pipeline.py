"""Per-file conversion: RAW -> develop look -> JPEG (+ EXIF)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mikraw import develop
from mikraw.errors import FileResult, Status

log = logging.getLogger("mikraw")

# Luminance thresholds for the two-decode exposure blend (gamma-space, 0..1).
# Below _BLEND_DARK: 100% from the bright decode (properly exposed subject).
# Above _BLEND_LIGHT: 100% from the base decode (highlight detail preserved).
# Wide zone + smoothstep avoids visible seams on arms/skin transitioning through lit areas.
_BLEND_DARK = 0.40
_BLEND_LIGHT = 0.90

# Baseline exposure lift for the non-autoexp path. Matches Darktable's documented
# default of +0.7 EV applied to every image -- midtone brightening that
# compensates for the +0.5..1.2 EV tone curve cameras bake into their previews
# (which LibRaw's raw decode does not). Routed through the two-decode blend so
# the lift can't blow highlights. Autoexp meters its own exposure and ignores this.
BASE_EXPOSURE = 2.0 ** 0.7   # ~1.62

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


@dataclass
class Options:
    """Conversion options. Must stay picklable (sent to worker processes)."""

    output_dir: str
    quality: int = 90
    autoexp: bool = False
    overwrite: bool = False
    suffix: str = ""
    contrast: float = 1.0
    saturation: float = 1.0
    clarity: float = 1.0
    copy_exif: bool = True


def output_path(src: str, opts: Options) -> Path:
    stem = Path(src).stem
    return Path(opts.output_dir) / f"{stem}{opts.suffix}.jpg"


def _postprocess(raw, exp_shift: float, rawpy):
    """Single rawpy decode with our standard settings."""
    return raw.postprocess(
        use_camera_wb=True,
        no_auto_bright=True,
        exp_shift=exp_shift,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(2.222, 4.5),
        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        highlight_mode=rawpy.HighlightMode.Clip,
        user_flip=None,
    )


def _blend_exposures(raw, exp_shift: float, rawpy) -> np.ndarray:
    """Decode twice and blend by luminance: highlights from base, subject from bright.

    Pixels with low luminance (shadows/midtones) come from the bright decode so
    the subject is properly exposed. Pixels with high luminance come from the
    base (exp_shift=1.0) decode so highlight detail is preserved and not clipped.
    """
    base = _postprocess(raw, 1.0, rawpy).astype(np.float32) / 65535.0
    bright = _postprocess(raw, exp_shift, rawpy).astype(np.float32) / 65535.0

    luma = (base @ _LUMA)[..., None]
    t = np.clip((luma - _BLEND_DARK) / (_BLEND_LIGHT - _BLEND_DARK), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)  # smoothstep: zero slope at both ends, no visible seam
    blended = base * t + bright * (1.0 - t)
    return (np.clip(blended, 0.0, 1.0) * 65535.0).astype(np.uint16)


def convert_one(src: str, opts: Options) -> FileResult:
    """Convert a single RAW file. Never raises -- failures come back as results."""
    out = output_path(src, opts)
    out_s = str(out)

    if out.exists() and not opts.overwrite:
        return FileResult(src, out_s, Status.SKIPPED, "output exists")

    try:
        import rawpy  # imported lazily so worker startup is cheap

        out.parent.mkdir(parents=True, exist_ok=True)

        with rawpy.imread(src) as raw:
            if opts.autoexp:
                from mikraw import autoexp

                exp_shift = autoexp.analyze(raw)
                log.debug("%s: autoexp exp_shift=%.3f", src, exp_shift)
            else:
                # Default Darktable-style baseline lift (no metering).
                exp_shift = BASE_EXPOSURE
                log.debug("%s: base exp_shift=%.3f", src, exp_shift)

            if exp_shift > 1.01:
                # Two-decode blend: subject exposure + highlight preservation.
                arr16 = _blend_exposures(raw, exp_shift, rawpy)
            else:
                arr16 = _postprocess(raw, exp_shift, rawpy)

        rgb8 = develop.apply_look(arr16, opts.contrast, opts.saturation, opts.clarity)

        from PIL import Image

        save_kwargs = {"quality": int(opts.quality), "optimize": True}
        if opts.quality >= 90:
            save_kwargs["subsampling"] = 0  # 4:4:4 for high quality
        Image.fromarray(rgb8, "RGB").save(out_s, "JPEG", **save_kwargs)

        msg = ""
        if opts.copy_exif:
            from mikraw import exif

            if not exif.copy_metadata(src, out_s):
                msg = "exif not copied"

        return FileResult(src, out_s, Status.CONVERTED, msg)

    except Exception as e:
        log.debug("convert failed for %s", src, exc_info=True)
        return FileResult(src, out_s, Status.FAILED, str(e))
