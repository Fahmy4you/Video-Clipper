"""Review proposals are independent of editable clips. Approval snapshots are immutable."""

import json
import math
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import select
from .db import session, Project, Clip, Job, HighlightProposal, ProposalSearch, now
from .schemas import Ratio, Hashtags, JobView
from .instansi_api import resolve_instansi
from .queue_runtime import PENDING, public_job, wake
from .media import project_dir

router = APIRouter(prefix="/api")


class VideoSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aspect_ratio: Ratio = "9:16"
    visual_mode: str = Field(default="podcast", pattern="^(podcast|mix)$")
    subtitle_mode: str = Field(default="sentence", pattern="^(sentence|word)$")
    subtitle_animation: str = Field(default="none", pattern="^(none|soft_zoom)$")
    instansi_ids: list[UUID] = Field(default_factory=list, max_length=100)
    include_global: bool = True
    mix_hashtags: Hashtags = Field(default_factory=list)
    mix_max_per_minute: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def normalize(self):
        self.instansi_ids = list(dict.fromkeys(self.instansi_ids))
        if self.visual_mode == "podcast":
            self.instansi_ids = []
            self.mix_hashtags = []
            self.mix_max_per_minute = None
            self.include_global = True
        if not self.instansi_ids:
            self.include_global = True
        return self


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class ProposalUpdate(ProposalInput):
    revision: int = Field(ge=1)
    settings: VideoSettings | None = None


class Approval(BaseModel):
    id: UUID
    revision: int = Field(ge=1)


class ApprovalBatch(BaseModel):
    items: list[Approval] = Field(min_length=1, max_length=100)


class ProposalView(BaseModel):
    id: str
    project_id: str
    revision: int
    title: str
    summary: str
    reason: str
    start: int
    end: int
    original_start: int
    original_end: int
    fulfills_prompt: bool
    settings: dict
    configured: bool
    job_id: str | None
    clip_id: str | None
    status: str
    instansi_ids: list[str]


class TranscriptGroup(BaseModel):
    start: float
    end: float
    text: str


class TranscriptRange(BaseModel):
    groups: list[TranscriptGroup]
    total: int
    offset: int
    limit: int


def lookup(s, model, id):
    x = s.get(model, id)
    if x is None:
        raise HTTPException(404, "Data tidak ditemukan.")
    return x


def locked_proposal(s, id):
    pid = s.scalar(select(HighlightProposal.project_id).where(HighlightProposal.id == id))
    if pid is None:
        raise HTTPException(404, "Usulan tidak ditemukan.")
    s.execute(select(Project).where(Project.id == pid).with_for_update()).scalar_one()
    p = s.scalar(select(HighlightProposal).where(HighlightProposal.id == id).with_for_update())
    if p is None:
        raise HTTPException(404, "Usulan tidak ditemukan.")
    return p


def validate_range(start, end, duration):
    from .highlight_limits import MIN_FRAMES, MAX_FRAMES

    if start < 0 or end > math.floor(duration * 30 + 0.00001):
        raise HTTPException(422, "Rentang harus berada dalam video sumber.")
    if end - start < MIN_FRAMES:
        raise HTTPException(422, "Durasi highlight minimal 10 detik.")
    if end - start > MAX_FRAMES:
        raise HTTPException(
            422, "Durasi highlight maksimal 20 menit. Sesuaikan waktu mulai atau akhir."
        )


def state(s, p):
    j = s.get(Job, p.job_id) if p.job_id else None
    if p.clip_id:
        c = s.get(Clip, p.clip_id)
        if c and c.ready:
            return "ready"
    return j.status if j else "review"


def view(s, p):
    return {
        **{
            k: getattr(p, k)
            for k in (
                "id",
                "project_id",
                "revision",
                "title",
                "summary",
                "reason",
                "original_start",
                "original_end",
                "start",
                "end",
                "fulfills_prompt",
                "settings",
                "configured",
                "job_id",
                "clip_id",
            )
        },
        "status": state(s, p),
        "instansi_ids": p.instansi_ids,
    }


def counts(s, pid):
    rows = list(s.scalars(select(HighlightProposal).where(HighlightProposal.project_id == pid)))
    states = [state(s, p) for p in rows]
    return {
        "proposals": len(rows),
        "review": sum(x in ("review", "failed", "cancelled") for x in states),
        "processing": sum(x in PENDING for x in states),
        "ready": len(
            list(s.scalars(select(Clip.id).where(Clip.project_id == pid, Clip.ready == True)))
        ),
    }


@router.get("/projects/{pid}/proposals", response_model=list[ProposalView])
def listing(pid: str, s=Depends(session)):
    lookup(s, Project, pid)
    return [
        view(s, p)
        for p in s.scalars(
            select(HighlightProposal)
            .where(HighlightProposal.project_id == pid)
            .order_by(HighlightProposal.created_at, HighlightProposal.id)
        )
    ]


@router.post("/projects/{pid}/proposals", status_code=201, response_model=ProposalView)
def create(pid: str, body: ProposalInput, s=Depends(session)):
    project = lookup(s, Project, pid)
    validate_range(body.start, body.end, project.duration)
    p = HighlightProposal(
        project_id=pid,
        **body.model_dump(),
        reason="Bagian dipilih manual.",
        original_start=body.start,
        original_end=body.end,
    )
    s.add(p)
    s.flush()
    from .db import HighlightRequest
    from .highlight_requests import next_number

    s.add(
        HighlightRequest(
            project_id=pid,
            number=next_number(s, pid),
            proposal_id=p.id,
            status="fulfilled",
            snapshot={"combo": project.ai_combo or "", "prompt": "", "avoid_used": False},
        )
    )
    s.commit()
    return view(s, p)


@router.get("/proposals/{id}", response_model=ProposalView)
def detail(id: str, s=Depends(session)):
    return view(s, lookup(s, HighlightProposal, id))


@router.patch("/proposals/{id}", response_model=ProposalView)
def revise(id: str, body: ProposalUpdate, s=Depends(session)):
    p = locked_proposal(s, id)
    if state(s, p) in (*PENDING, "ready"):
        raise HTTPException(409, "Usulan sudah diproses atau sedang dikunci pekerjaan.")
    if p.revision != body.revision:
        raise HTTPException(409, "Usulan sudah berubah. Muat ulang sebelum menyimpan.")
    validate_range(body.start, body.end, lookup(s, Project, p.project_id).duration)
    if not body.title.strip():
        raise HTTPException(422, "Judul wajib diisi.")
    for k in ("title", "summary", "start", "end"):
        setattr(p, k, getattr(body, k))
    capacity = min(5, ((p.end - p.start) * 3 // 10) // 90)
    if (
        body.settings is not None
        and body.settings.mix_max_per_minute is not None
        and body.settings.mix_max_per_minute > capacity
    ):
        raise HTTPException(422, "Batas sisipan melebihi kapasitas durasi highlight.")
    if body.settings is None and p.settings.get("mix_max_per_minute") is not None:
        p.settings = {
            **p.settings,
            "mix_max_per_minute": min(p.settings["mix_max_per_minute"], capacity),
        }
    if body.settings is not None:
        p.settings = body.settings.model_dump(mode="json", exclude={"instansi_ids"})
        p.instansi_records = resolve_instansi(s, body.settings.instansi_ids)
        p.configured = True
    p.revision += 1
    s.commit()
    return view(s, p)


@router.delete("/proposals/{id}")
def remove(id: str, s=Depends(session), commit=True):
    p = locked_proposal(s, id)
    if state(s, p) in (*PENDING, "ready"):
        raise HTTPException(
            409, "Batalkan pekerjaan aktif dahulu; highlight siap dihapus melalui daftar highlight."
        )
    # Failed partial builds have never been available for editing.
    if p.clip_id:
        s.execute(
            __import__("sqlalchemy")
            .update(Job)
            .where(Job.clip_id == p.clip_id)
            .values(clip_id=None)
        )
        c = s.get(Clip, p.clip_id)
        p.clip_id = None
        s.flush()
        if c:
            s.delete(c)
    from .db import HighlightRequest

    for item in s.scalars(select(HighlightRequest).where(HighlightRequest.proposal_id == p.id)):
        item.deleted = True
        item.snapshot = {**item.snapshot, "deleted_range": [p.start, p.end]}
        item.proposal_id = None
        item.revision += 1
    s.delete(p)
    if commit:
        s.commit()
    return {"deleted": id}


def approve(s, p, revision):
    current = state(s, p)
    if p.job_id and current in (*PENDING, "ready"):
        if p.revision != revision:
            raise HTTPException(409, "Revisi usulan sudah berubah.")
        return s.get(Job, p.job_id)
    if p.revision != revision:
        raise HTTPException(409, "Usulan sudah berubah. Muat ulang sebelum memproses.")
    if not p.configured:
        raise HTTPException(422, "Siapkan pengaturan video untuk setiap usulan dahulu.")
    project = lookup(s, Project, p.project_id)
    prior = s.get(Job, p.job_id) if p.job_id else None
    same = prior and prior.payload.get("proposal_revision") == p.revision
    if not (same and not prior.payload.get("mix_rules_version")):
        validate_range(p.start, p.end, project.duration)
    config = VideoSettings(**p.settings, instansi_ids=p.instansi_ids).model_dump(mode="json")
    maximum = config.get("mix_max_per_minute")
    capacity = min(5, ((p.end - p.start) * 3 // 10) // 90)
    if maximum is not None and maximum > capacity:
        raise HTTPException(422, "Batas sisipan melebihi kapasitas durasi highlight.")
    from .video_library import snapshot

    prior = s.get(Job, p.job_id) if p.job_id else None
    same = prior and prior.payload.get("proposal_revision") == p.revision
    payload = (
        prior.payload
        if same
        else {
            "proposal_id": p.id,
            "proposal_revision": p.revision,
            "workflow": "review",
            "mix_rules_version": 1,
            "start": p.start,
            "end": p.end,
            "title": p.title,
            "summary": p.summary,
            "reason": p.reason,
            "gemini_model": project.gemini_model,
            "ai_combo": (
                s.get(ProposalSearch, p.search_id).combo if p.search_id else project.ai_combo
            ),
            "provider": "9router",
            **config,
            "source_policy_version": 1,
            "library": snapshot(
                s, config["mix_hashtags"], config["instansi_ids"], config["include_global"]
            )
            if config["visual_mode"] == "mix"
            else [],
        }
    )
    from .video_library import live_job_payload

    payload = live_job_payload(s, {**payload, "project_id": p.project_id})
    j = Job(
        project_id=p.project_id,
        kind="build_highlight",
        payload=payload,
        checkpoint=prior.checkpoint if same else {},
    )
    s.add(j)
    s.flush()
    p.job_id = j.id
    # An altered draft must not reuse an old partial plan.
    if not same and p.clip_id:
        s.execute(
            __import__("sqlalchemy")
            .update(Job)
            .where(Job.clip_id == p.clip_id)
            .values(clip_id=None)
        )
        old = s.get(Clip, p.clip_id)
        p.clip_id = None
        s.flush()
        if old:
            s.delete(old)
    return j


@router.post("/projects/{pid}/proposals/process", status_code=202, response_model=list[JobView])
def process(pid: str, body: ApprovalBatch, s=Depends(session)):
    project = s.scalar(select(Project).where(Project.id == pid).with_for_update())
    if not project:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    ids = sorted({str(i.id) for i in body.items})
    if len(ids) != len(body.items):
        raise HTTPException(422, "Usulan tidak boleh dipilih dua kali.")
    rows = list(
        s.scalars(
            select(HighlightProposal)
            .where(HighlightProposal.project_id == pid, HighlightProposal.id.in_(ids))
            .order_by(HighlightProposal.id)
            .with_for_update()
        )
    )
    if len(rows) != len(ids):
        raise HTTPException(404, "Usulan tidak ditemukan pada proyek ini.")
    revisions = {str(x.id): x.revision for x in body.items}
    try:
        jobs = [approve(s, p, revisions[p.id]) for p in rows]
        s.commit()
    except Exception:
        s.rollback()
        raise
    wake()
    return [public_job(s, j) for j in jobs]


@router.get("/projects/{pid}/transcript-range", response_model=TranscriptRange)
def transcript_range(
    pid: str,
    start: int = 0,
    end: int | None = None,
    offset: int = 0,
    limit: int = 100,
    s=Depends(session),
):
    project = lookup(s, Project, pid)
    if start < 0 or offset < 0 or not 1 <= limit <= 200:
        raise HTTPException(422, "Rentang atau pagination tidak valid.")
    end = end if end is not None else math.floor(project.duration * 30)
    if end <= start or end > math.floor(project.duration * 30 + 0.00001):
        raise HTTPException(422, "Rentang di luar sumber.")
    path = project_dir(pid) / "transcript.json"
    words = json.loads(path.read_text()).get("words", []) if path.exists() else []
    selected = [w for w in words if w["end"] > start / 30 and w["start"] < end / 30]
    # Groups contain at most 20 words and 10 seconds for readable, bounded pages.
    groups = []
    for w in selected:
        if not groups or len(groups[-1]["words"]) >= 20 or w["start"] - groups[-1]["start"] >= 10:
            groups.append({"start": w["start"], "end": w["end"], "words": []})
        groups[-1]["words"].append(w["text"])
        groups[-1]["end"] = w["end"]
    return {
        "groups": [
            {"start": g["start"], "end": g["end"], "text": " ".join(g["words"])}
            for g in groups[offset : offset + limit]
        ],
        "total": len(groups),
        "offset": offset,
        "limit": limit,
    }
