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
REDIS_URL=redis://127.0.0.1:6381/0
WHISPER_MODEL=base
WHISPER_THREADS=2
```

Password dalam URL harus percent-encoded jika mengandung @, :, /, #, atau karakter URL lain.
Launcher menjalankan Alembic sebelum API bila DATABASE_URL terisi. Untuk migrasi manual:
`.venv/bin/python -m alembic -c backend/alembic.ini upgrade head`

## 3. Gemini

Buka Pengaturan → Koneksi Gemini untuk menambah maksimal lima API key. Key disimpan di
`apikey.json` pada root proyek, sejajar `.env`. File asli diabaikan Git; `apikey.json.example`
berisi template kosong. Konfigurasi dibaca ulang tanpa restart.

Untuk mengisi manual, gunakan format berikut di apikey.json (ganti nilai contoh dengan key sendiri):

```json
{"version":1,"connections":[{"id":"utama","name":"Utama","key":"ISI_KEY_SENDIRI","priority":1}]}
```

Setiap koneksi harus memiliki ID unik dan prioritas unik 1–5. Saat menyalin contoh manual, ubah ID juga.
Penambahan lewat Pengaturan membuat ID secara otomatis.

Key lengkap hanya dikirim saat pengguna menyimpan melalui dialog, tidak ditampilkan kembali melalui API.
File asli, lock, dan sementara tidak boleh dimasukkan ke Git. Jangan menaruhnya di folder public.
Pada pemakaian pertama, key lama dari .env dimigrasikan satu kali bila apikey.json belum ada;
setelah itu key Gemini di .env diabaikan. File kosong yang valid berarti tidak ada koneksi.
JSON rusak perlu diperbaiki; aplikasi tidak kembali ke key lama secara diam-diam.

Pilih model dari dropdown saat membuat proyek. Snapshot pekerjaan mempertahankan model;
key cadangan hanya digunakan bila mendukung model yang sama. Tambah/ganti/hapus, urutan prioritas,
dan uji koneksi tersedia di Pengaturan. Database tetap memakai .env dan perubahan database memerlukan restart.
Panggilan Gemini memakai kuota akun sendiri dan mengirim teks transkrip.

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

## Video panjang dan log

Whisper base CPU INT8, dua thread, memproses inti 120 detik dengan konteks dua detik pada kedua sisi.
Checkpoint tiap bagian disimpan di storage/projects/<project-id>/transcription; jangan menghapusnya
jika ingin melanjutkan pekerjaan. Transkrip lengkap lama tetap digunakan. Sumber 1080p dipertahankan.
Proses anak diawasi dengan batas RAM min(2 GiB, 60% RAM Ubuntu); kegagalan suatu bagian dicoba ulang
sekali. Gangguan database/cancel yang dihentikan dengan tertib tidak dihitung sebagai kegagalan model.

Worker yang mati dipulihkan maksimal tiga kali dalam sepuluh menit (jeda 5, 15, 30 detik); halaman dan API
bertahan. Setelah batas habis, periksa log sebelum menjalankan kembali launcher. Jangan menjalankan
build atau tes encoding berat bersamaan dengan transkripsi pada laptop RAM terbatas.

Log layanan: storage/logs/worker.log, api.log, dispatcher.log, web.log, redis.log.
Di File Explorer Windows: \\wsl.localhost\Ubuntu\home\fahmy_root\projects\video_clipping\storage\logs.
Bukti OOM dapat dilihat melalui PowerShell: `wsl -d Ubuntu -- journalctl -k -b -1 --no-pager`.
Lihat docs/LONG_VIDEO_RECOVERY.md untuk diagnosis dan catatan pengujian terbaru.

## Daftar model tanpa prompt uji

Pengaturan menyediakan **Periksa katalog**, yang hanya membaca metadata Google. Cache bertahan 24 jam dan setelah restart. Dropdown dapat menampilkan model yang belum pernah dipakai; katalog tidak menjamin akses generate atau sisa kuota. Lihat [MODEL_CATALOG.md](MODEL_CATALOG.md).
