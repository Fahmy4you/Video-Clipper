# Upgrade yang berlaku (19 Oktober 2026)

Implementasi empat tahap editor visual per highlight ada pada [VISUAL_EDITOR.md](VISUAL_EDITOR.md).
Dokumen MVP awal berikut disimpan sebagai riwayat.

# Rencana video_clipping

## Keputusan yang disepakati

- Web lokal untuk mengubah podcast YouTube 1–2 orang menjadi clip vertikal.
- Proyek utama /home/fahmy_root/projects/video_clipping di Ubuntu WSL2, tanpa Docker.
- Salinan planning dan launcher Windows di C:\Users\HP\Documents\Kumpulan Website\REACT\video_clipping.
- React + TypeScript + Vite; Tailwind + komponen pola shadcn/Radix; React Router; Zustand.
- FastAPI, Celery, Redis; PostgreSQL 17 Windows + SQLAlchemy + Alembic. SQLite tidak digunakan.
- yt-dlp, faster-whisper INT8 CPU, Gemini configurable, OpenCV/YuNet, PySceneDetect, FFmpeg/libass.
- Satu pekerjaan berat sekaligus. File media/model tetap di Ubuntu. API key hanya di backend.
- Output 9:16 MP4 H.264/AAC; preview 360×640; ekspor 1080×1920 30 fps.
- Bahasa UI Indonesia; pengguna tunggal. Tidak ada login, billing, kolaborasi, atau autopost.
- YouTube dahulu, Instagram dan TikTok kemudian melalui adapter sumber.

## Struktur dan kontrak

apps/web berisi dashboard, editor, konfigurasi dan komponen UI.
backend/app berisi konfigurasi, database, schema, HTTP API, Celery tasks, dan renderer.
backend/migrations menyimpan versi schema PostgreSQL. storage diabaikan Git.

EditPlan menyimpan start/end absolut sumber; words dan layouts memakai waktu relatif clip.
Style menyimpan font, warna, highlight, outline dan margin. Revisi optimistis mencegah tab lama menimpa edit baru.
Preview dan export merender snapshot revisi yang sama. Perubahan pengguna tidak menimpa render aktif.

API: create/list/detail project; start analysis; list/create/edit clip; transcript; preview/export;
job list/detail/cancel/retry; akses MP4 terbatas storage proyek. OpenAPI menjadi sumber kontrak.

## Tahap 1 — pipeline dasar

URL YouTube → metadata/download → audio → timestamp kata → rekomendasi Gemini → clip → ASS → MP4.
Simpan checkpoint source/transcript. Validasi URL, rentang highlight, audio, ruang disk dan error provider.
Job queued/running/succeeded/failed/cancelled. Retry menjaga edit pengguna. Tanpa Gemini, transcript tetap
tersimpan dan clip manual tersedia. Selesai ketika alur nyata menghasilkan MP4 yang dapat diunduh.

## Tahap 2 — editor

Dashboard proyek dan status layanan; editor daftar clip kiri, preview tengah, inspector kanan.
Tema gelap netral dengan aksen hijau mint, panel fungsional, fokus keyboard dan reduced motion.
Trim, koreksi kata/timing, judul, font/warna/outline/posisi, undo/redo sesi, simpan eksplisit dan revision.
Preview engine yang sama, ditandai usang saat edit berubah. Responsive untuk desktop/tablet/mobile.

## Tahap 3 — framing manual dan transisi

Layout source-fit, A, B, split atas–bawah; posisi crop A/B dan timeline segmen dapat diedit.
Cut untuk A→B. Animasi satu↔dua panel 250 ms; crop smoothing untuk orang yang sama; audio kontinu.
Fallback sumber utuh jika framing tidak aman. Animasi harus diverifikasi dengan render, bukan CSS preview.

## Tahap 4 — framing otomatis

Deteksi scene dan wajah hanya pada kandidat clip. YuNet untuk wajah dan tracking; pyannote diarization;
TalkNet adapter eksperimental diuji sebelum default. Audio speaker ID tidak otomatis sama dengan face ID.
Threshold editorial: minimum hold 2,5 s; ignore sahutan <0,8 s; tiga pergantian/4 s → split;
overlap → split jika dua wajah; dominan 3 s → close-up. Low confidence → split atau fit jika wajah kurang.
Semua keputusan dapat dikoreksi. Model berat terisolasi dari MVP, tidak wajib untuk editor manual.

## Tahap 5 — penyempurnaan

Adapter Instagram/TikTok setelah YouTube stabil. Compositor subtitle rounded/background/animasi lanjut.
Optimasi berdasarkan benchmark RAM/render/disk. Dokumentasi setup, backup, resume dan batasan perangkat.

## Pengujian dan penerimaan

- Validasi URL, timeline sumber/clip, timestamp kata, optimistic revision dan render snapshot.
- FFmpeg nyata: resolusi/codec/durasi/audio, subtitle, crop A/B, split, video portrait/landscape.
- Error URL, tanpa audio, provider gagal, disk kurang, cancel, worker restart, retry checkpoint.
- UI 1366/768/390 px; navigasi, empty/loading/error, keyboard, kontras, reduced motion.
- Benchmark podcast 10 menit dan 60 menit, dengan RAM/disk/waktu yang benar-benar diukur.
- Data tersimpan setelah restart; secrets tidak masuk frontend/Git; akses media dibatasi.

## Status

Lihat STATUS.md untuk kondisi implementasi aktual. Rencana ini bukan klaim semua tahap sudah selesai.
