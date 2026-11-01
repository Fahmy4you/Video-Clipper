# Antrean pekerjaan dan koneksi Gemini

Implementasi 27 Oktober 2026. Jalankan aplikasi dari WSL dengan `npm run dev` di root proyek. Launcher melakukan migrasi sampai 0011, kemudian menjalankan API, Redis, worker Celery, dispatcher antrean, dan frontend. Menutup browser tidak membatalkan pekerjaan; backend dan worker harus tetap hidup.

## Membuat highlight

Formulir langsung mengantrekan proyek dan membuka `/projects` setelah server menerima permintaan. Bisa kembali ke dashboard untuk membuat proyek berikutnya. Tidak ada batas tiga proyek menunggu.

Pada Mix, **Batasi topik sisipan — opsional** berada setelah rasio ekspor dan sebelum prompt tambahan. Hashtag kosong mempertimbangkan seluruh video yang diizinkan sumber Instansi/Global. Beberapa hashtag memakai AND, hanya untuk pemilihan sisipan. Jumlah kandidat siap pakai ditampilkan; nol kandidat tetap boleh dibuat dengan tampilan podcast. Pergantian sumber mempertahankan hashtag pilihan yang kini tidak tersedia agar pengguna dapat melepasnya sendiri. Podcast tidak mengirim filter Mix.

## Antrean

Satu pekerjaan berat aktif secara global. Analisis meliputi unduh, transkripsi, highlight dan Mix; ekspor, render preview, impor audio, proxy/thumbnail/waveform serta persiapan koleksi memakai slot yang sama. Pekerjaan siap berjalan berurutan berdasarkan waktu antrean. Playback langsung, editing, autosave, dan browsing halaman tidak memakai slot tersebut.

Status pekerjaan: queued, running, cancelling, waiting_quota, waiting_service, succeeded, failed, cancelled. UI menampilkan label bahasa Indonesia, tahap, progres, posisi menunggu, koneksi aktif, serta jadwal pemeriksaan ulang jika tersedia. Pekerjaan menunggu kuota/layanan melepas slot. Setelah eligible, prioritasnya memakai waktu antrean awal, tanpa menyela pekerjaan yang sedang aktif. Retry manual pekerjaan gagal/dibatalkan membuat pekerjaan baru di belakang antrean, mempertahankan snapshot dan checkpoint.

PostgreSQL adalah sumber kebenaran; pesan Celery hanya membangunkan worker. Dispatcher memeriksa setiap tiga detik, termasuk ketika broker sempat tidak tersedia. Advisory lock PostgreSQL dan flock pada storage melindungi eksekusi; heartbeat serta owner token membantu memantau pemilik. Proses FFmpeg yang dijalankan melalui media.run mewarisi file lock. Worker memulihkan pekerjaan terputus setelah memperoleh kedua lock. Deployment beberapa worker harus memakai database dan storage bersama, seperti konfigurasi WSL saat ini.

Checkpoint mencakup unduhan lengkap, setiap bagian transkripsi 120 detik, hasil highlight tervalidasi, serta batch Mix. Berkas parsial tidak dianggap selesai. Edit pengguna tidak ditimpa ketika retry. Pembatalan aktif menunggu proses berhenti sebelum melepas slot. Proyek dan pekerjaan awal disimpan dalam satu transaksi; request_id yang sama dengan payload identik tidak membuat proyek kedua, sedangkan perubahan payload dengan ID yang sama ditolak 409.

Jika menjalankan layanan secara terpisah, jalankan juga `PYTHONPATH=backend .venv/bin/python -m app.queue_runtime` selain API dan worker. Launcher sudah menanganinya. Jangan menjalankan skrip impor administratif yang memanggil prepare/FFmpeg langsung secara paralel dengan aplikasi; skrip itu berada di luar jalur antrean aplikasi.

## Koneksi Gemini

Koneksi dikelola melalui Pengaturan atau `apikey.json` di root proyek. Format contoh tersedia
di `apikey.json.example`, sedangkan file asli dan file sementara diabaikan Git dan diblokir dari Vite.
Maksimal lima koneksi dengan ID/nama stabil, key, dan prioritas. Perubahan berlaku sebelum permintaan
berikutnya tanpa restart; permintaan aktif boleh selesai. Key tidak dikembalikan dalam respons API.
Simpan menggunakan revision dari GET /api/gemini-config; perubahan bersamaan ditolak 409.

API pengelolaan: GET/POST /api/gemini-config, PATCH/DELETE /api/gemini-config/{id},
PATCH /api/gemini-config/order, POST /api/gemini-config/{id}/test. Semua respons tersanitasi.
Key lama dari .env dimigrasikan sekali jika file belum ada. Setelah itu JSON menjadi sumber tunggal;
konfigurasi kosong tidak mengambil kembali key lama. JSON rusak menahan pekerjaan Gemini sampai diperbaiki.

Model merupakan gabungan katalog metadata per koneksi, tanpa prompt pengujian. Katalog tersedia tidak menjamin izin generate atau kuota. Riwayat penggunaan nyata dan cooldown disimpan terpisah. Pemrosesan mempertahankan model pilihan; hanya koneksinya yang dapat berganti. Key tidak valid dinonaktifkan; mengganti key menghasilkan identitas baru. Penolakan satu model tidak mematikan model lain. Kesalahan payload/JSON tidak memutar koneksi. Lihat [MODEL_CATALOG.md](MODEL_CATALOG.md) untuk cache 24 jam, pembaruan latar belakang, status, dan API katalog.

Gangguan sementara dicoba maksimal tiga kali per koneksi. Retry-After/RetryInfo penyedia dihormati. Tanpa petunjuk, masa tunggu mulai sekitar satu menit dan meningkat sampai maksimal 15 menit. Batas harian tanpa waktu reset tetap menunggu tombol **Periksa lagi**; aplikasi tidak menebak tengah malam lokal. Tombol tersebut tidak melewati waktu retry yang diketahui.

Retry memakai model dan kebijakan sumber yang tersimpan pada pekerjaan. Memilih model berbeda secara eksplisit di halaman proyek memulai pekerjaan analisis baru, bukan mengubah snapshot pekerjaan lama. Hasil edit tetap dilindungi.

Kuota Google berlaku per proyek, bukan per key; beberapa key dari proyek Google yang sama tidak berarti kuotanya terpisah. Lihat [dokumentasi rate limit Gemini](https://ai.google.dev/gemini-api/docs/rate-limits). Penanganan error mengacu pada [panduan troubleshooting Gemini](https://ai.google.dev/gemini-api/docs/troubleshooting). Mekanisme lock mengacu pada [advisory lock PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS).

## Verifikasi awal antrean

Catatan ini merupakan hasil versi awal; pengujian perubahan JSON/transkripsi panjang dicatat di [LONG_VIDEO_RECOVERY.md](LONG_VIDEO_RECOVERY.md).

- 165 tes backend penuh lulus; dua regresi tambahan untuk cache key invalid dan batas backoff lulus bersama seluruh 15 tes model/koneksi lainnya (17 tes terarah).
- Build TypeScript/Vite dan regenerasi tipe OpenAPI lulus.
- Dua proses OS dengan koneksi PostgreSQL nyata: FIFO, tidak ada eksekusi ganda, pemulihan setelah pemilik dimatikan, checkpoint dipertahankan. Ekspor FFmpeg 1080x1920 dan proxy koleksi nyata juga lulus. Proses memanggil task Celery secara langsung untuk menguji executor, bukan dua worker yang mengambil pesan broker.
- Browser 1366x768 dan 390x844: posisi hashtag, kandidat nol, filter tetap terlihat, payload Podcast, submit idempotent, status antrean, status koneksi, tema terang/gelap, tanpa overflow horizontal dan tanpa error JavaScript. Playback studio diuji saat job berat berstatus aktif.
- Skenario kuota, gangguan layanan, dan tiga koneksi menggunakan respons provider simulasi. Konfigurasi pengguna saat verifikasi hanya berisi koneksi Utama; belum ada uji failover menggunakan tiga key nyata.

Ulangi tes backend dengan `PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q`. Tes integrasi antrean tersedia sebagai `PYTHONPATH=backend .venv/bin/python scripts/verify_queue_postgres.py`; jalankan saat antrean aplikasi kosong. Skrip membuat schema acak qa_queue_* dan media sementara, lalu menghapus schema uji itu saja. Tidak mengubah tabel aplikasi pada schema public. Laporan tersimpan di storage/qa/queue-postgres-report.json.

