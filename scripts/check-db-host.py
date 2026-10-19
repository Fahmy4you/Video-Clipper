
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from app.config import settings
import subprocess
url=make_url(settings.database_url)
host=subprocess.check_output(['sh','-c',"ip route show default | awk '{print $3}'"],text=True).strip()
if url.host not in ('localhost','127.0.0.1'):
    print('Database host already customized')
else:
    engine=create_engine(url.set(host=host),connect_args={'connect_timeout':3})
    try:
        with engine.connect():print('Windows host connection succeeded: '+host)
    except Exception as exc:
        message=str(exc).lower()
        reason='timeout' if 'timeout' in message else 'authentication' if 'password' in message else 'pg_hba rule' if 'pg_hba' in message else type(exc).__name__
        print('Windows host connection failed: '+reason)
    finally:engine.dispose()
