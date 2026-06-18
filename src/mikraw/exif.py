"""Best-effort EXIF copy from the source RAW into the output JPEG.

Primary path uses pyexiv2 (bundles exiv2, reads RW2). Since the JPEG pixels are
already rotated upright by LibRaw, we force Orientation=1 so viewers don't rotate
again. EXIF copying is best-effort: a metadata failure never fails the convert.
"""

from __future__ import annotations

import logging

log = logging.getLogger("mikraw")

try:  # optional dependency
    import pyexiv2  # type: ignore

    _HAVE_PYEXIV2 = True
except Exception:  # pragma: no cover - import-environment dependent
    _HAVE_PYEXIV2 = False


def available() -> bool:
    return _HAVE_PYEXIV2


def copy_metadata(src: str, dst: str) -> bool:
    """Copy EXIF from RAW ``src`` into JPEG ``dst``. Returns True on success."""
    if not _HAVE_PYEXIV2:
        log.debug("pyexiv2 not installed; skipping EXIF copy for %s", dst)
        return False
    try:
        with pyexiv2.Image(src) as s:
            exif = s.read_exif()
        # Drop the embedded RAW thumbnail/preview pointers -- they no longer
        # match the JPEG and can confuse viewers.
        exif = {
            k: v
            for k, v in exif.items()
            if not k.startswith("Exif.Thumbnail")
            and "JPEGInterchangeFormat" not in k
        }
        exif["Exif.Image.Orientation"] = "1"
        with pyexiv2.Image(dst) as d:
            d.modify_exif(exif)
        return True
    except Exception as e:  # best-effort
        log.warning("EXIF copy failed for %s: %s", dst, e)
        return False
