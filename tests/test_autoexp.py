import numpy as np

from mikraw import autoexp


def test_dark_image_brightens():
    luma = np.full((100, 100), 0.10, dtype=np.float32)
    shift = autoexp.exp_shift_for_luma(luma)
    assert shift > 1.0
    assert shift <= autoexp.EXP_SHIFT_MAX


def test_bright_image_darkens():
    luma = np.full((100, 100), 0.90, dtype=np.float32)
    shift = autoexp.exp_shift_for_luma(luma)
    assert shift < 1.0
    assert shift >= autoexp.EXP_SHIFT_MIN


def test_well_exposed_is_near_unity():
    luma = np.full((100, 100), autoexp._TARGET, dtype=np.float32)
    shift = autoexp.exp_shift_for_luma(luma)
    assert 0.9 <= shift <= 1.1


def test_clamped_to_usable_range():
    very_dark = np.full((50, 50), 0.001, dtype=np.float32)
    very_bright = np.full((50, 50), 0.999, dtype=np.float32)
    assert autoexp.exp_shift_for_luma(very_dark) <= autoexp.EXP_SHIFT_MAX
    assert autoexp.exp_shift_for_luma(very_bright) >= autoexp.EXP_SHIFT_MIN


def test_small_bright_cluster_does_not_block_brightening():
    # Mixed-light scene: mostly dark subject + small blown patches (e.g. window, sunlit floor).
    # The 70th-percentile reference sits below those patches, so brightening is not blocked.
    dark = np.full((100, 100), 0.15, dtype=np.float32)
    with_highlights = dark.copy()
    with_highlights[:5, :] = 0.97   # 5% bright specular patches
    shift_mixed = autoexp.exp_shift_for_luma(with_highlights)
    shift_dark = autoexp.exp_shift_for_luma(dark)
    # Mixed-light scene should still brighten significantly (not blocked by the hot patches).
    assert shift_mixed > 1.5
    # The bright patches pull the 40th pctile up slightly -> slightly less brightening.
    assert shift_mixed <= shift_dark
