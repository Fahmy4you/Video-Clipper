import math
import re
from urllib.parse import urlparse, parse_qs
from typing import Literal
from .hashtags import Hashtags
from .timeline import EditPlanV2, Ratio
from pydantic import BaseModel, Field, model_validator, field_validator


def youtube_url(value: str) -> str:
    u = urlparse(value.strip())
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Gunakan URL HTTPS YouTube yang valid.")
    video = ""
    if host == "youtu.be":
        video = u.path.strip("/")
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        if u.path == "/watch":
            video = parse_qs(u.query).get("v", [""])[0]
        elif u.path.startswith("/shorts/"):
            video = u.path.split("/")[2]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        raise ValueError("Masukkan satu video YouTube, bukan playlist atau live.")
    return "https://www.youtube.com/watch?v=" + video


class ModelSelection(BaseModel):
    model_config = {"extra": "forbid"}
    gemini_model: str | None = Field(default=None, min_length=1, max_length=200)
    ai_combo: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def chosen(self):
        if not self.ai_combo and not self.gemini_model:
            raise ValueError("Pilih combo 9Router.")
        return self


class ModelConnectionStatus(BaseModel):
    id: str
    label: str
    status: str
    next_attempt_at: str | None = None


class ModelOption(BaseModel):
    id: str
    name: str
    status: str = "catalog"
    selectable: bool = True
    stale: bool = False
    connections: list[ModelConnectionStatus] = Field(default_factory=list)


class CatalogConnection(BaseModel):
    id: str
    label: str
    refreshing: bool
    stale: bool
    fetched_at: str | None = None
    next_attempt_at: str | None = None
    error: str | None = None
    model_count: int


class ModelCatalog(BaseModel):
    models: list[ModelOption]
    connections: list[CatalogConnection]
    refreshing: bool
    stale: bool


class CatalogRefresh(BaseModel):
    connection_id: str | None = None


from uuid import UUID


class ProjectInput(ModelSelection):
    workflow: Literal["legacy", "review"] = "legacy"
    enqueue_analysis: bool = False
    request_id: UUID | None = None
    instansi_ids: list[UUID] = Field(default_factory=list, max_length=100)
    include_global: bool = True

    @model_validator(mode="after")
    def source_policy(self):
        self.instansi_ids = list(dict.fromkeys(self.instansi_ids))
        if not self.instansi_ids:
            self.include_global = True
        return self

    mix_hashtags: Hashtags = Field(default_factory=list)
    visual_mode: Literal["podcast", "mix"] = "podcast"
    subtitle_mode: Literal["sentence", "word"] = "sentence"
    subtitle_animation: Literal["none", "soft_zoom"] = "none"
    aspect_ratio: Ratio = "9:16"
    highlight_count: int = Field(default=3, ge=1, le=5)
    additional_prompt: str = Field(default="", max_length=4000)
    model_config = {"extra": "forbid"}
    url: str = Field(max_length=2048)
    _url = field_validator("url")(youtube_url)


class Word(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(max_length=150)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Waktu akhir kata harus setelah waktu awal.")
        return self


class Style(BaseModel):
    font: Literal["DejaVu Sans", "Liberation Sans"] = "DejaVu Sans"
    size: int = Field(default=62, ge=24, le=100)
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    highlight: str = Field(default="#5EEAD4", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline: int = Field(default=3, ge=0, le=8)
    margin: int = Field(default=180, ge=40, le=600)


class Layout(BaseModel):
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    mode: Literal["fit", "a", "b", "split"] = "fit"
    a: float = Field(default=0.30, ge=0, le=1)
    b: float = Field(default=0.70, ge=0, le=1)


class EditPlan(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    words: list[Word] = Field(default_factory=list, max_length=10000)
    style: Style = Field(default_factory=Style)
    layouts: list[Layout] = Field(default_factory=lambda: [Layout()], min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_timeline(self):
        if self.end <= self.start:
            raise ValueError("Akhir clip harus setelah awal.")
        duration = self.end - self.start
        if self.layouts[0].start != 0:
            raise ValueError("Layout pertama harus dimulai pada detik 0 clip.")
        times = [x.start for x in self.layouts]
        if times != sorted(set(times)) or times[-1] >= duration:
            raise ValueError("Waktu layout harus berurutan dan berada dalam clip.")
        if any(w.end > duration + 0.02 for w in self.words):
            raise ValueError(
                "Timestamp subtitle harus relatif terhadap clip dan di dalam durasinya."
            )
        if any(a.start > b.start for a, b in zip(self.words, self.words[1:])):
            raise ValueError("Kata harus berurutan.")
        return self


class ClipInput(BaseModel):
    aspect_ratio: Ratio | None = None
    processing_config: dict | None = None
    instansi_ids: list[UUID] = Field(default_factory=list)
    title: str = Field(min_length=1, max_length=200)
    plan: EditPlanV2 | EditPlan


class ClipUpdate(ClipInput):
    revision: int = Field(ge=1)


class Highlight(BaseModel):
    summary: str = Field(default="", max_length=2000)
    fulfills_prompt: bool = False
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    title: str = Field(max_length=200)
    reason: str = Field(max_length=2000)


class Highlights(BaseModel):
    clips: list[Highlight] = Field(max_length=5)
    unmet_requests: list[str] = Field(default_factory=list, max_length=20)


from datetime import datetime
from pydantic import ConfigDict


class ProjectView(BaseModel):
    ai_combo: str | None = None
    source_id: str | None = None
    workflow: str = "legacy"
    review_counts: dict = Field(default_factory=dict)
    highlight_request_counts: dict = Field(default_factory=dict)
    instansi_ids: list[str] = Field(default_factory=list)
    include_global: bool = True
    mix_hashtags: Hashtags = Field(default_factory=list)
    visual_mode: Literal["podcast", "mix"] = "podcast"
    subtitle_mode: Literal["sentence", "word"] = "sentence"
    subtitle_animation: Literal["none", "soft_zoom"] = "none"
    aspect_ratio: Ratio
    highlight_count: int
    additional_prompt: str
    analysis_report: dict
    id: str
    gemini_model: str | None
    url: str
    title: str
    duration: float
    status: str
    created_at: datetime
    updated_at: datetime


class ClipView(BaseModel):
    aspect_ratio: Ratio = "9:16"
    processing_config: dict = Field(default_factory=dict)
    instansi_ids: list[str] = Field(default_factory=list)
    fulfills_prompt: bool = False
    id: str
    project_id: str
    title: str
    reason: str
    revision: int
    plan: EditPlanV2 | EditPlan


class JobView(BaseModel):
    heartbeat_at: datetime | None = None
    telemetry: dict = Field(default_factory=dict)
    queue_at: datetime
    next_attempt_at: datetime | None = None
    queue_position: int | None = None
    wait_reason: str | None = None
    connection_label: str | None = None
    id: str
    project_id: str | None
    clip_id: str | None
    kind: str
    status: str
    stage: str
    progress: int
    error: str | None
    payload: dict
    result: dict
    created_at: datetime


def gemini_highlight_config():
    # JSON Schema preserves Pydantic constraints not accepted by the SDK's older Schema type.
    return {
        "response_mime_type": "application/json",
        "response_json_schema": Highlights.model_json_schema(),
    }
