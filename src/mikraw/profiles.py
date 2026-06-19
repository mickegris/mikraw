"""Named look presets for mikraw.

Each profile bundles the contrast/saturation/clarity multipliers and the
monochrome flag. CLI --contrast/--saturation/--clarity flags override the
profile's values when explicitly provided.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    contrast: float = 1.0
    saturation: float = 1.0
    clarity: float = 1.0
    monochrome: bool = False


PROFILES: dict[str, Profile] = {
    "vibrant": Profile(
        name="vibrant",
        description="Filmic look with punchy contrast, local clarity, and vibrant colors",
        contrast=1.0, saturation=1.0, clarity=1.0,
    ),
    "neutral": Profile(
        name="neutral",
        description="Minimal processing — faithful to the RAW decode, no color push",
        contrast=0.0, saturation=0.0, clarity=0.0,
    ),
    "camera": Profile(
        name="camera",
        description="Approximates what the camera's own JPEG engine would produce",
        contrast=0.4, saturation=0.3, clarity=0.1,
    ),
    "monochrome": Profile(
        name="monochrome",
        description="Black and white with punchy contrast and strong local clarity",
        contrast=1.5, saturation=0.0, clarity=2.0, monochrome=True,
    ),
    "landscape": Profile(
        name="landscape",
        description="Maximum clarity and color saturation — ideal for outdoor/nature shots",
        contrast=1.2, saturation=1.5, clarity=1.8,
    ),
}

DEFAULT_PROFILE = "vibrant"
