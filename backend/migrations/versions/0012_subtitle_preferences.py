"""Subtitle presentation defaults; saved edits remain intact."""
from alembic import op
import sqlalchemy as sa
revision='0012'
down_revision='0011'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('projects',sa.Column('subtitle_mode',sa.String(16),nullable=False,server_default='sentence'))
    op.add_column('projects',sa.Column('subtitle_animation',sa.String(16),nullable=False,server_default='none'))
def downgrade():
    op.drop_column('projects','subtitle_animation')
    op.drop_column('projects','subtitle_mode')
