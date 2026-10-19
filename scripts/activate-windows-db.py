
from sqlalchemy import create_engine,inspect
from sqlalchemy.engine import make_url
from dotenv import set_key
from app.config import settings,ROOT
url=make_url(settings.database_url)
if url.host not in ('localhost','127.0.0.1','172.20.240.1'):
    raise SystemExit('Host sudah berbeda. Tidak diubah otomatis.')
target=url.set(host='172.20.240.1')
engine=create_engine(target,connect_args={'connect_timeout':5})
with engine.connect() as conn:
    print('Tables before migration:',inspect(conn).get_table_names())
set_key(str(ROOT/'.env'),'DATABASE_URL',target.render_as_string(hide_password=False),quote_mode='always')
engine.dispose()
print('DATABASE_URL host updated; credentials preserved.')
