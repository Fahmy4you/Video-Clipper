# video_clipping

Studio lokal untuk YouTube → transcript → highlight Gemini → edit → MP4.
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
- [Setup PostgreSQL dan Gemini](docs/SETUP.md)
- [Antrean pekerjaan dan koneksi Gemini cadangan](docs/QUEUE_AND_GEMINI.md)
- [Status implementasi dan pengujian](docs/STATUS.md)

`npm run build` memeriksa TypeScript dan membangun frontend.
`npm test` menjalankan pengujian validasi timeline dan render FFmpeg nyata.
`npm run types` memperbarui kontrak TypeScript dari OpenAPI API yang sedang berjalan.

Video, model, log, dan hasil render berada di storage/ dan tidak masuk Git.
API key Gemini dikelola lewat Pengaturan atau apikey.json di root; perubahan tidak memerlukan restart.
File asli diabaikan Git, template tersedia di apikey.json.example.

Transcript dikirim ke Gemini untuk highlight; media tidak dikirim ke Gemini oleh aplikasi ini.

## Browser smoke test

`scripts/ui-smoke.cjs` menjalankan smoke test melalui Playwright dengan Edge headless.
Jalankan dari root proyek saat aplikasi aktif, menggunakan environment Node dengan Playwright tersedia.
Untuk runtime eksternal, atur `PLAYWRIGHT_MODULE` ke path modul Playwright tersebut.
Screenshot/report disimpan di storage/qa. Data editor adalah fixture terisolasi di browser,
tidak dimasukkan ke PostgreSQL. Tes ini memeriksa UI, bukan integrasi YouTube/Gemini/database.

Lihat docs/STATUS.md sebelum menganggap seluruh roadmap selesai.

Perbaikan transkripsi panjang, pemulihan worker, dan pengujian terbaru: [LONG_VIDEO_RECOVERY](docs/LONG_VIDEO_RECOVERY.md).

Daftar model Gemini memakai metadata tanpa prompt pengujian, cache 24 jam, dan pembaruan latar belakang. Panduan: [Katalog model](docs/MODEL_CATALOG.md).

Subtitle highlight: [akurasi, tinjauan koreksi, dan mode per kata](docs/SUBTITLES.md). Koleksi Global baru: [laporan pemeriksaan 31 Oktober](docs/GLOBAL_COLLECTION_2026-10-31.md).

### Kualitas preview sisipan dan waktu sumber

Studio menyediakan **Sisipan: Ringan / Tajam**. Ringan menggunakan proxy; Tajam memutar file asli hanya di sekitar playhead. Preferensi tersimpan di browser dan tidak mengubah ekspor atau edit. Format yang tidak didukung browser (misalnya HEVC pada sebagian browser) kembali memakai proxy dengan pemberitahuan. Ekspor tetap membaca sumber asli. Fill dapat memperbesar/crop video; Fit mempertahankan seluruh gambar. Hasil render preview diberi label resolusi yang lebih rendah daripada ekspor.

Kartu highlight menampilkan rentang YouTube berdasarkan edit tersimpan. Rentang bersambung digabung, bagian yang dibuang tetap menjadi celah. Menu **Salin batasan waktu** menghasilkan petunjuk untuk prompt proyek berikutnya; kartu dengan lebih dari dua rentang menyediakan daftar lengkap.
