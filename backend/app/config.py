from pathlib import Path
from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = "redis://127.0.0.1:6381/0"
    whisper_profile: Literal["standard", "light"] | None = None
    # Legacy WHISPER_MODEL is accepted only when no profile is configured.
    whisper_model: str = "small"
    whisper_threads: int = 2
    export_mode: str = "global"
    export_local_dir: str = ""
    source_min_duration_seconds: int = 10
    library_max_mb: int = 200
    library_max_duration: int = 1800

    @model_validator(mode="after")
    def resolve_whisper_profile(self):
        models = {"standard": "small", "light": "base"}
        profile = self.whisper_profile
        if profile is None:
            profile = {"small": "standard", "base": "light"}.get(self.whisper_model)
            if profile is None:
                raise ValueError("WHISPER_PROFILE harus standard atau light.")
        self.whisper_profile = profile
        self.whisper_model = models[profile]
        return self

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_ignore_empty=True)


settings = Settings()
STORAGE = ROOT / "storage"
STORAGE.mkdir(exist_ok=True)
