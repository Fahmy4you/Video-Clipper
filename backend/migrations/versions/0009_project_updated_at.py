"""Track project modification time; old rows start from their creation date."""
from alembic import op
import sqlalchemy as sa
revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('projects',sa.Column('updated_at',sa.DateTime(timezone=True),nullable=True))
    op.execute('UPDATE projects SET updated_at = created_at WHERE updated_at IS NULL')
    with op.batch_alter_table('projects') as batch:
        batch.alter_column('updated_at',existing_type=sa.DateTime(timezone=True),nullable=False)

def downgrade():
    with op.batch_alter_table('projects') as batch:
        batch.drop_column('updated_at')
