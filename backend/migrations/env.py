from alembic import context
from app.db import Base, engine
if engine is None: raise RuntimeError('Isi DATABASE_URL di .env sebelum migrasi.')
with engine.connect() as conn:
    context.configure(connection=conn,target_metadata=Base.metadata)
    with context.begin_transaction(): context.run_migrations()
