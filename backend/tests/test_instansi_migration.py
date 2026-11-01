import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_migration_preserves_old_memberships_and_refuses_lossy_downgrade():
    path=Path(__file__).parents[1]/'migrations/versions/0008_video_instansi_many.py'
    spec=importlib.util.spec_from_file_location('migration0008',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE instansi (id VARCHAR(36) PRIMARY KEY)')
        conn.exec_driver_sql("CREATE TABLE video_clip (id VARCHAR(36) PRIMARY KEY,scope VARCHAR(16) NOT NULL,instansi_id VARCHAR(36),CONSTRAINT fk_video_clip_instansi FOREIGN KEY(instansi_id) REFERENCES instansi(id),CONSTRAINT ck_video_clip_scope CHECK ((scope='global' AND instansi_id IS NULL) OR (scope='instansi' AND instansi_id IS NOT NULL)))")
        conn.exec_driver_sql('CREATE INDEX ix_video_clip_instansi_id ON video_clip(instansi_id)')
        conn.exec_driver_sql("INSERT INTO instansi(id) VALUES ('crypto'),('akademi')")
        conn.exec_driver_sql("INSERT INTO video_clip(id,scope,instansi_id) VALUES ('a','instansi','crypto'),('b','instansi','akademi'),('g','global',NULL)")
        migration.op=Operations(MigrationContext.configure(conn));migration.upgrade()
        assert set(conn.execute(sa.text('SELECT video_clip_id,instansi_id FROM instasi_to_video_clips')))=={('a','crypto'),('b','akademi')}
        assert 'instansi_id' not in {c['name'] for c in sa.inspect(conn).get_columns('video_clip')}
        conn.exec_driver_sql("INSERT INTO instasi_to_video_clips(video_clip_id,instansi_id) VALUES ('a','akademi')")
        with pytest.raises(RuntimeError,match='beberapa instansi'):migration.downgrade()
        assert conn.scalar(sa.text('SELECT COUNT(*) FROM instasi_to_video_clips'))==3
        conn.exec_driver_sql("DELETE FROM instasi_to_video_clips WHERE video_clip_id='a' AND instansi_id='akademi'")
        migration.downgrade()
        assert set(conn.execute(sa.text('SELECT id,scope,instansi_id FROM video_clip')))=={('a','instansi','crypto'),('b','instansi','akademi'),('g','global',None)}
    engine.dispose()
