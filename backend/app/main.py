from pydantic import BaseModel, Field
import json
import shutil
from pathlib import Path
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, text, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .db import session, engine, Project, Clip, Job, Session, HighlightProposal
from .schemas import (
    ProjectInput,
    ClipInput,
    ClipUpdate,
    ProjectView,
    ClipView,
    JobView,
    ModelSelection,
    ModelOption,
    ModelCatalog,
    CatalogRefresh,
)
from .media import project_dir
from .tasks import execute, celery
from .timeline import upgrade_plan, EditPlanV2
from .audio_assets import AudioImport, MAX_BYTES, audio_metadata
from .model_catalog import available_models, validate_model
from .queue_runtime import PENDING, WAITING, public_job, wake, eligible
from .router_ai import configuration, ConfigError

app = FastAPI(title="Video Clipping API", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def sanitized_validation(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
            ]
        },
    )


from .hashtag_api import router as hashtag_router
from .video_library import (
    router as library_router,
    snapshot as library_snapshot,
    folder as library_folder,
    lock_plan_assets,
    live_job_payload,
)
from .instansi_api import router as instansi_router, resolve_instansi
from .transition_effects import router as transition_effects_router

app.include_router(transition_effects_router)
app.include_router(instansi_router)
app.include_router(library_router)
app.include_router(hashtag_router)
from .review import router as review_router

app.include_router(review_router)
from .router_ai import ConfigError as KeyConfigError
from .proposal_searches import router as searches_router

app.include_router(searches_router)
from .router_recovery import router as recovery_router

app.include_router(recovery_router)


@app.exception_handler(KeyConfigError)
async def key_config_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc), "code": "key_config_invalid"})


app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_origin(request, call_next):
    origin = request.headers.get("origin")
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin
        not in (
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        )
    ):
        return JSONResponse(status_code=403, content={"detail": "Origin tidak diizinkan."})
    return await call_next(request)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Koneksi PostgreSQL sedang terganggu atau sibuk. Draft lokal tetap tersimpan. Tunggu sebentar lalu coba lagi; konfigurasi tidak perlu diisi ulang."
        },
    )


def get(s, model, id):
    item = s.get(model, id)
    if item is None:
        raise HTTPException(404, "Data tidak ditemukan.")
    return item


def serialize(obj):
    if isinstance(obj, Job):
        from sqlalchemy.orm import object_session

        return public_job(object_session(obj), obj)
    data = {
        c.name: getattr(obj, c.name)
        for c in obj.__table__.columns
        if c.name not in ("request_id", "request_hash")
    }
    if isinstance(obj, Project):
        data["instansi_ids"] = obj.instansi_ids
        from sqlalchemy.orm import object_session
        from .review import counts

        data["review_counts"] = counts(object_session(obj), obj.id)
        from .highlight_requests import counts as request_counts

        data["highlight_request_counts"] = request_counts(object_session(obj), obj.id)
    if isinstance(obj, Clip):
        data["instansi_ids"] = obj.instansi_ids
    return data


@app.get("/api/health")
def health():
    database = "not_configured"
    if engine:
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1 FROM projects LIMIT 1"))
            database = "ready"
        except SQLAlchemyError:
            database = "unavailable"
    try:
        import redis

        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1).ping()
        queue = True
    except Exception:
        queue = False
    from .job_diagnostics import worker_health

    from .router_ai import connection_status

    router = connection_status()
    gemini_ready = router["connected"]
    gemini_error = router["error"]
    return {
        "worker": worker_health(),
        "gemini_error": gemini_error,
        "router_error": gemini_error,
        "router": gemini_ready,
        "router_configured": router["configured"],
        "router_status": router["connection_status"],
        "database": database,
        "redis": queue,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "gemini": gemini_ready,
    }


@app.get("/api/model-catalog", response_model=ModelCatalog)
def model_catalog_snapshot():
    from .model_catalog import snapshot

    return snapshot()


@app.post("/api/model-catalog/refresh", status_code=202, response_model=ModelCatalog)
def refresh_model_catalog(body: CatalogRefresh | None = None):
    from .model_catalog import schedule, snapshot

    schedule(force=True)
    return snapshot(update=False)


@app.get("/api/models", response_model=list[ModelOption])
def models(refresh: bool = False):
    return available_models(refresh)


@app.get("/api/ai/status")
def ai_status():
    from .router_ai import snapshot, connection_status

    catalog = snapshot()
    status = connection_status(catalog)
    if not status["configured"]:
        return {**status, "catalog": catalog}
    config = configuration()
    return {
        **status,
        "base_url": config.url,
        "masked_key": "••••••••",
        "catalog": catalog,
    }


@app.get("/api/queue")
def queue_summary(s: DBSession = Depends(session)):
    rows = list(
        s.scalars(select(Job).where(Job.status.in_(PENDING)).order_by(Job.queue_at, Job.id))
    )
    brief = lambda j: {k: v for k, v in public_job(s, j).items() if k not in ("payload", "result")}
    from .job_diagnostics import worker_health

    return {
        "worker": worker_health(),
        "active": next((brief(j) for j in rows if j.status in ("running", "cancelling")), None),
        "waiting": [brief(j) for j in rows if j.status not in ("running", "cancelling")],
    }


@app.get("/api/projects", response_model=list[ProjectView])
def projects(view: str | None = None, s: DBSession = Depends(session)):
    rows = list(s.scalars(select(Project).order_by(Project.created_at.desc())))
    if view == "video":
        rows = [
            p
            for p in rows
            if s.scalar(select(Clip.id).where(Clip.project_id == p.id).limit(1))
            or s.scalar(
                select(HighlightProposal.id)
                .where(HighlightProposal.project_id == p.id, HighlightProposal.job_id.is_not(None))
                .limit(1)
            )
        ]
    return [serialize(x) for x in rows]


from .source_info import router as source_info_router, inspect_source
from .highlight_requests import router as request_router

app.include_router(source_info_router)
app.include_router(request_router)


@app.post("/api/projects", status_code=201, response_model=ProjectView)
def create_project(body: ProjectInput, s: DBSession = Depends(session)):
    import hashlib

    request_id = str(body.request_id) if body.request_id else None
    fingerprint = hashlib.sha256(body.model_dump_json(exclude={"request_id"}).encode()).hexdigest()
    if request_id:
        # Serialize identical submissions before checking the unique key.
        if s.bind.dialect.name == "postgresql":
            s.execute(
                text("SELECT pg_advisory_xact_lock(:lock)"),
                {"lock": int(hashlib.sha256(request_id.encode()).hexdigest()[:15], 16)},
            )
        existing = s.scalar(select(Project).where(Project.request_id == request_id))
        if existing:
            if existing.request_hash != fingerprint:
                raise HTTPException(409, "ID permintaan sudah dipakai dengan isi berbeda.")
            return serialize(existing)
    source_metadata = inspect_source(body.url) if body.workflow == "review" else None
    validate_model(body.ai_combo or body.gemini_model)
    owners = resolve_instansi(s, body.instansi_ids)
    values = body.model_dump(exclude={"instansi_ids", "enqueue_analysis", "request_id"})
    if body.visual_mode == "podcast":
        values.update(mix_hashtags=[], include_global=True)
        owners = []
    p = Project(
        **values,
        instansi_records=owners,
        request_id=request_id,
        request_hash=fingerprint if request_id else None,
    )
    if source_metadata:
        p.duration = source_metadata["duration"]
        p.title = source_metadata["title"]
    s.add(p)
    s.flush()
    from .source_cache import source_record

    source_record(s, p)
    if body.enqueue_analysis:
        if p.workflow == "review":
            from .proposal_searches import enqueue_search, SearchInput

            enqueue_search(
                s,
                p,
                SearchInput(
                    request_id=body.request_id or UUID(p.id),
                    ai_combo=p.ai_combo or p.gemini_model,
                    highlight_count=p.highlight_count,
                    additional_prompt=p.additional_prompt,
                    policy_version=2,
                ),
            )
        else:
            add_job(s, p.id, "analysis", payload=analysis_payload(s, p))
    s.commit()
    if body.enqueue_analysis:
        wake()
    return serialize(p)


@app.delete("/api/projects/{id}")
def delete_project(id: str, s: DBSession = Depends(session)):
    from uuid import uuid4
    from .config import STORAGE

    p = s.scalar(select(Project).where(Project.id == id).with_for_update())
    if p is None:
        raise HTTPException(404, "Proyek tidak ditemukan.")
    if s.scalar(select(Job.id).where(Job.project_id == id, Job.status.in_(PENDING))):
        raise HTTPException(
            409, "Tunggu pekerjaan proyek selesai atau batalkan sebelum menghapus proyek."
        )
    try:
        canonical = str(UUID(id))
    except ValueError:
        raise HTTPException(409, "Lokasi proyek tidak valid.")
    parent = (STORAGE / "projects").resolve()
    folder = parent / canonical
    if folder.is_symlink() or folder.resolve().parent != parent:
        raise HTTPException(409, "Lokasi proyek tidak valid.")
    if folder.exists() and (folder / "source.mp4").exists():
        from .source_cache import shared_folder

        shared_folder(id, folder, s, STORAGE)
    source_id = p.source_id
    clip_ids = list(s.scalars(select(Clip.id).where(Clip.project_id == id)))
    trash = parent / (".delete-" + canonical + "-" + str(uuid4()))
    moved = False
    try:
        if folder.exists():
            folder.rename(trash)
            moved = True
        from .db import HighlightRequest

        s.execute(delete(HighlightRequest).where(HighlightRequest.project_id == id))
        s.execute(delete(Job).where(Job.project_id == id))
        s.execute(delete(HighlightProposal).where(HighlightProposal.project_id == id))
        from .db import ProposalSearch

        s.execute(delete(ProposalSearch).where(ProposalSearch.project_id == id))
        s.execute(delete(Clip).where(Clip.project_id == id))
        s.delete(p)
        s.commit()
    except Exception:
        s.rollback()
        if moved:
            trash.rename(folder)
        raise
    cleanup_pending = False
    if moved:
        try:
            shutil.rmtree(trash)
        except OSError:
            cleanup_pending = True
    if source_id and not s.scalar(
        select(Project.id).where(Project.source_id == source_id).limit(1)
    ):
        from .db import MediaSource

        source = s.get(MediaSource, source_id)
        if source:
            s.delete(source)
            s.commit()
            cached = STORAGE / "sources" / str(UUID(source_id))
            if cached.exists():
                try:
                    shutil.rmtree(cached)
                except OSError:
                    cleanup_pending = True
    return {"deleted": id, "clip_ids": clip_ids, "cleanup_pending": cleanup_pending}


@app.get("/api/projects/{id}", response_model=ProjectView)
def project(id: str, s: DBSession = Depends(session)):
    return serialize(get(s, Project, id))


@app.patch("/api/projects/{id}/model", response_model=ProjectView)
def project_model(id: str, body: ModelSelection, s: DBSession = Depends(session)):
    p = get(s, Project, id)
    validate_model(body.ai_combo or body.gemini_model)
    p.ai_combo = body.ai_combo or body.gemini_model
    s.commit()
    return serialize(p)


@app.get("/api/projects/{id}/clips", response_model=list[ClipView])
def clips(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    return [
        serialize(x)
        for x in s.scalars(select(Clip).where(Clip.project_id == id, Clip.ready == True))
    ]


@app.get("/api/projects/{id}/transcript")
def transcript(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    f = project_dir(id) / "transcript.json"
    return json.loads(f.read_text()) if f.exists() else {"words": []}


@app.get("/api/projects/{id}/jobs", response_model=list[JobView])
def jobs(id: str, s: DBSession = Depends(session)):
    return [
        public_job(s, x)
        for x in s.scalars(select(Job).where(Job.project_id == id).order_by(Job.created_at.desc()))
    ]


def add_job(s, pid, kind, clip=None, payload=None, checkpoint=None):
    s.execute(select(Project).where(Project.id == pid).with_for_update()).scalar_one()
    active = list(s.scalars(select(Job).where(Job.project_id == pid, Job.status.in_(PENDING))))
    if kind in ("analysis", "mix") and any(j.kind in ("analysis", "mix") for j in active):
        raise HTTPException(
            409, "Pembuatan highlight atau Mix proyek ini masih aktif atau menunggu."
        )
    snapshot = live_job_payload(s, {**(payload or {}), "project_id": pid})
    for j in active:
        if (
            j.kind == kind
            and j.clip_id == clip
            and (kind == "editor_media" or j.payload == snapshot)
        ):
            return j
    if kind == "analysis":
        from .transcription import allow_manual_retry
        from .config import STORAGE

        allow_manual_retry(STORAGE / "projects" / pid)
    j = Job(project_id=pid, kind=kind, clip_id=clip, payload=snapshot, checkpoint=checkpoint or {})
    s.add(j)
    s.flush()
    return j


def enqueue(s, pid, kind, clip=None, payload=None, checkpoint=None):
    j = add_job(s, pid, kind, clip, payload, checkpoint)
    s.commit()
    wake()
    return public_job(s, j)


def analysis_payload(s, p):
    return {
        "workflow": p.workflow,
        "subtitle_mode": p.subtitle_mode,
        "subtitle_animation": p.subtitle_animation,
        "gemini_model": p.gemini_model,
        "ai_combo": p.ai_combo,
        "provider": "9router",
        "aspect_ratio": p.aspect_ratio,
        "highlight_count": p.highlight_count,
        "additional_prompt": p.additional_prompt,
        "visual_mode": p.visual_mode,
        "mix_hashtags": p.mix_hashtags,
        "source_policy_version": 1,
        "mix_rules_version": 1,
        "instansi_ids": p.instansi_ids,
        "include_global": p.include_global,
        "library": library_snapshot(s, p.mix_hashtags, p.instansi_ids, p.include_global)
        if p.visual_mode == "mix" and p.workflow != "review"
        else [],
    }


@app.post("/api/projects/{id}/analysis", status_code=202)
def analysis(id: str, s: DBSession = Depends(session)):
    p = get(s, Project, id)
    if not (p.ai_combo or p.gemini_model):
        raise HTTPException(422, "Pilih model Gemini untuk proyek ini terlebih dahulu.")
    validate_model(p.ai_combo or p.gemini_model)
    return enqueue(s, id, "analysis", payload=analysis_payload(s, p))


def validate_plan(plan, project, previous=None):
    v2 = upgrade_plan(plan.model_dump())
    from .boundaries import validate_minimum

    try:
        validate_minimum(v2, previous)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if any(x["source_in"] + x["duration"] > round(project.duration * 30) for x in v2["segments"]):
        raise HTTPException(422, "Clip melebihi durasi sumber.")
    for segment in v2["segments"]:
        for item in segment.get("broll", []):
            try:
                meta = json.loads((library_folder(item["asset_id"]) / "metadata.json").read_text())
            except (ValueError, OSError):
                raise HTTPException(422, "Video sisipan tidak tersedia.")
            if item["source_in"] + item["end"] - item["start"] > meta["frames"]:
                raise HTTPException(422, "Sisipan melewati akhir video koleksi.")
        for audio in segment.get("audio", []):
            try:
                metadata = audio_metadata(project_dir(project.id), audio["asset_id"])
            except (ValueError, OSError):
                raise HTTPException(422, "Audio tidak ditemukan pada proyek ini.")
            if audio["source_in"] + audio["end"] - audio["start"] > metadata["frames"]:
                raise HTTPException(422, "Potongan audio melebihi durasi aset.")
        for overlay in segment["overlays"]:
            if overlay["kind"] == "image":
                try:
                    asset = str(UUID(overlay["asset_id"]))
                except ValueError:
                    raise HTTPException(422, "ID gambar tidak valid.")
                if not (project_dir(project.id) / "assets" / f"{asset}.png").is_file():
                    raise HTTPException(422, "Gambar tidak ditemukan pada proyek ini.")


@app.post("/api/projects/{id}/clips", status_code=201, response_model=ClipView)
def manual_clip(id: str, body: ClipInput, s: DBSession = Depends(session)):
    p = get(s, Project, id)
    lock_plan_assets(s, body.plan.model_dump())
    validate_plan(body.plan, p)
    from .review import VideoSettings
    from pydantic import ValidationError

    try:
        config = VideoSettings(
            **(
                body.processing_config
                or {
                    k: getattr(p, k)
                    for k in (
                        "visual_mode",
                        "subtitle_mode",
                        "subtitle_animation",
                        "include_global",
                        "mix_hashtags",
                    )
                }
            ),
            instansi_ids=body.instansi_ids or p.instansi_ids,
        )
    except ValidationError as error:
        raise HTTPException(422, "Konfigurasi video tidak valid.") from error
    config.aspect_ratio = body.aspect_ratio or p.aspect_ratio
    c = Clip(
        project_id=id,
        title=body.title,
        plan=upgrade_plan(body.plan.model_dump()),
        aspect_ratio=body.aspect_ratio or p.aspect_ratio,
        processing_config=config.model_dump(mode="json", exclude={"instansi_ids"}),
        instansi_records=resolve_instansi(s, config.instansi_ids),
    )
    s.add(c)
    s.commit()
    return serialize(c)


@app.patch("/api/clips/{id}", response_model=ClipView)
def save_clip(id: str, body: ClipUpdate, s: DBSession = Depends(session)):
    c = s.scalar(select(Clip).where(Clip.id == id).with_for_update())
    if c is None:
        raise HTTPException(404, "Clip tidak ditemukan.")
    if not c.ready:
        raise HTTPException(409, "Highlight masih diproses.")
    if body.aspect_ratio and body.aspect_ratio != c.aspect_ratio:
        raise HTTPException(422, "Rasio highlight terkunci setelah diproses.")
    if body.processing_config is not None or body.instansi_ids:
        raise HTTPException(
            422, "Konfigurasi pemrosesan tidak dapat diubah melalui penyimpanan editor."
        )
    if c.revision != body.revision:
        raise HTTPException(409, "Clip sudah berubah. Muat ulang sebelum menyimpan.")
    p = get(s, Project, c.project_id)
    lock_plan_assets(s, body.plan.model_dump())
    validate_plan(body.plan, p, c.plan)
    from .boundaries import normalize

    incoming = body.plan.model_dump()
    if c.plan.get("transition_version") == 1 and incoming.get("transition_version") != 1:
        raise HTTPException(409, "Versi editor lama. Muat ulang sebelum menyimpan transisi.")
    if c.plan.get("transition_version") != 1:
        if c.legacy_plan is None:
            c.legacy_plan = c.plan
        backups = project_dir(c.project_id) / "plan-backups"
        backups.mkdir(exist_ok=True)
        try:
            with (backups / f"{c.id}-r{c.revision}-transitions.json").open("x") as backup:
                json.dump(c.plan, backup, ensure_ascii=False)
        except FileExistsError:
            pass
    c.title = body.title
    c.plan = normalize(upgrade_plan(incoming))
    c.revision += 1
    s.commit()
    return serialize(c)


@app.post("/api/clips/{id}/preview", status_code=202)
def preview(id: str, s: DBSession = Depends(session)):
    c = get(s, Clip, id)
    if not c.ready:
        raise HTTPException(409, "Highlight masih diproses.")
    return enqueue(
        s,
        c.project_id,
        "preview",
        c.id,
        {"plan": c.plan, "revision": c.revision, "aspect_ratio": c.aspect_ratio},
    )


from .export_delivery import ExportConfigView


@app.get("/api/export-config", response_model=ExportConfigView)
def export_config():
    from .export_delivery import config_view

    return config_view()


from .export_options import ExportRequest, dimensions, RENDER_VERSION


@app.post("/api/clips/{id}/exports", status_code=202)
def export(id: str, body: ExportRequest = ExportRequest(), s: DBSession = Depends(session)):
    from .export_delivery import config_snapshot

    try:
        delivery = config_snapshot()
    except (ValueError, OSError) as e:
        raise HTTPException(422, str(e))
    c = get(s, Clip, id)
    if not c.ready:
        raise HTTPException(409, "Highlight masih diproses.")
    ratio = c.aspect_ratio
    width, height = dimensions(ratio, body.resolution)
    return enqueue(
        s,
        c.project_id,
        "export",
        c.id,
        {
            "resolution": body.resolution,
            "width": width,
            "height": height,
            "render_version": RENDER_VERSION,
            "plan": c.plan,
            "revision": c.revision,
            "title": c.title,
            "delivery": delivery,
            "aspect_ratio": c.aspect_ratio,
        },
    )


@app.get("/api/exports/{id}/download")
def download_export(id: str, s: DBSession = Depends(session)):
    from .export_delivery import filename

    j = get(s, Job, id)
    if j.kind != "export" or j.status != "succeeded":
        raise HTTPException(404, "Ekspor belum tersedia.")
    f = project_dir(j.project_id) / (str(UUID(j.result.get("render_job_id", j.id))) + ".mp4")
    if not f.is_file():
        raise HTTPException(404, "File ekspor tidak ditemukan.")
    name = j.result.get("filename") or filename(
        j.payload.get("title", "highlight"), j.payload.get("revision", 1), j.id
    )
    return FileResponse(f, media_type="video/mp4", filename=name)


@app.get("/api/jobs/{id}", response_model=JobView)
@app.get("/api/exports/{id}", response_model=JobView)
def job(id: str, s: DBSession = Depends(session)):
    return public_job(s, get(s, Job, id))


@app.post("/api/jobs/{id}/cancel")
def cancel(id: str, s: DBSession = Depends(session)):
    j = s.scalar(select(Job).where(Job.id == id).with_for_update())
    if j is None:
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")
    if j.status in PENDING:
        j.status = "cancelling" if j.status in ("running", "cancelling") else "cancelled"
        j.stage = (
            "Membatalkan; menunggu proses berhenti" if j.status == "cancelling" else "Dibatalkan"
        )
        if j.library_id and j.status == "cancelled":
            from .db import VideoClip

            v = s.get(VideoClip, j.library_id)
            if v:
                v.status = "failed"
                v.error = "Persiapan dibatalkan."
        s.commit()
    return public_job(s, j)


@app.post("/api/jobs/{id}/check", status_code=202, response_model=JobView)
def check_waiting(id: str, s: DBSession = Depends(session)):
    j = s.scalar(select(Job).where(Job.id == id).with_for_update())
    if not j:
        raise HTTPException(404, "Pekerjaan tidak ditemukan.")
    if j.status not in WAITING:
        raise HTTPException(409, "Pekerjaan tidak sedang menunggu.")
    from .db import now

    if j.next_attempt_at and j.next_attempt_at > now():
        return public_job(s, j)
    j.checkpoint = {**j.checkpoint, "automatic_waits": 0}
    j.status = "queued"
    j.wait_reason = None
    j.next_attempt_at = None
    j.stage = "Menunggu giliran"
    s.commit()
    wake()
    return public_job(s, j)


@app.post("/api/jobs/{id}/retry", status_code=202)
def retry(id: str, s: DBSession = Depends(session)):
    j = get(s, Job, id)
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Pekerjaan belum gagal atau dibatalkan.")
    payload = j.payload
    if j.kind == "build_highlight":
        from .review import approve, locked_proposal

        p = locked_proposal(s, j.payload["proposal_id"])
        if not p or p.job_id != j.id or p.revision != j.payload["proposal_revision"]:
            raise HTTPException(409, "Usulan sudah direvisi. Proses dari usulan terbaru.")
        fresh = approve(s, p, p.revision)
        s.commit()
        wake()
        return public_job(s, fresh)
    # Keep the immutable model/source snapshot and saved stages on retry.
    if j.library_id:
        from .db import VideoClip
        from .queue_runtime import add_library

        v = get(s, VideoClip, j.library_id)
        v.status = "queued"
        v.error = None
        fresh = add_library(s, j.library_id)
        s.commit()
        wake()
        return public_job(s, fresh)
    return enqueue(s, j.project_id, j.kind, j.clip_id, payload, j.checkpoint)


@app.get("/api/media/{pid}/{filename}")
def media(pid: str, filename: str, s: DBSession = Depends(session)):
    get(s, Project, pid)
    if filename != "source.mp4":
        try:
            UUID(Path(filename).stem)
        except ValueError:
            raise HTTPException(404)
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise HTTPException(404)
    f = project_dir(pid) / filename
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="video/mp4")


@app.get("/api/projects/{id}/editor-media")
def editor_media(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    f = project_dir(id) / "editor" / "manifest.json"
    if not f.exists():
        return {"status": "pending"}
    return {
        **json.loads(f.read_text()),
        "proxy_url": f"/api/editor-media/{id}/proxy.mp4",
        "thumbnail_base": f"/api/editor-media/{id}/thumbs/",
    }


@app.post("/api/projects/{id}/editor-media", status_code=202)
def prepare_editor_media(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    if not (project_dir(id) / "source.mp4").exists():
        raise HTTPException(409, "Video sumber belum tersedia.")
    return enqueue(s, id, "editor_media")


@app.get("/api/editor-media/{id}/{filename:path}")
def serve_editor_media(id: str, filename: str, s: DBSession = Depends(session)):
    import re

    get(s, Project, id)
    if filename != "proxy.mp4" and not re.fullmatch(r"thumbs/[0-9]{5}\.jpg", filename):
        raise HTTPException(404)
    f = project_dir(id) / "editor" / filename
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/api/projects/{id}/assets")
def assets(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    folder = project_dir(id) / "assets"
    return (
        [json.loads(f.read_text()) for f in sorted(folder.glob("*.json"))]
        if folder.exists()
        else []
    )


@app.post("/api/projects/{id}/assets", status_code=201)
async def upload_asset(id: str, file: UploadFile = File(...), s: DBSession = Depends(session)):
    from PIL import Image, ImageOps, UnidentifiedImageError
    from io import BytesIO
    from uuid import uuid4
    from .media import write_json

    get(s, Project, id)
    data = await file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "Gambar maksimal 20 MB.")
    try:
        im = Image.open(BytesIO(data))
        if im.format not in ("PNG", "JPEG", "WEBP") or getattr(im, "n_frames", 1) != 1:
            raise HTTPException(422, "Gunakan PNG, JPEG, atau WebP statis.")
        if im.width * im.height > 40000000:
            raise HTTPException(422, "Resolusi gambar terlalu besar (maksimal 40 megapiksel).")
        im = ImageOps.exif_transpose(im).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Gambar tidak valid.")
    aid = str(uuid4())
    folder = project_dir(id) / "assets"
    folder.mkdir(exist_ok=True)
    im.save(folder / f"{aid}.png")
    result = {
        "id": aid,
        "name": Path(file.filename or "Gambar").name[:200],
        "width": im.width,
        "height": im.height,
        "url": f"/api/assets/{id}/{aid}",
    }
    write_json(folder / f"{aid}.json", result)
    return result


@app.get("/api/assets/{id}/{asset_id}")
def asset(id: str, asset_id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    try:
        aid = str(UUID(asset_id))
    except ValueError:
        raise HTTPException(404)
    f = project_dir(id) / "assets" / f"{aid}.png"
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/png")


@app.delete("/api/clips/{id}")
def delete_clip(id: str, s: DBSession = Depends(session)):
    from uuid import uuid4

    c = get(s, Clip, id)
    s.execute(select(Project).where(Project.id == c.project_id).with_for_update()).scalar_one()
    c = s.scalar(select(Clip).where(Clip.id == id).with_for_update())
    if c is None:
        raise HTTPException(404, "Highlight tidak ditemukan.")
    if s.scalar(select(Job).where(Job.project_id == c.project_id, Job.status.in_(PENDING))):
        raise HTTPException(
            409, "Tunggu pekerjaan proyek selesai atau batalkan sebelum menghapus highlight."
        )
    folder = project_dir(c.project_id).resolve()
    jobs = list(s.scalars(select(Job).where(Job.clip_id == id)))
    targets = []
    for job in jobs:
        jid = str(UUID(job.id))
        for name in (jid + ".mp4", jid + ".partial.mp4", jid + "-work"):
            path = folder / name
            if path.exists():
                if path.is_symlink() or path.resolve().parent != folder:
                    raise HTTPException(409, "Lokasi berkas highlight tidak valid.")
                targets.append(path)
    trash = folder / (".delete-" + str(uuid4()))
    trash.mkdir()
    moved = []
    try:
        for path in targets:
            dest = trash / path.name
            path.rename(dest)
            moved.append((path, dest))
        s.execute(delete(HighlightProposal).where(HighlightProposal.clip_id == id))
        s.execute(delete(Job).where(Job.clip_id == id))
        s.delete(c)
        s.commit()
    except Exception:
        s.rollback()
        for path, dest in reversed(moved):
            dest.rename(path)
        trash.rmdir()
        raise
    shutil.rmtree(trash)
    return {"deleted": id, "files_deleted": len(targets)}


@app.get("/api/projects/{id}/audio-assets")
def list_audio_assets(id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    folder = project_dir(id) / "audio"
    return (
        [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
        if folder.exists()
        else []
    )


@app.post("/api/projects/{id}/audio-assets/upload", status_code=202)
async def upload_audio(
    id: str,
    file: UploadFile = File(...),
    mode: str = Form("audio"),
    s: DBSession = Depends(session),
):
    from uuid import uuid4

    get(s, Project, id)
    if mode not in ("audio", "video"):
        raise HTTPException(422, "Pilih unggah audio atau ekstrak video.")
    folder = project_dir(id) / "audio-inbox"
    folder.mkdir(exist_ok=True)
    aid = str(uuid4())
    path = folder / f"{aid}.media"
    size = 0
    try:
        with path.open("wb") as out:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > MAX_BYTES:
                    raise HTTPException(413, "Unggahan audio/video maksimal 200 MB.")
                out.write(data)
        if not size:
            raise HTTPException(422, "File kosong.")
        return enqueue(
            s,
            id,
            "audio_import",
            payload={
                "mode": mode,
                "asset_id": aid,
                "name": Path(file.filename or "Audio").name[:200],
            },
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.post("/api/projects/{id}/audio-import", status_code=202)
def import_audio_url(id: str, body: AudioImport, s: DBSession = Depends(session)):
    from uuid import uuid4

    get(s, Project, id)
    return enqueue(
        s,
        id,
        "audio_import",
        payload={**body.model_dump(), "mode": "url", "asset_id": str(uuid4())},
    )


@app.get("/api/audio/{id}/{asset_id}")
def serve_audio(id: str, asset_id: str, s: DBSession = Depends(session)):
    get(s, Project, id)
    try:
        metadata = audio_metadata(project_dir(id), asset_id)
    except (ValueError, OSError):
        raise HTTPException(404, "Audio tidak ditemukan.")
    return FileResponse(
        project_dir(id) / "audio" / f"{str(UUID(asset_id))}.m4a", media_type="audio/mp4"
    )


@app.post("/api/projects/{id}/mix", status_code=202)
def retry_mix(id: str, s: DBSession = Depends(session)):
    p = get(s, Project, id)
    if p.workflow == "review":
        raise HTTPException(
            409,
            "Proses atau coba lagi dari usulan highlight agar konfigurasi per highlight tetap dipakai.",
        )
    prior = s.scalar(
        select(Job)
        .where(Job.project_id == id, Job.kind.in_(["analysis", "mix"]))
        .order_by(Job.created_at.desc())
    )
    payload = (
        prior.payload
        if prior and prior.payload.get("visual_mode") == "mix"
        else {
            "gemini_model": p.gemini_model,
            "ai_combo": p.ai_combo,
            "provider": "9router",
            "visual_mode": "mix",
            "mix_hashtags": p.mix_hashtags,
            "source_policy_version": 1,
            "mix_rules_version": 1,
            "instansi_ids": p.instansi_ids,
            "include_global": p.include_global,
            "library": library_snapshot(s, p.mix_hashtags, p.instansi_ids, p.include_global),
        }
    )
    return enqueue(s, id, "mix", payload=payload)


class SubtitleRefineRequest(BaseModel):
    revision: int = Field(ge=1)


class SubtitleApplyRequest(SubtitleRefineRequest):
    job_id: UUID
    caption_ids: list[str] = Field(min_length=1, max_length=10000)


@app.post("/api/clips/{id}/subtitle-refinement", status_code=202, response_model=JobView)
def refine_subtitles(id: str, body: SubtitleRefineRequest, s: DBSession = Depends(session)):
    c = get(s, Clip, id)
    if not c.ready:
        raise HTTPException(409, "Highlight masih diproses.")
    if c.revision != body.revision:
        raise HTTPException(
            409, "Highlight berubah. Simpan dan muat ulang sebelum memeriksa subtitle."
        )
    return enqueue(
        s, c.project_id, "subtitle_refine", c.id, {"plan": c.plan, "revision": c.revision}
    )


@app.post("/api/clips/{id}/subtitle-refinement/apply", response_model=ClipView)
def apply_subtitles(id: str, body: SubtitleApplyRequest, s: DBSession = Depends(session)):
    from .subtitle_refinement import apply_review

    c = s.scalar(select(Clip).where(Clip.id == id).with_for_update())
    if not c:
        raise HTTPException(404)
    j = get(s, Job, str(body.job_id))
    if j.kind != "subtitle_refine" or j.clip_id != id or j.status != "succeeded":
        raise HTTPException(422, "Hasil pemeriksaan subtitle tidak tersedia untuk highlight ini.")
    if c.revision != body.revision or j.result.get("revision") != c.revision:
        raise HTTPException(
            409,
            "Highlight berubah sejak pemeriksaan dimulai. Jalankan Perbaiki subtitle lagi; cache audio tetap digunakan.",
        )
    proposals = j.result.get("proposals", [])
    if not set(body.caption_ids) <= {p["caption_id"] for p in proposals}:
        raise HTTPException(422, "Blok subtitle tidak ditemukan pada hasil pemeriksaan.")
    c.plan = apply_review(upgrade_plan(c.plan), proposals, set(body.caption_ids))
    c.revision += 1
    s.commit()
    return serialize(c)


from .review_audio import router as review_audio_router

app.include_router(review_audio_router)
