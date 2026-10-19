from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from app import main

def setup(monkeypatch,tmp_path,active=False):
    cid='a9db922b-941b-4891-a696-fa5b48a78aae';jid='9021297d-5a74-4821-9da2-e0abe76c8e4b'
    clip=SimpleNamespace(id=cid,project_id='p')
    session=MagicMock();session.get.return_value=clip
    session.scalar.side_effect=[clip,object() if active else None]
    session.scalars.return_value=[SimpleNamespace(id=jid)]
    monkeypatch.setattr(main,'project_dir',lambda _:tmp_path)
    for name in ('source.mp4','other-highlight.mp4',jid+'.mp4',jid+'.partial.mp4'):(tmp_path/name).write_text('media')
    (tmp_path/(jid+'-work')).mkdir();(tmp_path/(jid+'-work')/'frame.png').write_text('frame')
    return session,cid,jid

def test_delete_clip_removes_only_its_outputs(monkeypatch,tmp_path):
    s,cid,jid=setup(monkeypatch,tmp_path)
    result=main.delete_clip(cid,s)
    assert result['files_deleted']==3
    assert sorted(p.name for p in tmp_path.iterdir())==['other-highlight.mp4','source.mp4']
    s.delete.assert_called_once();s.commit.assert_called_once()

def test_busy_project_cannot_delete_rendering_files(monkeypatch,tmp_path):
    s,cid,jid=setup(monkeypatch,tmp_path,True)
    with pytest.raises(HTTPException) as exc:main.delete_clip(cid,s)
    assert exc.value.status_code==409
    assert (tmp_path/(jid+'.mp4')).exists()
    s.delete.assert_not_called()

def test_database_failure_restores_files(monkeypatch,tmp_path):
    s,cid,jid=setup(monkeypatch,tmp_path);s.commit.side_effect=RuntimeError('db unavailable')
    with pytest.raises(RuntimeError):main.delete_clip(cid,s)
    assert (tmp_path/(jid+'.mp4')).read_text()=='media'
    assert (tmp_path/(jid+'-work')/'frame.png').exists()
    assert not list(tmp_path.glob('.delete-*'))
