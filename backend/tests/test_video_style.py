import pytest
from app import review
from app.review import ApprovalBatch
from app.subtitle_presentation import change_points
from app.subtitle_templates import motion_at, text_image
from app.timeline import VisualStyle
from app.video_preferences import read
from pydantic import ValidationError
from test_review_workflow import configure, data, proposal  # noqa: F401

CAPTION = {
    "id": "c",
    "start": 0,
    "end": 90,
    "words": [
        {"id": "a", "text": "Aku", "start": 0, "end": 30},
        {"id": "b", "text": "suka", "start": 30, "end": 60},
        {"id": "c", "text": "kamu", "start": 60, "end": 90},
    ],
}


@pytest.mark.parametrize(
    "mode", ["sentence", "word", "background", "reveal", "reveal_up", "karaoke", "karaoke_active"]
)
def test_templates_have_ink_and_preserve_input(mode):
    style = VisualStyle(subtitle_version=1, subtitle_template=mode).model_dump()
    assert text_image(CAPTION, style, 45, 640, 360).getbbox()
    assert CAPTION["words"][1]["start"] == 30


def test_reveal_keeps_layout_and_word_mode_has_gaps():
    style = VisualStyle(subtitle_version=1, subtitle_template="reveal").model_dump()
    first = text_image(CAPTION, style, 15, 640, 360).getbbox()
    last = text_image(CAPTION, style, 80, 640, 360).getbbox()
    assert first[0] == last[0]
    assert first[2] < last[2]
    style["subtitle_template"] = "word"
    caption = {**CAPTION, "words": [CAPTION["words"][0]]}
    assert text_image(caption, style, 40, 640, 360).getbbox() is None


@pytest.mark.parametrize("motion", ["none", "fade", "zoom", "zoom_fade", "down", "down_fade"])
def test_motion_stays_inside_unit(motion):
    middle = motion_at(0, 90, 45, motion)
    assert middle == {"opacity": 1, "scale": 1, "dy": 0}
    for frame in range(90):
        state = motion_at(0, 90, frame, motion)
        assert 0 <= state["opacity"] <= 1
        assert 0.96 <= state["scale"] <= 1
        assert -0.12 <= state["dy"] <= 0.12


def test_modern_animated_change_points_and_legacy_defaults():
    modern = VisualStyle(subtitle_version=1, subtitle_template="background").model_dump()
    assert len(change_points(CAPTION, modern)) == 91
    assert VisualStyle().subtitle_version is None
    with pytest.raises(ValidationError):
        VisualStyle(subtitle_template="unknown")
    with pytest.raises(ValidationError):
        VisualStyle(background="javascript:bad")


def test_preferences_only_change_on_fresh_single_explicit_approval(data):  # noqa: F811
    factory, pid, _ = data
    with factory() as s:
        assert read(s)["revision"] == 0
        p = proposal(s, pid)
        style = VisualStyle(subtitle_version=1, subtitle_template="background").model_dump()
        configured = configure(s, p, subtitle_style=style)
        assert read(s)["revision"] == 0
        body = ApprovalBatch(
            items=[{"id": p.id, "revision": configured["revision"]}], remember_style=True
        )
        review.process(pid, body, s)
        assert read(s)["revision"] == 1
        assert read(s)["style"]["subtitle_style"]["subtitle_template"] == "background"
        review.process(pid, body, s)
        assert read(s)["revision"] == 1
        p2 = proposal(s, pid, 1800, 3000)
        configured2 = configure(s, p2, subtitle_style=style)
        review.process(
            pid, ApprovalBatch(items=[{"id": p2.id, "revision": configured2["revision"]}]), s
        )
        assert read(s)["revision"] == 1


def test_build_inherits_style_and_manual_insertion_defaults(data, monkeypatch):
    from app import subtitle_refinement, editor_assets, review_build
    from app.db import Job, Clip
    from app.video_preferences import TransitionDefaults

    factory, pid, _ = data
    monkeypatch.setattr(subtitle_refinement, "refine", lambda *a, **k: {"words": []})
    monkeypatch.setattr(editor_assets, "prepare_editor", lambda *a, **k: None)
    with factory() as s:
        p = proposal(s, pid)
        style = VisualStyle(subtitle_version=1, subtitle_template="background").model_dump()
        transitions = TransitionDefaults(
            incoming={"kind": "flash", "frames": 12, "sound": "camera_shutter"}
        ).model_dump()
        configured = configure(s, p, subtitle_style=style, transition_defaults=transitions)
        result = review.process(
            pid, ApprovalBatch(items=[{"id": p.id, "revision": configured["revision"]}]), s
        )
        job = s.get(Job, result[0]["id"])
        payload = job.payload
        jid = job.id
    built = review_build.build(jid, pid, payload, lambda: None)
    with factory() as s:
        clip = s.get(Clip, built["clip_id"])
        assert clip.plan["subtitle_style"]["subtitle_template"] == "background"
        assert clip.processing_config["transition_defaults"]["outgoing"]["kind"] == "flash"
        assert (
            clip.processing_config["transition_defaults"]["outgoing"]["sound"] == "camera_shutter"
        )


def test_synchronized_transition_defaults_are_normalized():
    from app.video_preferences import TransitionDefaults

    defaults = TransitionDefaults(
        incoming={"kind": "flash", "frames": 12}, outgoing={"kind": "none", "frames": 0}
    )
    assert defaults.incoming == defaults.outgoing


def test_reveal_directions_have_same_end_position():
    from PIL import ImageChops

    caption = {**CAPTION, "words": [CAPTION["words"][0]]}
    down = VisualStyle(subtitle_version=1, subtitle_template="reveal").model_dump()
    up = {**down, "subtitle_template": "reveal_up"}
    early_down = text_image(caption, down, 4, 1080, 810).getbbox()
    early_up = text_image(caption, up, 4, 1080, 810).getbbox()
    assert early_down[1] < early_up[1]
    assert (
        ImageChops.difference(
            text_image(caption, down, 15, 1080, 810), text_image(caption, up, 15, 1080, 810)
        ).getbbox()
        is None
    )


def test_active_karaoke_only_colors_current_word_and_resets_during_gap():
    from PIL import ImageChops

    words = [dict(w) for w in CAPTION["words"]]
    words[0]["end"] = 20
    caption = {**CAPTION, "words": words}
    style = VisualStyle(
        subtitle_version=1,
        subtitle_template="karaoke_active",
        color="#FFFFFF",
        highlight="#FF0000",
        outline=0,
    ).model_dump()
    plain = {**style, "subtitle_template": "sentence"}
    gap = text_image(caption, style, 25, 1080, 810)
    assert ImageChops.difference(gap, text_image(caption, plain, 25, 1080, 810)).getbbox() is None
    second = text_image(caption, style, 40, 1080, 810)
    changed = (
        ImageChops.difference(second, text_image(caption, plain, 40, 1080, 810))
        .convert("RGB")
        .getbbox()
    )
    assert changed is not None
    # First word remains white; changed pixels only occupy the second word.
    assert changed[0] > second.getbbox()[0] + 100


def test_smoother_curve_has_flat_endpoints_and_longer_phase():
    from app.subtitle_templates import ease

    assert abs(ease(0.001) - ease(0)) < 0.000001
    assert abs(ease(1) - ease(0.999)) < 0.000001
    assert motion_at(0, 90, 0, "fade")["opacity"] == 0.7
    assert motion_at(0, 90, 3, "fade")["opacity"] == 1
    assert motion_at(0, 90, 6, "zoom")["scale"] < 1
    assert motion_at(0, 90, 9, "zoom")["scale"] == 1


@pytest.mark.parametrize("duration", [1, 2, 3, 6, 9, 30])
def test_fade_is_readable_at_onset_and_only_exits_at_end(duration):
    from app.subtitle_templates import readable_at

    assert readable_at(0, duration, 0) >= 0.7
    if duration < 3:
        assert all(readable_at(0, duration, f) == 1 for f in range(duration))
    else:
        phase = min(3, duration // 3)
        assert readable_at(0, duration, duration - 1) == 0
        for frame in range(phase, duration - 1 - phase + 1):
            assert readable_at(0, duration, frame) == 1


@pytest.mark.parametrize("mode", ["reveal", "reveal_up"])
def test_reveal_and_group_fade_do_not_multiply_opacity(mode):
    caption = {**CAPTION, "words": [CAPTION["words"][0]]}
    style = VisualStyle(
        subtitle_version=1, subtitle_template=mode, subtitle_motion="fade", opacity=0.5, outline=0
    ).model_dump()
    image = text_image(caption, style, 0, 1080, 810)
    # 70% onset * the user's 50% opacity, applied once (not 70% squared).
    assert 88 <= image.getchannel("A").getextrema()[1] <= 90


@pytest.mark.parametrize("font", ["DejaVu Sans", "Liberation Sans", "Poppins"])
def test_words_share_font_baseline_and_background_covers_descenders(font, monkeypatch):
    from PIL import ImageDraw

    calls = []
    original = ImageDraw.ImageDraw.text

    def capture(self, xy, text, *args, **kwargs):
        calls.append((xy, text, kwargs.get("anchor")))
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capture)
    caption = {
        "id": "mixed",
        "start": 0,
        "end": 180,
        "words": [
            {"id": str(i), "text": word, "start": i * 30, "end": (i + 1) * 30}
            for i, word in enumerate(["game", "global", "yang", "lebih", "besar", "ÉPAgy"])
        ],
    }
    style = VisualStyle(subtitle_version=1, font=font, size=40, width=0.95, outline=0).model_dump()
    text_image(caption, style, 15, 1920, 1080)
    assert len({xy[1] for xy, _, _ in calls}) == 1
    assert all(anchor == "ls" for _, _, anchor in calls)
    calls.clear()
    style.update(width=0.35, size=62)
    text_image(caption, style, 15, 1080, 810)
    rows = sorted({xy[1] for xy, _, _ in calls})
    assert len(rows) > 1
    assert all(abs(b - a - 62 * 1.25) < 0.001 for a, b in zip(rows, rows[1:]))
    style.update(subtitle_template="background", width=0.95)
    calls.clear()
    rectangles = []
    original_rectangle = ImageDraw.ImageDraw.rounded_rectangle

    def rectangle(self, xy, *args, **kwargs):
        rectangles.append(xy)
        return original_rectangle(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", rectangle)
    image = text_image(caption, style, 15, 1080, 810)
    from app.subtitle_templates import font_for

    bbox = font_for(font, 62).getbbox("game", anchor="ls")
    baseline = calls[0][0][1]
    assert rectangles[0][1] < baseline + bbox[1]
    assert rectangles[0][3] > baseline + bbox[3]
    assert image.getbbox()


def test_two_frame_background_word_is_highlighted_immediately(monkeypatch):
    from PIL import ImageDraw

    caption = {**CAPTION, "words": [CAPTION["words"][0], {**CAPTION["words"][1], "end": 32}]}
    style = VisualStyle(subtitle_version=1, subtitle_template="background").model_dump()
    rectangles = []
    original = ImageDraw.ImageDraw.rounded_rectangle

    def capture(self, xy, *args, **kwargs):
        rectangles.append(xy)
        return original(self, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", capture)
    text_image(caption, style, 30, 1080, 810)
    text_image(caption, style, 31, 1080, 810)
    assert rectangles[0] == rectangles[1]
