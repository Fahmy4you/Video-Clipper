"""Review proposals and per-highlight presentation; preserve legacy edits."""
from alembic import op
import sqlalchemy as sa
revision='0013'
down_revision='0012'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('projects',sa.Column('workflow',sa.String(16),nullable=False,server_default='legacy'))
    op.add_column('clips',sa.Column('ready',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('clips',sa.Column('aspect_ratio',sa.String(8),nullable=False,server_default='9:16'))
    op.add_column('clips',sa.Column('processing_config',sa.JSON(),nullable=False,server_default='{}'))
    op.create_table('highlight_proposals',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('project_id',sa.String(36),sa.ForeignKey('projects.id',ondelete='CASCADE'),nullable=False,index=True),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('title',sa.String(200),nullable=False),
        sa.Column('summary',sa.String(2000),nullable=False),sa.Column('reason',sa.String(2000),nullable=False),
        *[sa.Column(k,sa.Integer(),nullable=False) for k in ('original_start','original_end','start','end')],
        sa.Column('fulfills_prompt',sa.Boolean(),nullable=False),sa.Column('settings',sa.JSON(),nullable=False),
        sa.Column('configured',sa.Boolean(),nullable=False),sa.Column('job_id',sa.String(36)),
        sa.Column('clip_id',sa.String(36),sa.ForeignKey('clips.id',ondelete='SET NULL')),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    for name,col,table in [('proposal_instansi','proposal_id','highlight_proposals'),('clip_instansi','clip_id','clips')]:
        op.create_table(name,sa.Column(col,sa.String(36),sa.ForeignKey(table+'.id',ondelete='CASCADE'),primary_key=True),
            sa.Column('instansi_id',sa.String(36),sa.ForeignKey('instansi.id',ondelete='RESTRICT'),primary_key=True,index=True))
    c=op.get_bind()
    for p in c.execute(sa.text('SELECT * FROM projects')).mappings():
        config={k:p[k] for k in ('aspect_ratio','visual_mode','subtitle_mode','subtitle_animation','include_global','mix_hashtags')}
        c.execute(sa.text('UPDATE clips SET aspect_ratio=:ratio,processing_config=:config WHERE project_id=:id').bindparams(sa.bindparam('config',type_=sa.JSON())),{'ratio':p['aspect_ratio'],'config':config,'id':p['id']})
    c.execute(sa.text('INSERT INTO clip_instansi (clip_id,instansi_id) SELECT c.id,p.instansi_id FROM clips c JOIN project_instansi p ON p.project_id=c.project_id'))
def downgrade():
    op.drop_table('clip_instansi');op.drop_table('proposal_instansi');op.drop_table('highlight_proposals')
    op.drop_column('clips','ready');op.drop_column('clips','processing_config');op.drop_column('clips','aspect_ratio');op.drop_column('projects','workflow')
