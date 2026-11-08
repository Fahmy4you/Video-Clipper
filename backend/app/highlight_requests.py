"""Stable request cards; job attempts never create additional cards."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .db import session, Project, Job, ProposalSearch, HighlightProposal, HighlightRequest, Clip
from .queue_runtime import PENDING, public_job, wake
from .router_ai import validate_model

router = APIRouter(prefix="/api")


from .review import ProposalView
from .schemas import JobView


class RequestView(BaseModel):
    id: str
    number: int
    revision: int
    status: str
    reason: str
    snapshot: dict
    proposal: ProposalView | None
    job: JobView | None


def next_number(s, pid):
    return (
        s.scalar(
            select(func.max(HighlightRequest.number)).where(HighlightRequest.project_id == pid)
        )
        or 0
    ) + 1


def snapshot(search, job):
    payload = job.payload if job else {}
    return {
        "combo": search.combo,
        "prompt": search.prompt,
        "avoid_used": search.avoid_used,
        "exclusions": search.exclusions,
        "time_range": payload.get("time_range"),
        "policy_version": payload.get("policy_version", 1),
    }


def add_items(s, project, search, job):
    number = next_number(s, project.id)
    rows = [
        HighlightRequest(
            project_id=project.id,
            search_id=search.id,
            number=number + i,
            snapshot=snapshot(search, job),
            job_id=job.id,
        )
        for i in range(search.count)
    ]
    s.add_all(rows)
    s.flush()
    return rows


def backfill(s):
    # Only actual searches and actual proposals establish historical cardinality.
    for project in s.scalars(select(Project).order_by(Project.created_at, Project.id)):
        for search in s.scalars(
            select(ProposalSearch)
            .where(ProposalSearch.project_id == project.id)
            .order_by(ProposalSearch.created_at, ProposalSearch.id)
        ):
            if s.scalar(select(HighlightRequest.id).where(HighlightRequest.search_id == search.id)):
                continue
            proposals = list(
                s.scalars(
                    select(HighlightProposal)
                    .where(HighlightProposal.search_id == search.id)
                    .order_by(HighlightProposal.created_at, HighlightProposal.id)
                )
            )
            job = s.get(Job, search.job_id) if search.job_id else None
            if job and job.payload.get("request_item_ids"):
                continue
            number = next_number(s, project.id)
            for i in range(max(search.count, len(proposals))):
                p = proposals[i] if i < len(proposals) else None
                s.add(
                    HighlightRequest(
                        project_id=project.id,
                        search_id=search.id,
                        number=number + i,
                        proposal_id=p.id if p else None,
                        job_id=search.job_id,
                        snapshot=snapshot(search, job),
                        status="fulfilled"
                        if p
                        else ("unfulfilled" if search.completed else "queued"),
                        reason=""
                        if p
                        else (
                            "Seleksi sebelumnya belum memenuhi jumlah yang diminta."
                            if search.completed
                            else ""
                        ),
                    )
                )
            s.flush()
        for p in s.scalars(
            select(HighlightProposal)
            .where(HighlightProposal.project_id == project.id, HighlightProposal.search_id == None)
            .order_by(HighlightProposal.created_at, HighlightProposal.id)
        ):
            if not s.scalar(
                select(HighlightRequest.id).where(HighlightRequest.proposal_id == p.id)
            ):
                s.add(
                    HighlightRequest(
                        project_id=project.id,
                        number=next_number(s, project.id),
                        proposal_id=p.id,
                        status="fulfilled",
                        snapshot={
                            "combo": project.ai_combo or "",
                            "prompt": "",
                            "avoid_used": False,
                        },
                    )
                )
                s.flush()


def item_view(s, item):
    job = s.get(Job, item.job_id) if item.job_id else None
    status = item.status
    reason = item.reason
    if item.proposal_id:
        status = "fulfilled"
    elif job and status != "unfulfilled":
        status = job.status if job.status != "succeeded" else "unfulfilled"
        reason = job.error or job.wait_reason or reason
    from .review import view

    p = s.get(HighlightProposal, item.proposal_id) if item.proposal_id else None
    return {
        "id": item.id,
        "number": item.number,
        "revision": item.revision,
        "status": status,
        "reason": reason,
        "snapshot": item.snapshot,
        "proposal": view(s, p) if p else None,
        "job": public_job(s, job) if job else None,
    }


@router.get("/projects/{pid}/highlight-requests", response_model=list[RequestView])
def listing(pid: str, s=Depends(session)):
    if not s.get(Project, pid):
        raise HTTPException(404, "Proyek tidak ditemukan.")
    return [
        item_view(s, x)
        for x in s.scalars(
            select(HighlightRequest)
            .where(HighlightRequest.project_id == pid, HighlightRequest.deleted == False)
            .order_by(HighlightRequest.number)
        )
    ]


def locked(s, id):
    pid = s.scalar(select(HighlightRequest.project_id).where(HighlightRequest.id == id))
    if not pid:
        raise HTTPException(404, "Permintaan highlight tidak ditemukan.")
    project = s.scalar(select(Project).where(Project.id == pid).with_for_update())
    item = s.scalar(select(HighlightRequest).where(HighlightRequest.id == id).with_for_update())
    if item.deleted:
        raise HTTPException(404, "Permintaan highlight sudah dihapus.")
    return project, item


class RetryInput(BaseModel):
    request_id: UUID
    revision: int = Field(ge=1)
    ai_combo: str = Field(min_length=1, max_length=200)


@router.post("/highlight-requests/{id}/reanalyze", status_code=202, response_model=JobView)
def reanalyze(id: str, body: RetryInput, s=Depends(session)):
    from .proposal_searches import SearchInput, enqueue_search

    project, item = locked(s, id)
    existing = s.scalar(
        select(ProposalSearch).where(ProposalSearch.request_id == str(body.request_id))
    )
    if existing:
        job = s.get(Job, existing.job_id)
        if job.payload.get("request_item_ids") != [id] or existing.combo != body.ai_combo:
            raise HTTPException(409, "ID permintaan sudah digunakan.")
        return public_job(s, job)
    if item.revision != body.revision:
        raise HTTPException(409, "Permintaan berubah. Muat ulang sebelum mencoba lagi.")
    if item.proposal_id:
        raise HTTPException(409, "Usulan sudah tersedia. Buka halaman detail.")
    old_job = s.get(Job, item.job_id) if item.job_id else None
    if old_job and old_job.status in PENDING:
        raise HTTPException(409, "Analisis masih menunggu atau berjalan.")
    validate_model(body.ai_combo)
    snap = item.snapshot
    request = SearchInput(
        request_id=body.request_id,
        ai_combo=body.ai_combo,
        highlight_count=1,
        additional_prompt=snap.get("prompt", ""),
        avoid_used=snap.get("avoid_used", True),
        policy_version=2,
        time_range=snap.get("time_range"),
    )
    origin = item.search_id
    search = enqueue_search(s, project, request, items=[item], reuse_job_id=item.job_id)
    # Sibling results of a multi-item request are not new results for its missing item.
    siblings = list(
        s.scalars(
            select(HighlightProposal)
            .join(HighlightRequest, HighlightRequest.proposal_id == HighlightProposal.id)
            .where(HighlightRequest.search_id == origin, HighlightRequest.deleted == False)
        )
    )
    job = s.get(Job, search.job_id)
    exclusions = list(job.payload.get("exclusions", []))
    exclusions.extend([p.start, p.end] for p in siblings)
    job.payload = {**job.payload, "exclusions": exclusions}
    search.exclusions = exclusions
    s.commit()
    wake()
    return public_job(s, s.get(Job, search.job_id))


@router.delete("/highlight-requests/{id}")
def remove(id: str, revision: int, s=Depends(session)):
    project, item = locked(s, id)
    if item.revision != revision:
        raise HTTPException(409, "Permintaan berubah. Muat ulang sebelum menghapus.")
    job = s.get(Job, item.job_id) if item.job_id else None
    if not item.proposal_id and job and job.status in PENDING:
        raise HTTPException(409, "Tunggu analisis selesai atau batalkan pekerjaan dahulu.")
    if item.proposal_id:
        from .review import remove as remove_proposal

        remove_proposal(item.proposal_id, s, commit=False)
    if not item.deleted:
        item.deleted = True
        item.revision += 1
    s.commit()
    return {"deleted": True}


def counts(s, pid):
    result = {"requested": 0, "available": 0, "unfulfilled": 0, "failed": 0, "pending": 0}
    for item in s.scalars(
        select(HighlightRequest).where(
            HighlightRequest.project_id == pid, HighlightRequest.deleted == False
        )
    ):
        result["requested"] += 1
        status = item_view(s, item)["status"]
        key = (
            "available"
            if status == "fulfilled"
            else "unfulfilled"
            if status == "unfulfilled"
            else "pending"
            if status in PENDING
            else "failed"
        )
        result[key] += 1
    return result
