"""Versioned workspace defaults, written only by a new single approval."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import insert

from .db import Base, now
from .timeline import Transition, VisualStyle


class TransitionDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    same: bool = True
    incoming: Transition = Field(default_factory=Transition)
    outgoing: Transition = Field(default_factory=Transition)

    @model_validator(mode="after")
    def sync(self):
        if self.same:
            self.outgoing = self.incoming.model_copy()
        return self


class PreferenceStyle(BaseModel):
    subtitle_style: VisualStyle
    transition_defaults: TransitionDefaults


class PreferenceView(BaseModel):
    version: Literal[1] = 1
    revision: int
    style: PreferenceStyle


class VideoPreference(Base):
    __tablename__ = "video_preferences"
    id = Column(String(32), primary_key=True)
    revision = Column(Integer, nullable=False, default=1)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)


def defaults():
    return {
        "subtitle_style": VisualStyle(
            subtitle_version=1, subtitle_template="sentence", karaoke=False
        ).model_dump(),
        "transition_defaults": TransitionDefaults().model_dump(),
    }


def read(s):
    row = s.get(VideoPreference, "workspace")
    return {
        "version": 1,
        "revision": row.revision if row else 0,
        "style": row.value if row else defaults(),
    }


def remember(s, config):
    if not config.get("subtitle_style"):
        return
    value = {k: config[k] for k in ("subtitle_style", "transition_defaults")}
    query = insert(VideoPreference).values(
        id="workspace", revision=1, value=value, updated_at=now()
    )
    s.execute(
        query.on_conflict_do_update(
            index_elements=["id"],
            set_={"value": value, "revision": VideoPreference.revision + 1, "updated_at": now()},
        )
    )
