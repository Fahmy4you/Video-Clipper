from uuid import uuid4
import subprocess
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app import video_library as lib
from app.db import Base, VideoClip


def test_original_media_seek_and_scope(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(lib, "STORAGE", tmp_path)
    with Session(engine) as s:
        v = VideoClip(title="Original", status="ready")
        s.add(v)
        s.commit()
        aid = v.id
        root = lib.folder(aid)
        root.mkdir(parents=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=320x180:r=30",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                str(root / "test.mp4"),
            ],
            check=True,
        )
        (root / "test.mp4").rename(root / "source.media")
        assert lib.info(v)["source_url"].endswith("/media/original")
        monkeypatch.setattr(
            lib,
            "lookup",
            lambda session, id: v if id == aid else (_ for _ in ()).throw(lib.HTTPException(404)),
        )
        app = FastAPI()
        app.include_router(lib.router)
        app.dependency_overrides[lib.session] = lambda: None
        client = TestClient(app)
        url = "/api/video-clips/" + aid + "/media/original"
        response = client.get(url, headers={"Range": "bytes=0-63"})
        assert response.status_code == 206 and len(response.content) == 64
        assert response.headers["content-type"] == "video/mp4"
        assert response.headers["content-range"].startswith("bytes 0-63/")
        assert client.get("/api/video-clips/" + str(uuid4()) + "/media/original").status_code == 404
        assert client.get("/api/video-clips/" + aid + "/media/source.media").status_code == 404
        (root / "source.media").unlink()
        assert client.get(url).status_code == 404
