"""Tests for the OpenCL GPU path.

These tests must pass even without pyopencl installed, so they verify the
fallback behaviour rather than actual GPU execution.
"""

import sys

import numpy as np
import pytest


def test_gpu_returns_none_when_pyopencl_missing(monkeypatch):
    """try_apply_look returns None gracefully when pyopencl is not installed."""
    monkeypatch.setitem(sys.modules, "pyopencl", None)
    from mikraw import gpu

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    result = gpu.try_apply_look(arr, 1.0, 1.0, 1.0, False, 8)
    assert result is None


def test_gpu_returns_none_on_no_platform(monkeypatch):
    """try_apply_look returns None when OpenCL has no usable platform."""
    import types

    fake_cl = types.ModuleType("pyopencl")

    class _Err(Exception):
        pass

    fake_cl.Error = _Err
    fake_cl.get_platforms = lambda: []  # no platforms
    fake_cl.mem_flags = types.SimpleNamespace(READ_WRITE=1, WRITE_ONLY=2, COPY_HOST_PTR=4)
    monkeypatch.setitem(sys.modules, "pyopencl", fake_cl)
    # Invalidate cached context so the next call re-initialises.
    import threading
    from mikraw import gpu
    gpu._local.__dict__.clear()

    arr = (np.random.rand(8, 8, 3) * 65535).astype(np.uint16)
    result = gpu.try_apply_look(arr, 1.0, 1.0, 1.0, False, 8)
    assert result is None


def test_develop_apply_look_cpu_fallback_is_unaffected():
    """develop.apply_look() always uses the numpy path — GPU is opt-in from pipeline."""
    from mikraw import develop

    arr = (np.random.rand(16, 16, 3) * 65535).astype(np.uint16)
    out = develop.apply_look(arr)
    assert out.dtype == np.uint8
    assert out.shape == (16, 16, 3)
