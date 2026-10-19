import shutil,socket,subprocess
from app.config import settings, ROOT
print('Pemeriksaan workspace:',ROOT)
for cmd in ('node','npm','ffmpeg','ffprobe','redis-server'):
    print(cmd+': '+('tersedia' if shutil.which(cmd) else 'BELUM TERPASANG'))
print('DATABASE_URL: '+('terisi' if settings.database_url else 'BELUM DIISI'))
print('GEMINI_API_KEY: '+('terisi' if settings.gemini_api_key else 'BELUM DIISI (clip manual tetap didukung)'))
print('Gemini model: dipilih per proyek melalui UI')
