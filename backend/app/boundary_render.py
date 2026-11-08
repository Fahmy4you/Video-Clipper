"""Render transition windows over hard cuts without changing timeline/audio length."""

import math, json
from .boundaries import events
from .media import run
from . import mix_render
from .visual_filters import ffmpeg_filters


def framing(t, w, h):
    ph = h // 2 if t["mode"] == "split" else h

    def pane(x):
        mode = "decrease" if t["mode"] == "fit" else "increase"
        sw = math.ceil(w * t["scale"] / 2) * 2
        sh = math.ceil(ph * t["scale"] / 2) * 2
        xpos = f"max(0,min(iw-ow,iw*{x}-ow/2))" if t.get("legacy_center") else f"(iw-ow)*{x}"
        return f"format=rgba,scale={sw}:{sh}:force_original_aspect_ratio={mode}:force_divisible_by=2,pad=max(iw\\,{w}):max(ih\\,{ph}):(ow-iw)*{x if not t.get('legacy_center') else 0.5}:(oh-ih)*{t['y']}:black,crop={w}:{ph}:exact=1:x='{xpos}':y='(ih-oh)*{t['y']}',setsar=1,format=rgba"

    if t["mode"] == "split":
        return f"[0:v]fps=30,setpts=PTS-STARTPTS,split=2[a][b];[a]{pane(t['x'])}[top];[b]{pane(t['b'])}[bottom];[top][bottom]vstack[v]"
    return f"[0:v]fps=30,setpts=PTS-STARTPTS,{pane(t['x'])}[v]"


def apply(base, source, plan, out, w, h, source_frames, check):
    limits = {"podcast": source_frames}
    for s in plan["segments"]:
        for b in s.get("broll", []):
            limits[b["asset_id"]] = json.loads(
                (mix_render.folder(b["asset_id"]) / "metadata.json").read_text()
            )["frames"]
    selected = [
        e for e in events(plan, limits) if e["half"] and e["kind"] in ("black", "crossfade")
    ]
    if not selected:
        return base
    args = ["ffmpeg", "-y", "-v", "error", "-threads", "2", "-i", str(base)]
    filters = []
    label = "0:v"
    for index, event in enumerate(selected, 1):
        f = event["frame"]
        half = event["half"]
        a = f - half
        b = f + half
        length = half * 2
        patch = out.parent / f"transition-{index}.mkv"
        if event["kind"] == "black":
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    str(a / 30),
                    "-i",
                    str(base),
                    "-an",
                    "-filter_complex_threads",
                    "1",
                    "-filter_complex",
                    f"[0:v]fps=30,setpts=PTS-STARTPTS,split=2[a][b];[a]trim=end_frame={half},fade=t=out:st=0:d={half / 30}[out];[b]trim=start_frame={half},setpts=PTS-STARTPTS,fade=t=in:st=0:d={half / 30}[in];[out][in]concat=n=2:v=1:a=0[v]",
                    "-map",
                    "[v]",
                    "-frames:v",
                    str(length),
                    "-c:v",
                    "libx264",
                    "-threads",
                    "2",
                    "-crf",
                    "18",
                    str(patch),
                ],
                check,
            )
        else:
            sides = []
            for k, span in enumerate((event["before"], event["after"])):
                media = (
                    source
                    if span["kind"] == "podcast"
                    else mix_render.folder(span["asset_id"]) / "source.media"
                )
                vf = framing(span["transform"], w, h)
                chain = ffmpeg_filters(plan.get("filters", []), span["kind"], a)
                if chain:
                    vf = vf.replace("[v]", "[raw]") + ";[raw]" + chain + "[v]"
                target = out.parent / f"transition-{index}-{k}.mkv"
                start = (span["source_in"] + a - span["start"]) / 30
                run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-threads",
                        "2",
                        "-ss",
                        str(start),
                        "-i",
                        str(media),
                        "-filter_complex_threads",
                        "1",
                        "-filter_complex",
                        vf,
                        "-map",
                        "[v]",
                        "-an",
                        "-frames:v",
                        str(length),
                        "-c:v",
                        "libx264",
                        "-threads",
                        "2",
                        "-crf",
                        "18",
                        "-pix_fmt",
                        "yuv420p",
                        str(target),
                    ],
                    check,
                )
                sides.append(target)
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(sides[0]),
                    "-i",
                    str(sides[1]),
                    "-filter_complex_threads",
                    "1",
                    "-filter_complex",
                    f"[0:v]settb=1/30,setpts=N[a];[1:v]settb=1/30,setpts=N[b];[a][b]blend=all_expr='A*(1-(N-1)/{length})+B*(N-1)/{length}'[v]",
                    "-map",
                    "[v]",
                    "-an",
                    "-frames:v",
                    str(length),
                    "-c:v",
                    "libx264",
                    "-threads",
                    "2",
                    "-crf",
                    "18",
                    str(patch),
                ],
                check,
            )
        args += ["-i", str(patch)]
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS+{a}/30/TB[t{index}]")
        dest = f"v{index}"
        filters.append(
            f"[{label}][t{index}]overlay=enable='gte(t,{a / 30})*lt(t,{b / 30})':eof_action=pass[{dest}]"
        )
        label = dest
    run(
        args
        + [
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{label}]",
            "-map",
            "0:a",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(out),
        ],
        check,
    )
    return out
