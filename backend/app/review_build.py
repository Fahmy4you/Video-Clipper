"""Build one approved highlight without extending its source bounds."""

import json
from sqlalchemy import select
from .db import Session, HighlightProposal, Project, Clip, Job
from .media import project_dir, Cancelled
from .timeline import upgrade_plan
from .schemas import EditPlan


def build(jid, pid, payload, check):
    from .tasks import update, words_for_clip
    from .subtitle_refinement import refine, fresh_captions
    from .editor_assets import prepare_editor
    from .mix_generation import generate_mix

    folder = project_dir(pid)
    start = payload["start"] / 30
    end = payload["end"] / 30
    with Session() as s:
        p = s.get(HighlightProposal, payload["proposal_id"])
        if not p or p.job_id != jid or p.revision != payload["proposal_revision"]:
            raise Cancelled()
        project = s.get(Project, pid)
        duration = project.duration
    from .source_cache import prepare

    prepare(pid, folder, project.url, True, check, lambda **kw: update(jid, **kw))
    transcript = json.loads((folder / "transcript.json").read_text())
    update(jid, stage="Memperbaiki subtitle bagian disetujui", progress=10)
    refined = refine(
        folder / "source.mp4",
        duration,
        [(start, end)],
        check,
        lambda **kw: update(jid, **kw),
        jid,
        transcript.get("language"),
    )
    check()
    with Session() as s:
        s.execute(select(Project).where(Project.id == pid).with_for_update()).scalar_one()
        p = s.scalar(
            select(HighlightProposal)
            .where(HighlightProposal.id == payload["proposal_id"])
            .with_for_update()
        )
        if not p or p.job_id != jid:
            raise Cancelled()
        c = s.get(Clip, p.clip_id) if p.clip_id else None
        if c is None:
            plan = upgrade_plan(
                EditPlan(
                    start=start,
                    end=end,
                    words=words_for_clip(transcript["words"], start, end),
                    layouts=[{"start": 0, "mode": "a", "a": 0.5, "b": 0.7}],
                ).model_dump(),
                p.id,
            )
            # Preserve approved frame boundaries exactly.
            plan["segments"][0]["source_in"] = payload["start"]
            plan["segments"][0]["duration"] = payload["end"] - payload["start"]
            plan["subtitle_style"].update(
                subtitle_mode=payload["subtitle_mode"],
                subtitle_animation=payload["subtitle_animation"],
            )
            for segment in plan["segments"]:
                improved = fresh_captions(segment, refined["words"])
                if improved:
                    segment["captions"] = improved
            c = Clip(
                project_id=pid,
                title=payload["title"],
                reason=payload["summary"] or payload["reason"],
                plan=plan,
                fulfills_prompt=p.fulfills_prompt,
                aspect_ratio=payload["aspect_ratio"],
                ready=False,
                processing_config={
                    k: payload.get(k)
                    for k in (
                        "visual_mode",
                        "subtitle_mode",
                        "subtitle_animation",
                        "include_global",
                        "mix_hashtags",
                        "mix_max_per_minute",
                    )
                },
                instansi_records=list(p.instansi_records),
            )
            s.add(c)
            s.flush()
            p.clip_id = c.id
        job = s.get(Job, jid)
        job.clip_id = c.id
        cid = c.id
        s.commit()
    if payload["visual_mode"] == "mix":
        update(jid, stage="Menyusun video sisipan", progress=75)
        generate_mix(jid, pid, {**payload, "mix_target_ids": [cid]}, check)
    check()
    update(jid, stage="Menyiapkan media studio", progress=90)
    prepare_editor(folder, check)
    check()
    with Session() as s:
        s.execute(select(Project).where(Project.id == pid).with_for_update()).scalar_one()
        p = s.scalar(
            select(HighlightProposal)
            .where(HighlightProposal.id == payload["proposal_id"])
            .with_for_update()
        )
        if not p or p.job_id != jid:
            raise Cancelled()
        c = s.get(Clip, cid)
        c.ready = True
        s.commit()
    return {"clip_id": cid, "message": "Highlight siap dibuka di studio."}
