"""Optional OpenCL-accelerated develop look.

Mirrors develop.apply_look() on the GPU. Returns None if PyOpenCL is unavailable,
no device is found, or any kernel fails — the caller falls back to the numpy path.

Install:  pip install pyopencl   (or pip install -e ".[gpu]")

The full develop pipeline runs on the GPU:
  1. filmic tone curve (shadow lift, S-curve, sine highlight shoulder)
  2. local contrast (luma extraction, 2-pass separable box blur ×2 scales, tanh clip)
  3. vibrance with skin-tone protection  —or—  monochrome luma conversion
  4. quantize to uint8 (JPEG) or uint16 (TIFF)

The OpenCL context + compiled program are cached thread-locally so repeated calls
in the same process (or worker) pay the compile cost only once.
"""

from __future__ import annotations

import logging
import threading
from types import SimpleNamespace
from typing import Optional

import numpy as np

from mikraw.develop import (
    CONTRAST_STRENGTH,
    HIGHLIGHT_ROLLOFF,
    LOCAL_CONTRAST,
    LOCAL_CONTRAST_CLIP,
    LOCAL_CONTRAST_RADIUS,
    SATURATION_BASE,
    SATURATION_VIBRANCE,
    SHADOW_LIFT,
    SKIN_HUE_CENTER,
    SKIN_HUE_WIDTH,
    SKIN_PROTECT,
)

log = logging.getLogger("mikraw")

_local = threading.local()
# None = untested, True = working, False = known-failed (import or device).
# Set process-wide so failed workers don't retry on every file.
_cl_available: bool | None = None


def probe() -> bool:
    """Return True if an OpenCL device is reachable. Result cached per process."""
    global _cl_available
    if _cl_available is not None:
        return _cl_available
    try:
        import pyopencl as cl
        for platform in cl.get_platforms():
            if platform.get_devices(device_type=cl.device_type.GPU):
                _cl_available = True
                return True
        for platform in cl.get_platforms():
            if platform.get_devices(device_type=cl.device_type.CPU):
                _cl_available = True
                return True
    except Exception:
        pass
    _cl_available = False
    return False

_CL_SOURCE = r"""
#define PI_HALF 1.5707963267948966f

/* -----------------------------------------------------------------------
   1. Filmic tone curve  (in-place on flat H*W*3 float array)
   ----------------------------------------------------------------------- */
__kernel void k_filmic(
    __global float* rgb,
    const int      n,
    const float    shadow_lift,
    const float    contrast_str,
    const float    contrast_mult,
    const float    hi_rolloff
) {
    int i = get_global_id(0);
    if (i >= n) return;
    float x = rgb[i];

    /* Shadow lift: remap [0,1] → [shadow_lift, 1] */
    x = x * (1.0f - shadow_lift) + shadow_lift;

    /* Midtone S-curve */
    if (contrast_mult > 0.0f) {
        float g = 1.0f + fmax(contrast_str * contrast_mult, 0.0f);
        float xg = pow(x, g);
        float ig = pow(fmax(1.0f - x, 0.0f), g);
        x = xg / (xg + ig + 1e-12f);
    }

    /* Sine highlight shoulder */
    if (x > hi_rolloff) {
        float t = fmin((x - hi_rolloff) / (1.0f - hi_rolloff), 1.0f);
        x = hi_rolloff + (1.0f - hi_rolloff) * sin(t * PI_HALF);
    }

    rgb[i] = x;
}

/* -----------------------------------------------------------------------
   2a. Extract luma from interleaved RGB into a H*W float array
   ----------------------------------------------------------------------- */
__kernel void k_luma(
    __global const float* rgb,
    __global float*       luma,
    const int             npix
) {
    int i = get_global_id(0);
    if (i >= npix) return;
    luma[i] = 0.2126f * rgb[i*3]
             + 0.7152f * rgb[i*3+1]
             + 0.0722f * rgb[i*3+2];
}

/* -----------------------------------------------------------------------
   2b. Horizontal box blur (2D global: [W, H])
       Each work-item computes one output pixel by summing 2*radius+1 inputs.
       Edge: clamp-extend (mirrors numpy's mode="edge" pad).
   ----------------------------------------------------------------------- */
__kernel void k_blur_h(
    __global const float* in,
    __global float*       out,
    const int W, const int H, const int radius
) {
    int x = (int)get_global_id(0);
    int y = (int)get_global_id(1);
    if (x >= W || y >= H) return;

    float sum = 0.0f;
    const int k = 2 * radius + 1;
    const __global float* row = in + y * W;

    for (int dx = -radius; dx <= radius; dx++) {
        sum += row[clamp(x + dx, 0, W - 1)];
    }
    out[y * W + x] = sum / (float)k;
}

/* -----------------------------------------------------------------------
   2c. Vertical box blur (2D global: [W, H])
   ----------------------------------------------------------------------- */
__kernel void k_blur_v(
    __global const float* in,
    __global float*       out,
    const int W, const int H, const int radius
) {
    int x = (int)get_global_id(0);
    int y = (int)get_global_id(1);
    if (x >= W || y >= H) return;

    float sum = 0.0f;
    const int k = 2 * radius + 1;

    for (int dy = -radius; dy <= radius; dy++) {
        sum += in[clamp(y + dy, 0, H - 1) * W + x];
    }
    out[y * W + x] = sum / (float)k;
}

/* -----------------------------------------------------------------------
   2d. Apply local contrast: compute detail from two blur scales,
       tanh-clip it, and add the luma delta to all three RGB channels.
   ----------------------------------------------------------------------- */
__kernel void k_local_contrast(
    __global float*       rgb,
    __global const float* luma,
    __global const float* blur_fine,
    __global const float* blur_coarse,
    const int   npix,
    const float amount,
    const float clip
) {
    int i = get_global_id(0);
    if (i >= npix) return;

    float detail = 0.45f * (luma[i] - blur_fine[i])
                 + 0.55f * (luma[i] - blur_coarse[i]);
    detail = tanh(detail * clip) / clip;
    float delta = amount * detail;

    rgb[i*3  ] = fmin(fmax(rgb[i*3  ] + delta, 0.0f), 1.0f);
    rgb[i*3+1] = fmin(fmax(rgb[i*3+1] + delta, 0.0f), 1.0f);
    rgb[i*3+2] = fmin(fmax(rgb[i*3+2] + delta, 0.0f), 1.0f);
}

/* -----------------------------------------------------------------------
   3a. Vibrance with luma-preserving saturation + skin-tone protection
   ----------------------------------------------------------------------- */
__kernel void k_vibrance(
    __global float* rgb,
    const int   npix,
    const float sat_base,
    const float sat_vib,
    const float skin_protect,
    const float skin_hue_center,
    const float skin_hue_width
) {
    int i = get_global_id(0);
    if (i >= npix) return;

    float r = rgb[i*3  ];
    float g = rgb[i*3+1];
    float b = rgb[i*3+2];
    float luma = 0.2126f * r + 0.7152f * g + 0.0722f * b;

    float mx = fmax(r, fmax(g, b));
    float mn = fmin(r, fmin(g, b));
    float chroma = mx - mn;

    /* Hue in [0,1) */
    float hue = 0.0f;
    if (chroma > 1e-6f) {
        float h;
        if (mx == r) {
            h = fmod((g - b) / chroma, 6.0f);
            if (h < 0.0f) h += 6.0f;
        } else if (mx == g) {
            h = ((b - r) / chroma) + 2.0f;
        } else {
            h = ((r - g) / chroma) + 4.0f;
        }
        hue = fmod(h / 6.0f, 1.0f);
    }

    /* Skin weight (gaussian around skin hue) */
    float d = (hue - skin_hue_center) / skin_hue_width;
    float skin_w = exp(-d * d);

    /* Vibrance boost, tapered for already-saturated pixels */
    float boost = sat_base + sat_vib * (1.0f - chroma);
    boost *= (1.0f - skin_protect * skin_w);
    float factor = 1.0f + boost;

    rgb[i*3  ] = fmin(fmax(luma + (r - luma) * factor, 0.0f), 1.0f);
    rgb[i*3+1] = fmin(fmax(luma + (g - luma) * factor, 0.0f), 1.0f);
    rgb[i*3+2] = fmin(fmax(luma + (b - luma) * factor, 0.0f), 1.0f);
}

/* -----------------------------------------------------------------------
   3b. Monochrome: convert all channels to luminance (in-place)
   ----------------------------------------------------------------------- */
__kernel void k_monochrome(
    __global float* rgb,
    const int npix
) {
    int i = get_global_id(0);
    if (i >= npix) return;
    float luma = 0.2126f * rgb[i*3]
               + 0.7152f * rgb[i*3+1]
               + 0.0722f * rgb[i*3+2];
    rgb[i*3  ] = luma;
    rgb[i*3+1] = luma;
    rgb[i*3+2] = luma;
}

/* -----------------------------------------------------------------------
   4a. Quantize float [0,1] → uint8 (JPEG output)
   ----------------------------------------------------------------------- */
__kernel void k_quantize_u8(
    __global const float* in,
    __global uchar*       out,
    const int n
) {
    int i = get_global_id(0);
    if (i >= n) return;
    out[i] = (uchar)fmin(fmax(in[i] * 255.0f + 0.5f, 0.0f), 255.0f);
}

/* -----------------------------------------------------------------------
   4b. Quantize float [0,1] → uint16 (TIFF output)
   ----------------------------------------------------------------------- */
__kernel void k_quantize_u16(
    __global const float* in,
    __global ushort*      out,
    const int n
) {
    int i = get_global_id(0);
    if (i >= n) return;
    out[i] = (ushort)fmin(fmax(in[i] * 65535.0f + 0.5f, 0.0f), 65535.0f);
}
"""


_KERNEL_NAMES = (
    "k_filmic", "k_luma", "k_blur_h", "k_blur_v",
    "k_local_contrast", "k_vibrance", "k_monochrome",
    "k_quantize_u8", "k_quantize_u16",
)


def _get_cl():
    """Return (ctx, queue, kernels). Compiled once per thread/process."""
    if getattr(_local, "kernels", None) is None:
        import pyopencl as cl

        ctx = None
        device_name = "unknown"
        for platform in cl.get_platforms():
            gpus = platform.get_devices(device_type=cl.device_type.GPU)
            if gpus:
                ctx = cl.Context(gpus[:1])
                device_name = f"{platform.name.strip()} / {gpus[0].name.strip()}"
                break
        if ctx is None:
            for platform in cl.get_platforms():
                cpus = platform.get_devices(device_type=cl.device_type.CPU)
                if cpus:
                    ctx = cl.Context(cpus[:1])
                    device_name = f"{platform.name.strip()} / {cpus[0].name.strip()} (CPU)"
                    break
        if ctx is None:
            raise RuntimeError("No OpenCL platform or device found")

        log.debug("OpenCL device: %s", device_name)
        queue = cl.CommandQueue(ctx)
        program = cl.Program(ctx, _CL_SOURCE).build()
        # Pre-create all kernel objects once so repeated calls reuse the same
        # instance (avoids RepeatedKernelRetrieval warning and compile cost).
        kernels = SimpleNamespace(**{name: cl.Kernel(program, name) for name in _KERNEL_NAMES})
        _local.ctx = ctx
        _local.queue = queue
        _local.program = program  # keep Python wrapper alive so kernels stay valid
        _local.kernels = kernels

    return _local.ctx, _local.queue, _local.kernels


def _buf(ctx, flags, npix_floats: int = 0, nbytes: int = 0):
    """Shorthand: allocate a GPU buffer sized in float32 values or explicit bytes."""
    import pyopencl as cl
    size = nbytes if nbytes else npix_floats * 4
    return cl.Buffer(ctx, flags, size=size)


def try_apply_look(
    arr16: np.ndarray,
    contrast_mult: float,
    saturation_mult: float,
    clarity_mult: float,
    monochrome: bool,
    bits: int,
) -> Optional[np.ndarray]:
    """GPU develop path. Returns a (H,W,3) uint8 or uint16 array, or None on failure."""
    global _cl_available
    if _cl_available is False:
        return None  # known-failed this process; skip without retrying
    try:
        import pyopencl as cl

        ctx, queue, k = _get_cl()
        mf = cl.mem_flags

        H, W, _ = arr16.shape
        npix = H * W
        n = npix * 3

        # Upload input: convert uint16 → float32 [0,1].
        rgb_host = np.ascontiguousarray(arr16, dtype=np.float32) * np.float32(1.0 / 65535.0)
        rgb_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=rgb_host)

        # ------------------------------------------------------------------
        # 1. Filmic tone curve.
        # ------------------------------------------------------------------
        k.k_filmic(queue, (n,), None,
                      rgb_buf, np.int32(n),
                      np.float32(SHADOW_LIFT),
                      np.float32(CONTRAST_STRENGTH),
                      np.float32(contrast_mult),
                      np.float32(HIGHLIGHT_ROLLOFF))

        # ------------------------------------------------------------------
        # 2. Local contrast (optional — skip when clarity_mult <= 0).
        # ------------------------------------------------------------------
        amount = LOCAL_CONTRAST * clarity_mult
        if amount > 0.0:
            coarse_r = max(2, int(round(min(H, W) * LOCAL_CONTRAST_RADIUS)))
            fine_r = max(1, coarse_r // 3)

            # Extract luma.
            luma_buf = _buf(ctx, mf.READ_WRITE, npix)
            k.k_luma(queue, (npix,), None, rgb_buf, luma_buf, np.int32(npix))

            gsize = (W, H)

            # Fine blur: 2 passes of separable box blur from luma_buf.
            # We need luma_buf to stay unmodified throughout, so all blur
            # passes read from either luma_buf or a ping-pong temp.
            buf_a = _buf(ctx, mf.READ_WRITE, npix)
            buf_b = _buf(ctx, mf.READ_WRITE, npix)

            # Fine pass 1: luma_buf → buf_a (H), buf_a → buf_b (V)
            k.k_blur_h(queue, gsize, None, luma_buf, buf_a, np.int32(W), np.int32(H), np.int32(fine_r))
            k.k_blur_v(queue, gsize, None, buf_a, buf_b, np.int32(W), np.int32(H), np.int32(fine_r))
            # Fine pass 2: buf_b → buf_a (H), buf_a → buf_b (V) → fine_blurred = buf_b
            k.k_blur_h(queue, gsize, None, buf_b, buf_a, np.int32(W), np.int32(H), np.int32(fine_r))
            k.k_blur_v(queue, gsize, None, buf_a, buf_b, np.int32(W), np.int32(H), np.int32(fine_r))
            fine_blurred = buf_b

            # Coarse blur: 2 passes from luma_buf; reuse buf_a as temp.
            buf_c = _buf(ctx, mf.READ_WRITE, npix)

            k.k_blur_h(queue, gsize, None, luma_buf, buf_a, np.int32(W), np.int32(H), np.int32(coarse_r))
            k.k_blur_v(queue, gsize, None, buf_a, buf_c, np.int32(W), np.int32(H), np.int32(coarse_r))
            k.k_blur_h(queue, gsize, None, buf_c, buf_a, np.int32(W), np.int32(H), np.int32(coarse_r))
            k.k_blur_v(queue, gsize, None, buf_a, buf_c, np.int32(W), np.int32(H), np.int32(coarse_r))
            coarse_blurred = buf_c

            k.k_local_contrast(queue, (npix,), None,
                                   rgb_buf, luma_buf, fine_blurred, coarse_blurred,
                                   np.int32(npix),
                                   np.float32(amount),
                                   np.float32(LOCAL_CONTRAST_CLIP))

        # ------------------------------------------------------------------
        # 3. Vibrance or monochrome.
        # ------------------------------------------------------------------
        if monochrome:
            k.k_monochrome(queue, (npix,), None, rgb_buf, np.int32(npix))
        else:
            k.k_vibrance(queue, (npix,), None,
                            rgb_buf, np.int32(npix),
                            np.float32(SATURATION_BASE * saturation_mult),
                            np.float32(SATURATION_VIBRANCE * saturation_mult),
                            np.float32(SKIN_PROTECT),
                            np.float32(SKIN_HUE_CENTER),
                            np.float32(SKIN_HUE_WIDTH))

        # ------------------------------------------------------------------
        # 4. Quantize and download.
        # ------------------------------------------------------------------
        if bits == 16:
            out_buf = _buf(ctx, mf.WRITE_ONLY, nbytes=n * 2)
            k.k_quantize_u16(queue, (n,), None, rgb_buf, out_buf, np.int32(n))
            out_host = np.empty(n, dtype=np.uint16)
        else:
            out_buf = _buf(ctx, mf.WRITE_ONLY, nbytes=n)
            k.k_quantize_u8(queue, (n,), None, rgb_buf, out_buf, np.int32(n))
            out_host = np.empty(n, dtype=np.uint8)

        cl.enqueue_copy(queue, out_host, out_buf)
        queue.finish()
        _cl_available = True
        return out_host.reshape(H, W, 3)

    except Exception as exc:
        if _cl_available is None:  # first failure — warn once per process
            log.warning("GPU develop unavailable (%s); falling back to CPU", type(exc).__name__)
        _cl_available = False
        return None
