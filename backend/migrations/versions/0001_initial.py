from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('projects',sa.Column('id',sa.String(36),primary_key=True),sa.Column('url',sa.String(2048),nullable=False),sa.Column('title',sa.String(500),nullable=False),sa.Column('duration',sa.Float,nullable=False),sa.Column('status',sa.String(32),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('clips',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False),sa.Column('title',sa.String(200),nullable=False),sa.Column('reason',sa.String(2000),nullable=False),sa.Column('revision',sa.Integer,nullable=False),sa.Column('plan',sa.JSON,nullable=False))
    op.create_index('ix_clips_project_id','clips',['project_id'])
    op.create_table('jobs',sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id'),nullable=False),sa.Column('clip_id',sa.String(36),sa.ForeignKey('clips.id')),sa.Column('kind',sa.String(24),nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('stage',sa.String(80),nullable=False),sa.Column('progress',sa.Integer,nullable=False),sa.Column('error',sa.String(2000)),sa.Column('payload',sa.JSON,nullable=False),sa.Column('result',sa.JSON,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_jobs_project_id','jobs',['project_id'])
def downgrade():
    op.drop_table('jobs'); op.drop_table('clips'); op.drop_table('projects')
