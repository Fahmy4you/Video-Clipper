# video_clipping

Studio lokal untuk YouTube → transcript → usulan highlight melalui 9Router → edit → MP4.
React/TypeScript/Vite + FastAPI/Celery/Redis. PostgreSQL 17 tetap berada di Windows.

## Mulai

```bash
cd /home/fahmy_root/projects/video_clipping
source ~/.nvm/nvm.sh
nvm use 22
bash scripts/setup.sh
# Isi .env sesuai docs/SETUP.md
npm run dev
```

Buka http://localhost:5173 di Windows. Ctrl+C menghentikan layanan milik launcher.
Redis proyek memakai port 6381, API 8000, frontend 5173.

- [Planning](docs/PROJECT_PLAN.md)
- [Setup PostgreSQL dan 9Router](docs/SETUP.md)
- [Antrean pekerjaan dan 9Router](docs/QUEUE_AND_ROUTER.md)
- [Status implementasi dan pengujian](docs/STATUS.md)

`npm run build` memeriksa TypeScript dan membangun frontend.
`npm test` menjalankan pengujian validasi timeline dan render FFmpeg nyata.
`npm run types` memperbarui kontrak TypeScript dari OpenAPI API yang sedang berjalan.

Video, model, log, dan hasil render berada di storage/ dan tidak masuk Git.
Koneksi AI memakai 9Router. Isi 9router_base_url dan 9router_key pada .env.
Perubahan kedua nilai ini berlaku pada permintaan berikutnya tanpa restart.
Transkripsi audio memakai Whisper lokal: profil Standar (`small`) atau Ringan (`base`) melalui `WHISPER_PROFILE`. Teks transkrip dikirim ke combo pilihan. Perubahan profil membutuhkan restart backend/worker dan tidak menimpa transkrip lama.
Panduan alur baru: [Proyek Transkripsi dan Video](docs/TRANSCRIPTION_PROJECTS.md).


Transcript dikirim ke Gemini untuk highlight; media tidak dikirim ke Gemini oleh aplikasi ini.

## Browser smoke test

`scripts/ui-smoke.cjs` menjalankan smoke test melalui Playwright dengan Edge headless.
Jalankan dari root proyek saat aplikasi aktif, menggunakan environment Node dengan Playwright tersedia.
Untuk runtime eksternal, atur `PLAYWRIGHT_MODULE` ke path modul Playwright tersebut.
Screenshot/report disimpan di storage/qa. Data editor adalah fixture terisolasi di browser,
tidak dimasukkan ke PostgreSQL. Tes ini memeriksa UI, bukan integrasi YouTube/9Router/database.

Lihat docs/STATUS.md sebelum menganggap seluruh roadmap selesai.

Perbaikan transkripsi panjang, pemulihan worker, dan pengujian terbaru: [LONG_VIDEO_RECOVERY](docs/LONG_VIDEO_RECOVERY.md).

Daftar combo 9Router memakai metadata tanpa prompt pengujian. Panduan: [Katalog combo](docs/MODEL_CATALOG.md).

Subtitle highlight: [akurasi, tinjauan koreksi, dan mode per kata](docs/SUBTITLES.md). Koleksi Global baru: [laporan pemeriksaan 31 Oktober](docs/GLOBAL_COLLECTION_2026-10-31.md).

### Kualitas preview sisipan dan waktu sumber

Studio menyediakan **Rendering ringan / Rendering berat — preview lebih detail**. Rendering ringan menggunakan proxy; rendering berat memutar file asli hanya di sekitar playhead. Preferensi tersimpan di browser dan tidak mengubah ekspor atau edit. Format yang tidak didukung browser (misalnya HEVC pada sebagian browser) kembali memakai proxy dengan pemberitahuan. Ekspor tetap membaca sumber asli. Fill dapat memperbesar/crop video; Fit mempertahankan seluruh gambar. Hasil render preview diberi label resolusi yang lebih rendah daripada ekspor.

Kartu highlight menampilkan rentang YouTube berdasarkan edit tersimpan. Rentang bersambung digabung, bagian yang dibuang tetap menjadi celah. Menu **Salin batasan waktu** menghasilkan petunjuk untuk prompt proyek berikutnya; kartu dengan lebih dari dua rentang menyediakan daftar lengkap.

### Kilatan dan suara transisi

Dock kanan sisipan menyediakan animasi **Kilatan** dan suara **Camera shutter** secara terpisah untuk transisi masuk/keluar. Pusat audio berada tepat pada cut; durasi audio tidak berubah mengikuti durasi animasi. Lihat [petunjuk efek transisi](docs/TRANSITION_EFFECTS.md).

### Filter Tajam pada timeline

Tombol **Filter** menambahkan blok Tajam yang mengikuti waktu highlight, dengan slider kekuatan serta target Gambar, Video Podcast, dan Video Sisipan. Filter ikut diekspor dan berbeda dari pilihan rendering preview. Lihat [petunjuk filter dan preview](docs/FILTERS.md).

### Ekspor dan transisi antar-potongan

Pengaturan ekspor developer memakai `EXPORT_MODE` (default `global`) dan `EXPORT_LOCAL_DIR` di root `.env`. Mode Global menyediakan tombol **Unduh MP4**; Local menyalin hasil otomatis ke folder yang sudah ada. Restart backend dan worker setelah mengubah konfigurasi. Lihat [penyimpanan ekspor dan transisi](docs/EXPORTS_AND_CUTS.md).

Klik kotak pada batas track Video untuk mengatur transisi podcast maupun sisipan. Split dan trim video minimal satu detik di kedua hasil; elemen audio, teks, subtitle, gambar, dan filter tetap mengikuti ketelitian frame.

## Code formatting

Install frontend tools with `npm install` and Python development tools with `.venv/bin/python -m pip install -r backend/requirements-dev.txt`.

Run `npm run format` to format application code and `npm run format:check` to verify it. Prettier formats TypeScript, JSX, CSS, JSON configuration, and JavaScript scripts. Ruff formats Python application code, migrations, tests, and scripts. Generated types, dependencies, build output, storage, and user media are excluded.
