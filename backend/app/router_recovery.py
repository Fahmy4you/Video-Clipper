"""Explicit migration of interrupted jobs to a user-selected combo."""

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .db import session, Project, Job, Clip, HighlightProposal
from .schemas import ModelSelection, JobView
from .router_ai import validate_model
from .queue_runtime import public_job, wake
from .proposal_searches import enqueue_search, SearchInput

router = APIRouter(prefix="/api")


def recovery_target(job):
    if job.kind == "build_highlight":
        return job.kind, job.payload.get("proposal_id") or job.clip_id or job.id
    return job.kind, job.clip_id


@router.post("/jobs/{id}/router", status_code=202, response_model=JobView)
def resume(id: str, body: ModelSelection, s=Depends(session)):
    prior = s.get(Job, id)
    if prior is None or prior.project_id is None:
        raise HTTPException(404, "Pekerjaan proyek tidak ditemukan.")
    project = s.scalar(select(Project).where(Project.id == prior.project_id).with_for_update())
    prior = s.scalar(select(Job).where(Job.id == id).with_for_update())
    successor = (prior.result or {}).get("successor_job_id")
    if successor:
        fresh = s.get(Job, successor)
        if fresh is None:
            raise HTTPException(
                409,
                "Pekerjaan penerus sudah tidak tersedia. Buka proyek untuk membuat permintaan baru.",
            )
        return public_job(s, fresh)
    if prior.kind not in ("analysis", "mix", "build_highlight"):
        raise HTTPException(409, "Jenis pekerjaan ini tidak memerlukan migrasi ke 9Router.")
    if prior.payload.get("provider") == "9router":
        raise HTTPException(
            409,
            "Pekerjaan ini sudah menggunakan 9Router. Gunakan percobaan ulang pekerjaan terbaru.",
        )
    if prior.status in ("running", "cancelling") or prior.owner_token:
        raise HTTPException(
            409, "Batalkan dan tunggu worker berhenti sebelum mengganti koneksi pekerjaan."
        )
    if prior.status == "succeeded":
        raise HTTPException(409, "Pekerjaan sudah selesai.")

    attempts = s.scalars(
        select(Job)
        .where(Job.project_id == prior.project_id, Job.kind == prior.kind)
        .order_by(Job.created_at.desc(), Job.id.desc())
    )
    latest = next(job for job in attempts if recovery_target(job) == recovery_target(prior))
    if latest.id != prior.id:
        raise HTTPException(
            409,
            "Percobaan lama ini sudah digantikan pekerjaan yang lebih baru. "
            "Gunakan pekerjaan terbaru atau tambah usulan baru dari transkrip tersimpan.",
        )
    if prior.kind == "build_highlight":
        proposal = s.get(HighlightProposal, prior.payload.get("proposal_id"))
        clip = s.get(Clip, proposal.clip_id) if proposal and proposal.clip_id else None
        if proposal is None or proposal.job_id != prior.id or (clip and clip.ready):
            raise HTTPException(
                409, "Usulan sudah diproses atau berubah. Buka usulan terbaru pada proyek."
            )

    combo = body.ai_combo or body.gemini_model
    validate_model(combo)
    prior.status = "cancelled"
    prior.stage = "Dilanjutkan melalui 9Router"
    s.flush()
    project.ai_combo = combo
    if prior.kind == "analysis" and prior.payload.get("workflow") == "review":
        search = enqueue_search(
            s,
            project,
            SearchInput(
                request_id=uuid4(),
                ai_combo=combo,
                highlight_count=prior.payload.get("highlight_count", 3),
                additional_prompt=prior.payload.get("additional_prompt", ""),
                avoid_used=False,
            ),
        )
        fresh = s.get(Job, search.job_id)
    else:
        fresh = Job(
            project_id=prior.project_id,
            clip_id=prior.clip_id,
            kind=prior.kind,
            payload={**prior.payload, "ai_combo": combo, "provider": "9router"},
            checkpoint=prior.checkpoint,
        )
        s.add(fresh)
        s.flush()
        if prior.kind == "build_highlight":
            proposal = s.get(HighlightProposal, prior.payload["proposal_id"])
            proposal.job_id = fresh.id
    prior.result = {**(prior.result or {}), "successor_job_id": fresh.id}
    s.commit()
    wake()
    return public_job(s, fresh)
