"""Auto-exposure: pick an ``exp_shift`` from a fast half-res analysis pass.

``exp_shift`` is the linear exposure multiplier LibRaw applies during decode
(usable range 0.25 = 2 stops darker .. 8.0 = 3 stops brighter). We estimate it
from a quick half-size, display-gamma render.

Center-weighted metering: only the center 60×70% of the frame is analyzed,
matching how camera center-weighted metering works and excluding peripheral
hot-spots (lit floors, windows, sunlit patches).

Two references are combined, and the *smaller* shift wins:
  - Shadow metering: bring the 40th-percentile luminance up to _TARGET so a
    dark subject is properly exposed.
  - Highlight cap: the bright part of the center (92nd percentile, which lands
    on a subject's face/skin) must not be pushed past _HI_CEILING.

The highlight cap is what stops the "dark clothing fools the meter" failure:
when a subject wears dark clothes, the 40th-percentile reference is very low and
shadow metering alone would over-brighten and blow the face. Capping the bright
reference keeps the face from clipping while still letting genuinely dark scenes
(no bright subject in centre) brighten fully.
"""

from __future__ import annotations

import numpy as np

EXP_SHIFT_MIN = 0.25
EXP_SHIFT_MAX = 8.0

_PCTILE = 40.0       # lower-midtone reference: targets the darker half of the center zone
_TARGET = 0.55       # where to bring that percentile (display 0..1)
_HI_PCTILE = 92.0    # bright reference within the center (lands on face/skin highlights)
_HI_CEILING = 0.74   # never push that bright reference past this (display 0..1)
_CW_X = 0.60         # center fraction of width to analyze
_CW_Y = 0.70         # center fraction of height to analyze
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def exp_shift_for_luma(luma: np.ndarray) -> float:
    """Compute a clamped exp_shift from a normalized (0..1) luma array.

    Returns the smaller of the shadow-metering shift and the highlight-cap shift,
    so brightening never blows the brightest part of the (centre) frame.
    """
    luma = luma.astype(np.float32).ravel()
    eps = 1e-4
    ref = float(np.percentile(luma, _PCTILE))
    hi = float(np.percentile(luma, _HI_PCTILE))

    shift_shadow = _TARGET / max(ref, eps)
    shift_hi = _HI_CEILING / max(hi, eps)
    shift = min(shift_shadow, shift_hi)
    # The highlight cap may only limit brightening, never darken a scene that
    # shadow-metering wants brighter (a bright background must not darken a subject).
    if shift_shadow > 1.0:
        shift = max(shift, 1.0)
    return float(np.clip(shift, EXP_SHIFT_MIN, EXP_SHIFT_MAX))


def analyze(raw) -> float:
    """Estimate exp_shift from an open rawpy.RawPy handle via a half-res pass."""
    thumb = raw.postprocess(
        half_size=True,
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=8,
        exp_shift=1.0,
    )
    luma = (thumb.astype(np.float32) / 255.0) @ _LUMA
    # Crop to center zone to exclude peripheral hot-spots.
    h, w = luma.shape
    y0 = int(h * (1 - _CW_Y) / 2)
    y1 = int(h * (1 + _CW_Y) / 2)
    x0 = int(w * (1 - _CW_X) / 2)
    x1 = int(w * (1 + _CW_X) / 2)
    return exp_shift_for_luma(luma[y0:y1, x0:x1])
