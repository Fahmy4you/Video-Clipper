"""Local runtime checks without exposing credentials or calling paid APIs."""
import importlib,shutil,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
failed=[]
for name in ('fastapi','sqlalchemy','psycopg','celery','redis','yt_dlp','faster_whisper','google.genai','cv2','scenedetect'):
    try:importlib.import_module(name);print(name+': OK')
    except Exception as exc:failed.append(name);print(name+': FAILED ('+type(exc).__name__+')')
for cmd in ('ffmpeg','ffprobe','redis-server'):
    ok=bool(shutil.which(cmd));print(cmd+': '+('OK' if ok else 'MISSING'))
    if not ok:failed.append(cmd)
raise SystemExit(bool(failed))
