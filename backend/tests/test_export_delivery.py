from pathlib import Path
import pytest
from app.export_delivery import validate,deliver,filename,config_view
from app.config import settings

def test_config_errors_do_not_crash_settings(monkeypatch):
    monkeypatch.setattr(settings,"export_mode","incorrect")
    assert not config_view()["ready"]
    with pytest.raises(ValueError):validate({"mode":"local","local_dir":""})
    with pytest.raises(ValueError):validate({"mode":"local","local_dir":"relative/folder"})
    assert validate({"mode":"global"}) is None

def test_atomic_delivery_retry_and_no_overwrite(tmp_path):
    folder=tmp_path/"Folder with spaces";folder.mkdir();source=tmp_path/"source.mp4";source.write_bytes(b"real rendered file"*100)
    config={"mode":"local","local_dir":str(folder)}
    result=deliver(source,config,"test.mp4");assert result["delivery_status"]=="saved"
    assert (folder/"test.mp4").read_bytes()==source.read_bytes()
    assert deliver(source,config,"test.mp4")==result
    source.write_bytes(b"different")
    with pytest.raises(ValueError):deliver(source,config,"test.mp4")
    assert not list(folder.glob("*.part"))
    def cancel():raise RuntimeError("cancel")
    with pytest.raises(RuntimeError):deliver(source,config,"cancel.mp4",cancel)
    assert not (folder/"cancel.mp4").exists() and not list(folder.glob("*.part"))
    assert deliver(source,{"mode":"global"},"g.mp4")["delivery_status"]=="ready"

def test_missing_permissions_filename(tmp_path,monkeypatch):
    with pytest.raises(ValueError):validate({"mode":"local","local_dir":str(tmp_path/"gone")})
    import app.export_delivery as module
    monkeypatch.setattr(module.tempfile,"NamedTemporaryFile",lambda **kw:(_ for _ in ()).throw(PermissionError()))
    with pytest.raises(ValueError,match="ditulis"):validate({"mode":"local","local_dir":str(tmp_path)})
    name=filename('  a/b:video?* 🌟'*50,3,"job")
    assert "/" not in name and len(name.encode())<255 and name.endswith("-r3-job.mp4")
