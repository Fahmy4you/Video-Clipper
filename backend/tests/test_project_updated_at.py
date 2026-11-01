import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import db

def test_project_and_highlight_changes_are_tracked_but_reads_are_not(monkeypatch):
    engine=create_engine('sqlite://');db.Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    clock=[datetime(2026,1,1,tzinfo=timezone.utc)]
    monkeypatch.setattr(db,'now',lambda:clock[0])
    with factory() as s:
        p=db.Project(url='https://youtu.be/test');s.add(p);s.commit();pid=p.id
        assert p.updated_at==clock[0]
        clock[0]=datetime(2026,2,1,tzinfo=timezone.utc)
        s.scalars(select(db.Project)).all();s.commit()
        assert p.updated_at.month==1
        p.title=p.title;s.commit();assert p.updated_at.month==1
        p.title='Renamed';s.commit();assert p.updated_at==clock[0]
        c=db.Clip(project_id=pid,title='Highlight',plan={});s.add(c)
        clock[0]=datetime(2026,3,1,tzinfo=timezone.utc);s.commit();assert p.updated_at==clock[0]
        clock[0]=datetime(2026,4,1,tzinfo=timezone.utc)
        c.plan={'version':2};c.revision+=1;s.commit();assert p.updated_at==clock[0]
        clock[0]=datetime(2026,5,1,tzinfo=timezone.utc)
        c.title='Discarded';s.flush();s.rollback();s.refresh(p);assert p.updated_at.month==4
        s.delete(c);s.commit();assert p.updated_at.month==5
        s.delete(p);s.commit();assert s.get(db.Project,pid) is None
    engine.dispose()

def test_migration_preserves_creation_and_existing_project_data():
    path=Path(__file__).parents[1]/'migrations/versions/0009_project_updated_at.py'
    spec=importlib.util.spec_from_file_location('migration0009',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE projects (id TEXT PRIMARY KEY,title TEXT,created_at DATETIME NOT NULL)')
        conn.exec_driver_sql("INSERT INTO projects VALUES ('old','Existing project','2026-01-02 03:04:05')")
        migration.op=Operations(MigrationContext.configure(conn));migration.upgrade()
        row=conn.execute(text('SELECT title,created_at,updated_at FROM projects')).one()
        assert row==('Existing project','2026-01-02 03:04:05','2026-01-02 03:04:05')
        migration.downgrade()
        assert conn.execute(text('SELECT title,created_at FROM projects')).one()==row[:2]
    engine.dispose()
