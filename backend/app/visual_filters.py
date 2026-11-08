"""Per-category maximum-strength sharpening. RGB Gaussian 3x3; alpha preserved."""

import numpy as np
from PIL import Image


def strength_at(filters, target, frame):
    return max(
        (
            f["strength"]
            for f in filters
            if target in f["targets"] and f["start"] <= frame < f["end"]
        ),
        default=0,
    )


def intervals(filters, target):
    chosen = [f for f in filters if target in f["targets"] and f["strength"] > 0]
    points = sorted({p for f in chosen for p in (f["start"], f["end"])})
    out = []
    for a, b in zip(points, points[1:]):
        strength = strength_at(chosen, target, a)
        if not strength:
            continue
        if out and out[-1][1] == a and out[-1][2] == strength:
            out[-1] = (out[-1][0], b, strength)
        else:
            out.append((a, b, strength))
    return out


def ffmpeg_filters(filters, target, offset=0):
    out = []
    for a, b, s in intervals(filters, target):
        matrix = f"{-s} {-2 * s} {-s} {-2 * s} {1600 + 12 * s} {-2 * s} {-s} {-2 * s} {-s}"
        params = ":".join(f"{i}m='{matrix}':{i}rdiv=0.000625" for i in range(3))
        # RGB processing prevents chroma-only/luma-only differences from the preview shader.
        out.append(
            f"format=gbrp,convolution={params}:enable='gte(n+{offset},{a})*lt(n+{offset},{b})'"
        )
    return ",".join(out)


def sharpen_image(image, strength):
    if not strength:
        return image
    pixels = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = pixels[:, :, 3:4] / 255
    rgb = pixels[:, :, :3]
    premult = rgb * alpha
    pad = np.pad(premult, ((1, 1), (1, 1), (0, 0)), mode="edge")
    apad = np.pad(alpha, ((1, 1), (1, 1), (0, 0)), mode="edge")
    blur = np.zeros_like(premult)
    weight = np.zeros_like(alpha)
    h, w = alpha.shape[:2]
    for y in range(3):
        for x in range(3):
            k = (2 if y == 1 else 1) * (2 if x == 1 else 1) / 16
            blur += pad[y : y + h, x : x + w] * k
            weight += apad[y : y + h, x : x + w] * k
    blurred = np.divide(blur, weight, out=rgb.copy(), where=weight > 0)
    pixels[:, :, :3] = np.clip(np.floor(rgb + (strength / 100) * (rgb - blurred) + 0.5), 0, 255)
    return Image.fromarray(pixels.astype(np.uint8), "RGBA")
