import math
import re
from urllib.parse import urlparse, parse_qs
from typing import Literal
from .timeline import EditPlanV2, Ratio
from pydantic import BaseModel, Field, model_validator, field_validator

def youtube_url(value: str) -> str:
    u = urlparse(value.strip())
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('Gunakan URL HTTPS YouTube yang valid.')
    video = ''
    if host == 'youtu.be': video = u.path.strip('/')
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if u.path == '/watch': video = parse_qs(u.query).get('v', [''])[0]
        elif u.path.startswith('/shorts/'): video = u.path.split('/')[2]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
        raise ValueError('Masukkan satu video YouTube, bukan playlist atau live.')
    return 'https://www.youtube.com/watch?v=' + video

class ModelSelection(BaseModel):
    model_config = {'extra':'forbid'}
    gemini_model: str = Field(min_length=1, max_length=200, pattern=r'^gemini-[A-Za-z0-9._-]+$')
class ModelOption(BaseModel):
    id: str
    name: str
class ProjectInput(ModelSelection):
    aspect_ratio: Ratio = '9:16'
    highlight_count: int = Field(default=3,ge=1,le=5)
    additional_prompt: str = Field(default='',max_length=4000)
    model_config = {'extra':'forbid'}
    url: str = Field(max_length=2048)
    _url = field_validator('url')(youtube_url)
class Word(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(max_length=150)
    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start: raise ValueError('Waktu akhir kata harus setelah waktu awal.')
        return self
class Style(BaseModel):
    font: Literal['DejaVu Sans', 'Liberation Sans'] = 'DejaVu Sans'
    size: int = Field(default=62, ge=24, le=100)
    color: str = Field(default='#FFFFFF', pattern=r'^#[0-9A-Fa-f]{6}$')
    highlight: str = Field(default='#5EEAD4', pattern=r'^#[0-9A-Fa-f]{6}$')
    outline: int = Field(default=3, ge=0, le=8)
    margin: int = Field(default=180, ge=40, le=600)
class Layout(BaseModel):
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    mode: Literal['fit', 'a', 'b', 'split'] = 'fit'
    a: float = Field(default=.30, ge=0, le=1)
    b: float = Field(default=.70, ge=0, le=1)
class EditPlan(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    words: list[Word] = Field(default_factory=list, max_length=10000)
    style: Style = Field(default_factory=Style)
    layouts: list[Layout] = Field(default_factory=lambda:[Layout()], min_length=1, max_length=200)
    @model_validator(mode='after')
    def validate_timeline(self):
        if self.end <= self.start: raise ValueError('Akhir clip harus setelah awal.')
        duration = self.end-self.start
        if self.layouts[0].start != 0: raise ValueError('Layout pertama harus dimulai pada detik 0 clip.')
        times = [x.start for x in self.layouts]
        if times != sorted(set(times)) or times[-1] >= duration: raise ValueError('Waktu layout harus berurutan dan berada dalam clip.')
        if any(w.end > duration + .02 for w in self.words): raise ValueError('Timestamp subtitle harus relatif terhadap clip dan di dalam durasinya.')
        if any(a.start > b.start for a,b in zip(self.words, self.words[1:])): raise ValueError('Kata harus berurutan.')
        return self
class ClipInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    plan: EditPlanV2 | EditPlan
class ClipUpdate(ClipInput):
    revision: int = Field(ge=1)
class Highlight(BaseModel):
    fulfills_prompt: bool = False
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    title: str = Field(max_length=200)
    reason: str = Field(max_length=2000)
class Highlights(BaseModel):
    clips: list[Highlight] = Field(max_length=5)
    unmet_requests: list[str] = Field(default_factory=list,max_length=20)


from datetime import datetime
from pydantic import ConfigDict
class ProjectView(BaseModel):
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
class ClipView(BaseModel):
    fulfills_prompt: bool = False
    id: str
    project_id: str
    title: str
    reason: str
    revision: int
    plan: EditPlanV2 | EditPlan
class JobView(BaseModel):
    id: str
    project_id: str
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
    return {'response_mime_type':'application/json','response_json_schema':Highlights.model_json_schema()}
