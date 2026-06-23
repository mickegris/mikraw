"""Per-file conversion: RAW -> develop look -> JPEG/TIFF (+ EXIF)."""

from __future__ import annotations

import importlib.util
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


def _srgb_icc() -> bytes | None:
    """Return the sRGB ICC profile as bytes, generated once from PIL's built-in profile."""
    if not hasattr(_srgb_icc, "_cached"):
        try:
            from PIL import ImageCms
            _srgb_icc._cached = ImageCms.ImageCmsProfile(
                ImageCms.createProfile("sRGB")
            ).tobytes()
        except Exception:
            _srgb_icc._cached = None
    return _srgb_icc._cached


@dataclass
class Options:
    """Conversion options. Must stay picklable (sent to worker processes)."""

    output_dir: str
    quality: int = 90
    autoexp: bool = True
    overwrite: bool = False
    suffix: str = ""
    contrast: float = 1.0
    saturation: float = 1.0
    clarity: float = 1.0
    monochrome: bool = False
    output_format: str = "jpeg"   # "jpeg" or "tiff"
    use_gpu: bool = True
    colorspace: str = "srgb"      # "srgb" or "adobergb"
    dpi: int = 300
    copy_exif: bool = True


def output_path(src: str, opts: Options) -> Path:
    stem = Path(src).stem
    ext = ".tif" if opts.output_format == "tiff" else ".jpg"
    return Path(opts.output_dir) / f"{stem}{opts.suffix}{ext}"


def _postprocess(raw, exp_shift: float, rawpy, colorspace: str = "srgb"):
    """Single rawpy decode with our standard settings."""
    cs = rawpy.ColorSpace.Adobe if colorspace == "adobergb" else rawpy.ColorSpace.sRGB
    return raw.postprocess(
        use_camera_wb=True,
        no_auto_bright=True,
        exp_shift=exp_shift,
        output_bps=16,
        output_color=cs,
        gamma=(2.222, 4.5),
        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        highlight_mode=rawpy.HighlightMode.Clip,
        user_flip=None,
    )


def _blend_exposures(raw, exp_shift: float, rawpy, colorspace: str = "srgb") -> np.ndarray:
    """Decode twice and blend by luminance: highlights from base, subject from bright.

    Pixels with low luminance (shadows/midtones) come from the bright decode so
    the subject is properly exposed. Pixels with high luminance come from the
    base (exp_shift=1.0) decode so highlight detail is preserved and not clipped.
    """
    base = _postprocess(raw, 1.0, rawpy, colorspace).astype(np.float32) / 65535.0
    bright = _postprocess(raw, exp_shift, rawpy, colorspace).astype(np.float32) / 65535.0

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

    # Import rawpy eagerly so we can reference rawpy.LibRawError in the except below.
    try:
        import rawpy  # imported lazily so worker startup is cheap
    except ImportError:
        return FileResult(src, out_s, Status.FAILED,
                          "rawpy not installed — run: pip install rawpy")

    try:
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
                arr16 = _blend_exposures(raw, exp_shift, rawpy, opts.colorspace)
            else:
                arr16 = _postprocess(raw, exp_shift, rawpy, opts.colorspace)

        tiff_out = opts.output_format == "tiff"
        bits = 16 if tiff_out else 8

        rgb = None
        if opts.use_gpu:
            from mikraw import gpu as _gpu
            rgb = _gpu.try_apply_look(
                arr16, opts.contrast, opts.saturation, opts.clarity,
                opts.monochrome, bits,
            )
        if rgb is None:
            rgb = develop.apply_look(
                arr16, opts.contrast, opts.saturation, opts.clarity,
                opts.monochrome, bits=bits,
            )

        # ICC profile: embed sRGB profile for sRGB output so viewers render it
        # correctly. Adobe RGB output is saved without an embedded profile because
        # the Adobe RGB ICC data is not freely redistributable; embed it afterwards
        # with exiftool if your print workflow requires it.
        icc = _srgb_icc() if opts.colorspace == "srgb" else None
        if opts.colorspace == "adobergb":
            log.debug("Adobe RGB saved without embedded ICC profile")

        if tiff_out:
            try:
                import tifffile
            except ImportError:
                return FileResult(src, out_s, Status.FAILED,
                                  "tifffile is required for TIFF output — run: pip install tifffile")

            tiff_kw: dict = {
                "photometric": "rgb",
                "resolutionunit": 2,          # inch
                "resolution": (opts.dpi, opts.dpi),
            }
            if icc:
                tiff_kw["iccprofile"] = icc

            if importlib.util.find_spec("imagecodecs") is not None:
                tifffile.imwrite(out_s, rgb, compression="lzw", **tiff_kw)
            else:
                log.warning(
                    "imagecodecs not installed (pip install imagecodecs); "
                    "saving uncompressed TIFF"
                )
                tifffile.imwrite(out_s, rgb, **tiff_kw)
        else:
            from PIL import Image

            jpeg_kw: dict = {
                "quality": int(opts.quality),
                "optimize": True,
                "dpi": (opts.dpi, opts.dpi),
            }
            if opts.quality >= 90:
                jpeg_kw["subsampling"] = 0  # 4:4:4 for high quality
            if icc:
                jpeg_kw["icc_profile"] = icc
            Image.fromarray(rgb, "RGB").save(out_s, "JPEG", **jpeg_kw)

        msg = ""
        if opts.copy_exif:
            from mikraw import exif

            if not exif.copy_metadata(src, out_s, icc=icc):
                msg = "exif not copied"

        return FileResult(src, out_s, Status.CONVERTED, msg)

    except rawpy.LibRawError as e:
        return FileResult(src, out_s, Status.FAILED,
                          f"unsupported or unreadable RAW file: {e}")
    except Exception as e:
        log.debug("convert failed for %s", src, exc_info=True)
        return FileResult(src, out_s, Status.FAILED, str(e))
