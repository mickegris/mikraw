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
    # Mixed-light scene: mostly dark subject + tiny blown patches (e.g. window, sunlit floor).
    # A 5% cluster stays below the 92nd-pctile highlight reference, so brightening is not capped.
    dark = np.full((100, 100), 0.15, dtype=np.float32)
    with_highlights = dark.copy()
    with_highlights[:5, :] = 0.97   # 5% bright specular patches
    shift_mixed = autoexp.exp_shift_for_luma(with_highlights)
    shift_dark = autoexp.exp_shift_for_luma(dark)
    assert shift_mixed > 1.5
    assert shift_mixed <= shift_dark


def test_highlight_cap_protects_bright_subject():
    # Dark clothing dominates the centre (drags the 40th pctile down), but a sizeable
    # bright face region exists. The highlight cap must limit brightening so the face
    # is not blown -- far less than a uniformly-dark frame at the same 40th pctile.
    jacket = np.full((100, 100), 0.12, dtype=np.float32)
    with_face = jacket.copy()
    with_face[:15, :] = 0.55          # 15% bright skin region -> lands on 92nd pctile
    shift_face = autoexp.exp_shift_for_luma(with_face)
    shift_uniform = autoexp.exp_shift_for_luma(jacket)
    # The cap holds the bright region near the ceiling instead of over-brightening.
    assert shift_face < shift_uniform
    assert shift_face < 2.0
