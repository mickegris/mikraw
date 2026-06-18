"""Auto-exposure: pick an ``exp_shift`` from a fast half-res analysis pass.

``exp_shift`` is the linear exposure multiplier LibRaw applies during decode
(usable range 0.25 = 2 stops darker .. 8.0 = 3 stops brighter). We estimate it
from a quick half-size, display-gamma render.

Center-weighted metering: only the center 60×70% of the frame is analyzed,
matching how camera center-weighted metering works and excluding peripheral
hot-spots (lit floors, windows, sunlit patches). Within that zone we use the
70th-percentile luminance as the reference and bring it to 0.58, which keeps
the main subject properly exposed in mixed-light scenes.
"""

from __future__ import annotations

import numpy as np

EXP_SHIFT_MIN = 0.25
EXP_SHIFT_MAX = 8.0

_PCTILE = 40.0    # lower-midtone reference: targets the darker half of the center zone
_TARGET = 0.55    # where to bring that percentile (display 0..1)
_CW_X = 0.60      # center fraction of width to analyze
_CW_Y = 0.70      # center fraction of height to analyze
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def exp_shift_for_luma(luma: np.ndarray) -> float:
    """Compute a clamped exp_shift from a normalized (0..1) luma array."""
    luma = luma.astype(np.float32).ravel()
    ref = float(np.percentile(luma, _PCTILE))
    eps = 1e-4
    stops = float(np.log2(_TARGET / max(ref, eps)))
    shift = float(2.0 ** stops)
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
