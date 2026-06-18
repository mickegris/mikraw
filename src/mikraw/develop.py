"""The hardcoded "develop" look: filmic tone curve + vibrant saturation.

Input is the gamma-corrected (display-referred) 16-bit RGB array produced by
rawpy's ``postprocess`` (uint16, HxWx3, range 0..65535). White balance and base
exposure are already baked in by LibRaw; this module applies the look on top.

Tone pipeline (in order):
  1. Shadow lift (toe) — raises the black point slightly; recovers shadow detail.
  2. Midtone S-curve — adds punch without touching the extreme ends.
  3. Highlight rolloff (shoulder) — sine-based soft compression above the rolloff
     point; highlights approach white gradually rather than clipping hard.
  4. Vibrance — luma-preserving saturation boost that tapers for already-saturated
     pixels so skies/skin don't posterize.

All look constants are named module-level values. The CLI ``--contrast`` /
``--saturation`` multipliers scale the hardcoded strengths (1.0 = baked-in look,
0.0 = that stage disabled).

Luma weights are Rec.709 (sRGB primaries).
"""

from __future__ import annotations

import numpy as np

# --- Look constants ----------------------------------------------------------
SHADOW_LIFT = 0.04          # raise black point by this much (0..1); subtle toe lift
HIGHLIGHT_ROLLOFF = 0.80    # start of smooth shoulder compression (0..1)
CONTRAST_STRENGTH = 0.14    # midtone S-curve steepness (applied between toe and shoulder)

SATURATION_BASE = 0.14      # baseline chroma boost (all pixels)
SATURATION_VIBRANCE = 0.26  # extra boost for low-chroma pixels (tapers to 0 at full chroma)


_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _s_curve(x: np.ndarray, strength: float) -> np.ndarray:
    """Monotonic sigmoid contrast on [0,1]. strength<=0 is identity."""
    g = 1.0 + max(strength, 0.0)
    if g == 1.0:
        return x
    xg = np.power(x, g)
    ig = np.power(1.0 - x, g)
    return xg / (xg + ig + 1e-12)


def _filmic_curve(x: np.ndarray, contrast_mult: float) -> np.ndarray:
    """Filmic tone curve: shadow lift → midtone contrast → highlight rolloff."""
    # 1) Shadow lift: remap [0,1] → [SHADOW_LIFT, 1] linearly.
    x = x * (1.0 - SHADOW_LIFT) + SHADOW_LIFT

    # 2) Midtone S-curve for punch (scaled by the --contrast multiplier).
    if contrast_mult > 0.0:
        x = _s_curve(x, CONTRAST_STRENGTH * contrast_mult)

    # 3) Highlight rolloff: sine shoulder above HIGHLIGHT_ROLLOFF.
    #    At the join point the slope is π/2 (~1.57), creating a distinct shoulder
    #    that eases highlights to white rather than clipping abruptly.
    r = HIGHLIGHT_ROLLOFF
    above = x > r
    t = np.clip((x - r) / (1.0 - r), 0.0, 1.0)
    rolled = r + (1.0 - r) * np.sin(t * (np.pi / 2.0))
    return np.where(above, rolled, x)


def _vibrance(rgb: np.ndarray, base: float, vibrance: float) -> np.ndarray:
    """Luma-preserving saturation push that tapers for already-saturated pixels."""
    luma = (rgb @ _LUMA)[..., None]
    chroma = rgb.max(axis=-1, keepdims=True) - rgb.min(axis=-1, keepdims=True)
    factor = 1.0 + base + vibrance * (1.0 - chroma)
    return np.clip(luma + (rgb - luma) * factor, 0.0, 1.0)


def apply_look(
    arr16: np.ndarray,
    contrast_mult: float = 1.0,
    saturation_mult: float = 1.0,
) -> np.ndarray:
    """Apply the develop look to a uint16 RGB array, returning uint8 RGB.

    contrast_mult / saturation_mult scale the hardcoded strengths; 1.0 keeps the
    baked-in look, 0.0 disables that stage.
    """
    x = arr16.astype(np.float32) / 65535.0
    x = _filmic_curve(x, contrast_mult)
    x = _vibrance(x, SATURATION_BASE * saturation_mult, SATURATION_VIBRANCE * saturation_mult)
    return np.clip(x * 255.0 + 0.5, 0, 255).astype(np.uint8)
