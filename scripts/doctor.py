import shutil,socket,subprocess
from app.config import settings, ROOT
print('Pemeriksaan workspace:',ROOT)
for cmd in ('node','npm','ffmpeg','ffprobe','redis-server'):
    print(cmd+': '+('tersedia' if shutil.which(cmd) else 'BELUM TERPASANG'))
print('DATABASE_URL: '+('terisi' if settings.database_url else 'BELUM DIISI'))
from app.gemini_connections import connections
try:print('Gemini apikey.json: '+str(len(connections()))+' koneksi terpasang')
except RuntimeError:print('Gemini apikey.json: perlu diperiksa di Pengaturan')
print('Gemini model: dipilih per proyek melalui UI')
