# Setup lokal

## 1. Lokasi

Ubuntu: `/home/fahmy_root/projects/video_clipping`
Windows Explorer: `\\wsl.localhost\Ubuntu\home\fahmy_root\projects\video_clipping`
File konfigurasi: `.env` pada root tersebut. Jangan bagikan isinya di chat atau commit ke Git.

## 2. PostgreSQL 17 Windows

Server yang terdeteksi: service postgresql-x64-17, port 5432. Server sudah listen pada semua alamat,
tetapi pg_hba.conf saat pemeriksaan hanya mengizinkan loopback Windows. Tidak ada konfigurasi database
Windows yang diubah otomatis oleh proyek ini.

Di pgAdmin, sebagai administrator:
1. Login/Group Roles â†’ Create â†’ Login/Group Role. Nama `video_clipping`; aktifkan login; beri password unik.
   Tidak perlu superuser, create role, atau create database untuk akun aplikasi.
2. Databases â†’ Create â†’ Database. Nama `video_clipping`, owner `video_clipping`.
3. Cari IP Windows dari Ubuntu: `ip route show default` (kolom setelah `via`).
4. Cari subnet Ubuntu: `ip -4 route show dev eth0`. Untuk NAT pada sesi ini subnetnya `172.20.240.0/20`.
   Subnet dapat berubah setelah WSL restart; periksa lagi bila koneksi gagal.
5. Tambahkan aturan spesifik di `C:\Program Files\PostgreSQL\17\data\pg_hba.conf`:
   `host video_clipping video_clipping 172.20.240.0/20 scram-sha-256`
   Gunakan subnet WSL aktual. Jangan gunakan trust atau membuka semua database ke semua alamat.
6. Jalankan `SELECT pg_reload_conf();` di Query Tool admin pgAdmin.
7. Bila Windows Firewall memblokir koneksi, buat aturan inbound TCP 5432 terbatas ke subnet WSL.

Isi `.env` menggunakan host Windows aktual:

```dotenv
DATABASE_URL=postgresql+psycopg://video_clipping:PASSWORD_URL_ENCODED@172.20.240.1:5432/video_clipping
GEMINI_API_KEY=
REDIS_URL=redis://127.0.0.1:6381/0
WHISPER_MODEL=base
WHISPER_THREADS=2
```

Password dalam URL harus percent-encoded jika mengandung @, :, /, #, atau karakter URL lain.
Launcher menjalankan Alembic sebelum API bila DATABASE_URL terisi. Untuk migrasi manual:
`.venv/bin/python -m alembic -c backend/alembic.ini upgrade head`

## 3. Gemini

Isi GEMINI_API_KEY milik sendiri di .env. Pilih model melalui dropdown Model Gemini saat membuat proyek.
Daftar diambil dari Gemini API melalui backend. Tombol muat ulang mengambil katalog terbaru.
Pilihan disimpan per proyek dan dapat diubah di editor; job analisis memakai snapshot model saat diantrekan.
Proyek lama tanpa pilihan model harus memilih model terlebih dahulu. GEMINI_MODEL tidak lagi digunakan.
Restart launcher setelah mengubah .env. API key hanya dibaca backend. Tanpa key, transcript lokal tetap
tersimpan dan clip manual dapat dibuat; rekomendasi highlight menampilkan pesan konfigurasi.
Panggilan Gemini memakai kuota akun sendiri dan mengirim teks transcript.

## 4. Menjalankan

Di Ubuntu: `bash scripts/launch.sh`. Di Windows: gunakan `Start-VideoClipping.ps1` pada folder REACT/video_clipping.
Layanan lokal: Redis 6381, FastAPI 8000, Vite 5173. Jangan jalankan dua launcher bersamaan.
`storage/logs/` memuat log layanan. Stop melalui Ctrl+C di terminal launcher.

## 5. Ketergantungan dan data

Python yang tersedia pada Ubuntu adalah 3.12, dipakai melalui .venv (penyesuaian dari rancangan awal 3.11).
Node 22 dipilih untuk frontend. FFmpeg harus tersedia di Ubuntu dengan libass dan libx264.
Model Whisper diunduh saat transkripsi pertama; koneksi internet diperlukan saat itu.
Sumber YouTube dapat dibatasi platform; retry tidak menjamin video private/restricted dapat diakses.

Database menyimpan metadata dan edit plan; MP4 tetap di storage/projects. Cadangkan keduanya.
Tidak ada upload ke Instagram/TikTok atau layanan hosting otomatis.


## Konfigurasi yang sudah berhasil diterapkan

Pada 18 Oktober 2026, database yang diisi pengguna adalah `video_clipper` dengan role `postgres`.
Host Windows adalah `172.20.240.1`, IP Ubuntu `172.20.245.227`. DATABASE_URL sudah diperbaiki,
dan migrasi 0002 selesai. Tidak perlu mengulangi pembuatan database/role dari panduan awal.

Firewall rule `VideoClipping-PostgreSQL-WSL` dan baris pg_hba bertanda `video_clipping` memakai IP Ubuntu /32.
Jika alamat NAT WSL berubah, perbarui hanya kedua aturan proyek dan host DATABASE_URL sesuai alamat aktual.
Aturan lain, autentikasi password, dan firewall Windows tetap dipertahankan.

### Kompatibilitas transkripsi

Gunakan requirements.lock.txt untuk instalasi yang sudah diuji. faster-whisper 1.2.1 memanggil
argumen metadata_errors pada PyAV; PyAV 19 menghapus argumen tersebut. Proyek membatasi PyAV
ke >=16,<17 dan menyertakan tes decode WAV nyata, selain tes timeline/subtitle.
Model Whisper diunduh hanya pada pemakaian pertama ke storage/models. Tahap persiapan model
bisa lebih lama dibanding pemakaian berikutnya; ini terpisah dari transkripsi audio.
