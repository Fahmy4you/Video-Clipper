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
- [Status implementasi dan pengujian](docs/STATUS.md)

`npm run build` memeriksa TypeScript dan membangun frontend.
`npm test` menjalankan pengujian validasi timeline dan render FFmpeg nyata.
`npm run types` memperbarui kontrak TypeScript dari OpenAPI API yang sedang berjalan.

Video, model, log, dan hasil render berada di storage/ dan tidak masuk Git.
Transcript dikirim ke Gemini untuk highlight; media tidak dikirim ke Gemini oleh aplikasi ini.

## Browser smoke test

`scripts/ui-smoke.cjs` menjalankan smoke test melalui Playwright dengan Edge headless.
Jalankan dari root proyek saat aplikasi aktif, menggunakan environment Node dengan Playwright tersedia.
Untuk runtime eksternal, atur `PLAYWRIGHT_MODULE` ke path modul Playwright tersebut.
Screenshot/report disimpan di storage/qa. Data editor adalah fixture terisolasi di browser,
tidak dimasukkan ke PostgreSQL. Tes ini memeriksa UI, bukan integrasi YouTube/Gemini/database.

Lihat docs/STATUS.md sebelum menganggap seluruh roadmap selesai.
