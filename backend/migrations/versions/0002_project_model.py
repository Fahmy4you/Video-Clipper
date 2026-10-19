"""Persist an explicit Gemini choice per project; legacy projects choose in UI."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('projects',sa.Column('gemini_model',sa.String(200),nullable=True))
def downgrade():
    op.drop_column('projects','gemini_model')
