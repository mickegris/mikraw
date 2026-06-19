import numpy as np
import pytest

from mikraw.profiles import DEFAULT_PROFILE, PROFILES


def test_all_profiles_have_required_fields():
    for name, prof in PROFILES.items():
        assert hasattr(prof, "contrast")
        assert hasattr(prof, "saturation")
        assert hasattr(prof, "clarity")
        assert hasattr(prof, "monochrome")
        assert 0.0 <= prof.contrast <= 3.0
        assert 0.0 <= prof.saturation <= 3.0
        assert 0.0 <= prof.clarity <= 3.0


def test_default_profile_exists():
    assert DEFAULT_PROFILE in PROFILES


def test_vibrant_is_full_strength():
    p = PROFILES["vibrant"]
    assert p.contrast == 1.0
    assert p.saturation == 1.0
    assert p.clarity == 1.0
    assert not p.monochrome


def test_neutral_disables_look():
    p = PROFILES["neutral"]
    assert p.contrast == 0.0
    assert p.saturation == 0.0
    assert p.clarity == 0.0
    assert not p.monochrome


def test_monochrome_profile_is_flagged():
    assert PROFILES["monochrome"].monochrome is True


def test_non_monochrome_profiles_are_color():
    for name, prof in PROFILES.items():
        if name != "monochrome":
            assert not prof.monochrome, f"profile '{name}' should not be monochrome"


def test_monochrome_apply_gives_equal_channels():
    from mikraw import develop

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    out = develop.apply_look(arr, monochrome=True)
    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])


def test_monochrome_output_is_uint8():
    from mikraw import develop

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    out = develop.apply_look(arr, monochrome=True)
    assert out.dtype == np.uint8


def test_tiff_bits_returns_uint16():
    from mikraw import develop

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    out = develop.apply_look(arr, bits=16)
    assert out.dtype == np.uint16
    assert out.shape == arr.shape
    assert out.min() >= 0 and out.max() <= 65535


def test_tiff_monochrome_channels_equal():
    from mikraw import develop

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    out = develop.apply_look(arr, monochrome=True, bits=16)
    assert out.dtype == np.uint16
    assert np.array_equal(out[..., 0], out[..., 1])
    assert np.array_equal(out[..., 1], out[..., 2])
