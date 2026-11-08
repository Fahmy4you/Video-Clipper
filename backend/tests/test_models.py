from types import SimpleNamespace
from unittest.mock import MagicMock


def test_analysis_uses_job_model_snapshot(monkeypatch, tmp_path):
    from app import tasks

    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.get.side_effect = [
        SimpleNamespace(
            status="running",
            kind="analysis",
            project_id="p",
            payload={"gemini_model": "gemini-chosen"},
        ),
        SimpleNamespace(id="p", url="https://example.invalid", gemini_model="gemini-changed-later"),
    ]
    monkeypatch.setattr(tasks, "Session", MagicMock(return_value=fake))
    monkeypatch.setattr(tasks, "project_dir", lambda _: tmp_path)
    monkeypatch.setattr(tasks, "update", MagicMock())
    monkeypatch.setattr(tasks.shutil, "disk_usage", lambda _: SimpleNamespace(free=10 * 1024**3))
    analyze = MagicMock(return_value={"message": "ok"})
    monkeypatch.setattr(tasks, "analyze", analyze)
    tasks.process_job("job")
    assert analyze.call_args.args[4:] == ("gemini-chosen", 3, "")


def test_model_required_in_new_project():
    import pytest
    from app.schemas import ProjectInput
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProjectInput(url="https://youtu.be/dQw4w9WgXcQ")
