import importlib.util,json,hashlib
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base,VideoClip,Instansi

spec=importlib.util.spec_from_file_location("global_import",Path(__file__).parents[2]/"scripts/import_global_collection.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.fixture
def setup(tmp_path,monkeypatch):
    engine=create_engine("sqlite://");Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False)
    monkeypatch.setattr(module,"Session",factory);monkeypatch.setattr(module,"STORAGE",tmp_path)
    monkeypatch.setattr(module,"folder",lambda aid:tmp_path/"video-clips"/aid)
    # Test import transactions/copying independently of the separately tested FFmpeg renderer.
    monkeypatch.setattr(module,"wake",lambda:None)
    source=tmp_path/"input.mp4";source.write_bytes(b"reviewed source bytes")
    entry={"index":1,"source_id":"123456789","url":"https://www.tiktok.com/@test/video/123456789","file":str(source),"sha256":module.digest(source),"filename":"reviewed-footage-123456789.mp4","title":"Footage","hashtags":["inovasi"],"explain":"Visual dan konteks.","scenes":[{"start":0,"end":90,"explain":"Inovasi transportasi."}],"excluded_ranges":[{"start":90,"end":120,"reason":"closing"}],"duration":4,"width":320,"height":180,"reviewed":True,"uncertainty_notes":[]}
    manifest=tmp_path/"approved.json"
    def save(a=entry):manifest.write_text(json.dumps([a]));return manifest
    yield factory,entry,save
    engine.dispose()

def test_import_resumes_without_overwriting_edits(setup):
    factory,entry,save=setup
    result=module.perform(save(),True);aid=result[0]["id"]
    with factory() as s:
        asset=s.get(VideoClip,aid);assert asset.scope=="global" and asset.instansi_ids==[]
        assert asset.hashtags==["inovasi"];assert asset.scenes==entry["scenes"]
        asset.title="User correction";asset.revision+=1;asset.status="ready";s.commit()
    result=module.perform(save(),True)
    with factory() as s:
        assets=list(s.scalars(select(VideoClip)));assert len(assets)==1
        assert assets[0].title=="User correction" and assets[0].revision==2
    assert result[0]["status"]=="existing"
    assert module.digest(module.folder(aid)/"source.media")==entry["sha256"]

def test_duplicate_hash_preserves_existing_institution_ownership(setup):
    factory,entry,save=setup
    with factory() as s:
        owner=Instansi(name="Existing",name_key="existing");s.add(owner)
        old=VideoClip(id=str(uuid4()),scope="instansi",instansi_records=[owner],title="Keep",url_path="input.mp4",status="ready",scenes=[{"start":0,"end":60,"explain":"Keep scene"}]);s.add(old);s.commit();aid=old.id
    result=module.perform(save(),True)
    assert result[0]["id"]==aid and result[0]["status"]=="existing"
    with factory() as s:
        old=s.get(VideoClip,aid);assert old.scope=="instansi" and len(old.instansi_ids)==1
        assert old.title=="Keep" and old.scenes[0]["explain"]=="Keep scene"

def test_review_and_checksum_required(setup):
    _,entry,_=setup
    with pytest.raises(ValueError,match="review required"):module.validate_entry({**entry,"reviewed":False})
    with pytest.raises(ValueError,match="checksum"):module.validate_entry({**entry,"sha256":"bad"})

def test_excluded_closing_and_overlaps_rejected(setup):
    _,entry,_=setup
    with pytest.raises(ValueError,match="closing"):module.validate_entry({**entry,"scenes":[{"start":0,"end":100,"explain":"Wrong"}]})
    with pytest.raises(ValueError,match="overlaps"):module.validate_entry({**entry,"scenes":[{"start":0,"end":60,"explain":"First"},{"start":30,"end":90,"explain":"Second"}]})
    with pytest.raises(ValueError,match="curated"):module.validate_entry({**entry,"scenes":[]})

def test_dry_run_does_not_create_assets_or_tags(setup):
    factory,entry,save=setup
    result=module.perform(save(),False);assert result[0]["status"]=="would_import"
    with factory() as s:assert list(s.scalars(select(VideoClip)))==[]
    assert not (Path(entry["file"]).parent/"video-clips").exists()


def test_youtube_identity_and_queue_resume(setup):
    factory,entry,save=setup
    from app.db import Job
    entry.update(provider='youtube',source_id='pVGGOn_ntdg',url='https://www.youtube.com/watch?v=pVGGOn_ntdg')
    first=module.perform(save(),True);module.perform(save(),True)
    with factory() as s:
        jobs=list(s.scalars(select(Job)))
        assert len(jobs)==1 and jobs[0].kind=='library' and jobs[0].library_id==first[0]['id']
    assert module.source_key(entry)=='https://www.youtube.com/watch?v=pVGGOn_ntdg'
