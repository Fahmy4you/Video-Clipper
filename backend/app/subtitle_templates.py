"""Modern subtitle rasterizer. Timing and easing mirror subtitleTemplates.ts."""

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=32)
def font_for(name, size):
    from .render_v2 import FONTS

    return ImageFont.truetype(str(FONTS[name]), size)


@lru_cache(maxsize=4096)
def text_width(name, size, text):
    return font_for(name, size).getlength(text)


def ease(x):
    x = max(0, min(1, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def readable_at(start, end, frame, exit=True):
    phase = min(3, (end - start) // 3)
    if not phase:
        return 1
    entering = 0.7 + 0.3 * ease((frame - start) / phase)
    leaving = ease((end - 1 - frame) / phase) if exit else 1
    return min(entering, leaving)


def motion_at(start, end, frame, motion):
    phase = min(9, (end - start) // 3)
    entering = ease((frame - start) / phase) if phase else 1
    leaving = ease((end - 1 - frame) / phase) if phase else 1
    gain = min(entering, leaving)
    return {
        "opacity": readable_at(start, end, frame) if "fade" in motion else 1,
        "scale": 0.96 + 0.04 * gain if "zoom" in motion else 1,
        "dy": 0.12 * (1 - leaving if leaving < 1 else entering - 1) if "down" in motion else 0,
    }


def text_image(caption, style, frame, w, h):
    mode = style.get("subtitle_template") or "sentence"
    words = caption["words"]
    active = next((i for i, x in enumerate(words) if x["start"] <= frame < x["end"]), -1)
    canvas = Image.new("RGBA", (w, h))
    if mode == "word":
        if active < 0:
            return canvas
        words = [words[active]]
    unit = words[0] if mode == "word" else caption
    group = motion_at(unit["start"], unit["end"], frame, style.get("subtitle_motion", "none"))
    size = max(1, int(style["size"] * w / 1080 + 0.5))
    font = font_for(style["font"], size)
    _, top, _, bottom = font.getbbox("ÁÉHgyp", anchor="ls")
    ascent, descent = -top, bottom
    space = text_width(style["font"], size, " ")
    limit = style["width"] * w
    lines = [[]]
    width = 0
    for index, word in enumerate(words):
        for j, text in enumerate(word["text"].split("\n")):
            if j:
                lines.append([])
                width = 0
            tw = text_width(style["font"], size, text)
            if lines[-1] and width + space + tw > limit:
                lines.append([])
                width = 0
            if lines[-1]:
                width += space
            lines[-1].append(dict(text=text, width=tw, word=word, index=index))
            width += tw
    boxes = []
    for row, line in enumerate(lines):
        tw = sum(b["width"] for b in line) + space * max(0, len(line) - 1)
        x = (
            -tw / 2
            if style["align"] == "center"
            else -limit / 2
            if style["align"] == "left"
            else limit / 2 - tw
        )
        y = -len(lines) * size * 1.25 / 2 + row * size * 1.25 + size * 0.1
        for b in line:
            boxes.append(dict(**b, x=x + style["x"] * w, y=y + ascent + style["y"] * h, row=row))
            x += b["width"] + space
    if mode == "background" and active >= 0:
        target = next((b for b in boxes if b["index"] == active), None)
        previous = next((b for b in boxes if b["index"] == active - 1), None)
        if target:
            duration = target["word"]["end"] - target["word"]["start"]
            phase = 0 if duration < 3 else min(3, duration - 1)
            t = (
                1 - (1 - max(0, min(1, (frame - target["word"]["start"]) / phase))) ** 3
                if phase
                else 1
            )
            same = (
                previous
                and previous["row"] == target["row"]
                and previous["word"]["end"] == target["word"]["start"]
            )
            x = previous["x"] + (target["x"] - previous["x"]) * t if same else target["x"]
            tw = (
                previous["width"] + (target["width"] - previous["width"]) * t
                if same
                else target["width"]
            )
            layer = Image.new("RGBA", (w, h))
            ld = ImageDraw.Draw(layer)
            ld.rounded_rectangle(
                (
                    x - size * 0.12,
                    target["y"] - ascent - size * 0.08,
                    x + tw + size * 0.12,
                    target["y"] + descent + size * 0.08,
                ),
                radius=size * 0.15,
                fill=style.get("background", "#FACC15"),
            )
            background_alpha = group["opacity"]
            if previous and previous["row"] != target["row"]:
                background_alpha *= t
            if background_alpha != 1:
                layer.putalpha(layer.getchannel("A").point(lambda p: round(p * background_alpha)))
            canvas.alpha_composite(layer)
    for box in boxes:
        word = box["word"]
        if mode in ("reveal", "reveal_up") and frame < word["start"]:
            continue
        phase = max(0, min(9, word["end"] - word["start"] - 1))
        t = (
            ease((frame - word["start"]) / phase)
            if mode in ("reveal", "reveal_up") and phase
            else 1
        )
        layer = Image.new("RGBA", (w, h))
        ld = ImageDraw.Draw(layer)
        ld.text(
            (box["x"], box["y"] + (1 if mode == "reveal_up" else -1) * (1 - t) * size * 0.12),
            box["text"],
            font=font,
            fill=style["highlight"]
            if (mode == "karaoke" and frame >= word["start"])
            or (mode == "karaoke_active" and box["index"] == active)
            else style["color"],
            stroke_width=round(style["outline"] * w / 1080),
            stroke_fill="#101010",
            anchor="ls",
        )
        word_opacity = (
            readable_at(word["start"], word["end"], frame, exit=False)
            if mode in ("reveal", "reveal_up")
            else 1
        )
        opacity = min(group["opacity"], word_opacity)
        if opacity != 1:
            layer.putalpha(layer.getchannel("A").point(lambda p: round(p * opacity)))
        canvas.alpha_composite(layer)
    scale = group["scale"]
    cx, cy = style["x"] * w, style["y"] * h
    if scale != 1 or group["dy"]:
        canvas = canvas.transform(
            (w, h),
            Image.Transform.AFFINE,
            (
                1 / scale,
                0,
                cx - cx / scale,
                0,
                1 / scale,
                cy - cy / scale - group["dy"] * size / scale,
            ),
            Image.Resampling.BICUBIC,
        )
    if style["rotation"]:
        canvas = canvas.rotate(
            -style["rotation"], resample=Image.Resampling.BICUBIC, center=(cx, cy)
        )
    alpha = style["opacity"]
    if alpha != 1:
        canvas.putalpha(canvas.getchannel("A").point(lambda p: round(p * alpha)))
    return canvas
