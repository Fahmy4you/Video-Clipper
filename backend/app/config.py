from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    database_url: str = ''
    gemini_api_key: str = ''
    redis_url: str = 'redis://127.0.0.1:6381/0'
    whisper_model: str = 'base'
    whisper_threads: int = 2
    library_max_mb: int = 200
    library_max_duration: int = 1800
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
settings = Settings()
STORAGE = ROOT / 'storage'
STORAGE.mkdir(exist_ok=True)
