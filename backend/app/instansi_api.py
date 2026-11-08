"""Shared institutions and explicit automatic Mix source policy."""

import unicodedata
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, ConfigDict
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from .db import (
    session,
    Instansi,
    VideoClip,
    project_instansi,
    instasi_to_video_clips,
    proposal_instansi,
    clip_instansi,
    HighlightProposal,
    Clip,
)

router = APIRouter(prefix="/api/instansi")


class InstansiInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean(cls, value):
        value = unicodedata.normalize("NFKC", value).strip()
        if not value or len(value) > 100:
            raise ValueError("Nama instansi wajib berisi 1–100 karakter.")
        return value


class InstansiView(BaseModel):
    id: str
    name: str
    video_count: int = 0
    project_count: int = 0


def resolve_instansi(s, ids):
    wanted = sorted({str(id) for id in ids})
    rows = (
        list(
            s.scalars(
                select(Instansi)
                .where(Instansi.id.in_(wanted))
                .order_by(Instansi.id)
                .with_for_update(read=True)
            )
        )
        if wanted
        else []
    )
    if len(rows) != len(wanted):
        raise HTTPException(422, "Instansi sudah dihapus atau tidak ditemukan. Muat ulang daftar.")
    return rows


def source_owners(s, scope, instansi_ids):
    if scope == "global":
        if instansi_ids:
            raise HTTPException(422, "Video Global tidak memiliki instansi pemilik.")
        return []
    if scope != "instansi" or not instansi_ids:
        raise HTTPException(422, "Pilih minimal satu instansi pemilik video.")
    if len(instansi_ids) > 100:
        raise HTTPException(422, "Maksimal 100 instansi per video.")
    return resolve_instansi(s, instansi_ids)


def filter_sources(library, instansi_ids, include_global=True):
    wanted = {str(id) for id in instansi_ids}
    # Pre-pivot job snapshots keep their original single-institution membership.
    return [
        a
        for a in library
        if (a.get("scope") == "global" and (include_global or not wanted))
        or (
            a.get("scope") == "instansi"
            and wanted.intersection(
                a.get("instansi_ids", []) if "instansi_ids" in a else [a.get("instansi_id")]
            )
        )
    ]


def view(s, item):
    return {
        "id": item.id,
        "name": item.name,
        "video_count": s.scalar(
            select(func.count())
            .select_from(instasi_to_video_clips)
            .where(instasi_to_video_clips.c.instansi_id == item.id)
        ),
        "project_count": len(
            set(
                s.scalars(
                    select(project_instansi.c.project_id).where(
                        project_instansi.c.instansi_id == item.id
                    )
                )
            )
            | set(
                s.scalars(
                    select(HighlightProposal.project_id)
                    .join(
                        proposal_instansi, proposal_instansi.c.proposal_id == HighlightProposal.id
                    )
                    .where(proposal_instansi.c.instansi_id == item.id)
                )
            )
            | set(
                s.scalars(
                    select(Clip.project_id)
                    .join(clip_instansi, clip_instansi.c.clip_id == Clip.id)
                    .where(clip_instansi.c.instansi_id == item.id)
                )
            )
        ),
    }


def commit(s):
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409, "Nama instansi sudah digunakan.")


@router.get("", response_model=list[InstansiView])
def listing(s=Depends(session)):
    return [view(s, item) for item in s.scalars(select(Instansi).order_by(Instansi.name_key))]


@router.post("", response_model=InstansiView, status_code=201)
def create(body: InstansiInput, s=Depends(session)):
    item = Instansi(name=body.name, name_key=body.name.casefold())
    s.add(item)
    commit(s)
    return view(s, item)


def lookup(s, id):
    item = s.scalar(select(Instansi).where(Instansi.id == id).with_for_update())
    if item is None:
        raise HTTPException(404, "Instansi tidak ditemukan.")
    return item


@router.patch("/{id}", response_model=InstansiView)
def rename(id: str, body: InstansiInput, s=Depends(session)):
    item = lookup(s, id)
    if item.name != body.name:
        item.name = body.name
        item.name_key = body.name.casefold()
        s.execute(
            update(VideoClip)
            .where(
                VideoClip.id.in_(
                    select(instasi_to_video_clips.c.video_clip_id).where(
                        instasi_to_video_clips.c.instansi_id == id
                    )
                )
            )
            .values(revision=VideoClip.revision + 1)
        )
    commit(s)
    return view(s, item)


@router.delete("/{id}")
def remove(id: str, s=Depends(session)):
    item = lookup(s, id)
    counts = view(s, item)
    if counts["video_count"] or counts["project_count"]:
        raise HTTPException(
            409, "Instansi masih dipakai video atau proyek. Pindahkan relasinya terlebih dahulu."
        )
    s.delete(item)
    s.commit()
    return {"deleted": id}
