import shutil, socket, subprocess
from app.config import settings, ROOT

print("Pemeriksaan workspace:", ROOT)
for cmd in ("node", "npm", "ffmpeg", "ffprobe", "redis-server"):
    print(cmd + ": " + ("tersedia" if shutil.which(cmd) else "BELUM TERPASANG"))
print("DATABASE_URL: " + ("terisi" if settings.database_url else "BELUM DIISI"))
from app.router_ai import configuration, ConfigError

try:
    configuration()
    print("9Router: konfigurasi terpasang")
except ConfigError:
    print("9Router: isi 9router_base_url dan 9router_key pada .env")
print("Combo 9Router: dipilih melalui UI")
