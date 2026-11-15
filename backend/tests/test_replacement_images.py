from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
import asyncio
import pytest
from fastapi import HTTPException
from PIL import Image
from starlette.datastructures import UploadFile
from app import main


def png_bytes(size=(12, 8)):
    image = Image.new("RGB", size, (30, 180, 90))
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_upload_replacement_image_is_project_scoped_and_listed(monkeypatch, tmp_path):
    project_id = str(uuid4())
    monkeypatch.setattr(main, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "get", lambda _s, _model, _id: SimpleNamespace(id=project_id))
    result = asyncio.run(
        main.upload_replacement_image(
            project_id,
            UploadFile(filename="still.png", file=BytesIO(png_bytes())),
            SimpleNamespace(),
        )
    )
    assert result["replacement"] and result["url"] == f"/api/assets/{project_id}/{result['id']}"
    assert (tmp_path / "replacement-images" / f"{result['id']}.png").is_file()
    assert main.assets(project_id, SimpleNamespace()) == [result]
    assert (
        main.asset(project_id, result["id"], SimpleNamespace()).path.name == result["id"] + ".png"
    )


def test_upload_replacement_image_rejects_over_five_mib(monkeypatch, tmp_path):
    project_id = str(uuid4())
    monkeypatch.setattr(main, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "get", lambda _s, _model, _id: SimpleNamespace(id=project_id))
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            main.upload_replacement_image(
                project_id,
                UploadFile(filename="large.png", file=BytesIO(b"x" * (5 * 1024 * 1024 + 1))),
                SimpleNamespace(),
            )
        )
    assert error.value.status_code == 413


def test_delete_replacement_image_refuses_plan_references(monkeypatch, tmp_path):
    project_id, asset_id = str(uuid4()), str(uuid4())
    folder = tmp_path / "replacement-images"
    folder.mkdir()
    (folder / f"{asset_id}.png").write_bytes(b"still")
    clip = SimpleNamespace(plan={"segments": [{"image_asset_id": asset_id, "broll": []}]})
    calls = [iter([clip]), iter([])]
    session = SimpleNamespace(scalars=lambda _query: next(iter(calls)))
    monkeypatch.setattr(main, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "get", lambda _s, _model, _id: SimpleNamespace(id=project_id))
    with pytest.raises(HTTPException) as error:
        main.delete_replacement_image(project_id, asset_id, session)
    assert error.value.status_code == 409 and (folder / f"{asset_id}.png").exists()


def test_delete_unreferenced_replacement_image(monkeypatch, tmp_path):
    project_id, asset_id = str(uuid4()), str(uuid4())
    folder = tmp_path / "replacement-images"
    folder.mkdir()
    (folder / f"{asset_id}.png").write_bytes(b"still")
    (folder / f"{asset_id}.json").write_text("{}")
    session = SimpleNamespace(scalars=lambda _query: iter([]))
    monkeypatch.setattr(main, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(main, "get", lambda _s, _model, _id: SimpleNamespace(id=project_id))
    assert main.delete_replacement_image(project_id, asset_id, session) == {"deleted": asset_id}
    assert not (folder / f"{asset_id}.png").exists()
    assert not (folder / f"{asset_id}.json").exists()
