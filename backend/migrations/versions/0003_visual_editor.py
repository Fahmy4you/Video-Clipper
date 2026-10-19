from alembic import op
import sqlalchemy as sa
from app.timeline import upgrade_plan
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None
def upgrade():
    for c in [sa.Column('aspect_ratio',sa.String(8),nullable=False,server_default='9:16'),sa.Column('highlight_count',sa.Integer(),nullable=False,server_default='3'),sa.Column('additional_prompt',sa.String(4000),nullable=False,server_default=''),sa.Column('analysis_report',sa.JSON(),nullable=False,server_default='{}')]:op.add_column('projects',c)
    op.add_column('clips',sa.Column('legacy_plan',sa.JSON(),nullable=True))
    op.add_column('clips',sa.Column('fulfills_prompt',sa.Boolean(),nullable=False,server_default=sa.false()))
    clips=sa.table('clips',sa.column('id',sa.String),sa.column('plan',sa.JSON),sa.column('legacy_plan',sa.JSON))
    conn=op.get_bind()
    for row in conn.execute(sa.select(clips.c.id,clips.c.plan)).mappings().all():
        if row['plan'].get('version')!=2:conn.execute(clips.update().where(clips.c.id==row['id']).values(legacy_plan=row['plan'],plan=upgrade_plan(row['plan'],row['id'])))
def downgrade():
    op.get_bind().execute(sa.text('UPDATE clips SET plan=legacy_plan WHERE legacy_plan IS NOT NULL'))
    for c in ['legacy_plan','fulfills_prompt']:op.drop_column('clips',c)
    for c in ['aspect_ratio','highlight_count','additional_prompt','analysis_report']:op.drop_column('projects',c)
