# Revisi terbaru: alur proyek dan studio

Lihat [PROJECT_FLOW.md](PROJECT_FLOW.md) untuk navigasi baru, CRUD highlight, preview besar,
filter akses model dan hasil verifikasi. Revisi ini menggantikan alur studio lama di bawah.

# Status terkini — 19 Oktober 2026

Upgrade editor visual EditPlan v2 sudah diterapkan. Panduan fitur, migrasi, batas dan bukti
pengujian ada di [VISUAL_EDITOR.md](VISUAL_EDITOR.md). Migrasi database mencapai 0003.
Proyek sampel YouTube dan tiga highlight asli dipertahankan. Aplikasi berjalan pada localhost:5173.

Catatan bertanggal 17–18 Oktober di bawah adalah riwayat, bukan daftar pekerjaan terbaru.

---

# Status implementasi video_clipping

Diperbarui: 18 Oktober 2026 (Asia/Jakarta).

## Sudah dibuat

- Monorepo React/TypeScript/Vite dan backend Python/FastAPI di Ubuntu WSL2.
- Dashboard, halaman konfigurasi, editor clip/subtitle, preset, undo/redo, trim dan layout manual.
- API PostgreSQL dengan SQLAlchemy, migrasi Alembic dan konflik revisi edit.
- Celery + Redis khusus proyek pada port 6381; satu pekerjaan berat sekaligus.
- Pipeline yt-dlp â†’ faster-whisper â†’ Gemini; checkpoint source/transcript dan retry.
- Renderer FFmpeg untuk preview 360Ã—640 dan ekspor 1080Ã—1920, ASS highlight kata, crop A/B/split.
- Snapshot edit pada render; cancel/retry job; pemulihan job terhenti saat launcher dimulai ulang.
- Launcher satu perintah, log lokal, .env.example, lockfile npm dan Python.
- Kontrak frontend dihasilkan dari OpenAPI; akses perubahan API dibatasi origin lokal.

## Verifikasi yang sudah dilakukan

- Build produksi frontend dan pemeriksaan TypeScript: lulus.
- 18 tes backend: lulus, termasuk render FFmpeg nyata dengan audio, subtitle, crop dan split.
- Browser Edge pada lebar 1366/768/390 px: tidak ada horizontal overflow atau page error.
- Alur editor menggunakan fixture terisolasi: ubah judul, undo, redo, simpan, split dan save-before-preview lulus.
- Dashboard dan konfigurasi diuji terhadap backend lokal yang benar-benar berjalan.
- Semua modul pipeline berhasil diimpor; pip check tidak menemukan dependency rusak.
- Launcher lengkap berhasil: FastAPI, Vite, Redis dan Celery worker ready.

## Belum terverifikasi / belum selesai

- DATABASE_URL dan GEMINI_API_KEY telah diisi; koneksi PostgreSQL sudah diperbaiki.
- Koneksi PostgreSQL Windows, migrasi sampai 0002, dan persistensi proyek/model sudah diuji nyata dan lulus.
- Download YouTube, transkripsi model Whisper dan panggilan Gemini end-to-end belum dijalankan.
- Model Whisper akan diunduh pada transkripsi pertama. Penggunaan RAM/waktu podcast 10/60 menit belum diukur.
- Framing otomatis (YuNet/tracking/pyannote/TalkNet) belum diimplementasikan. Paket visual terpasang sebagai fondasi.
- Pergantian layout manual saat ini CUT; animasi panel 250 ms dan crop smoothing belum tersedia.
- Subtitle rounded/background compositor dan adapter Instagram/TikTok masih tahap lanjutan.
- Label lulus pada tes UI fixture tidak berarti database atau layanan AI nyata sudah lulus.

## Langkah selanjutnya

1. Konfigurasi database dan key selesai; frontend, API, worker, dan Redis sudah berjalan.
2. Pengujian persistensi proyek/model selesai. Penyimpanan clip/revisi masih perlu uji alur video nyata.
3. Uji satu URL podcast YouTube dengan akun Gemini pengguna; perbaiki masalah integrasi yang ditemukan.
4. Setelah MVP end-to-end terverifikasi, lanjutkan animasi manual, framing otomatis dan benchmark.

## Menjalankan

Ubuntu: `bash /home/fahmy_root/projects/video_clipping/scripts/launch.sh`
Windows: `Start-VideoClipping.ps1` di folder REACT/video_clipping.
Browser: http://localhost:5173
API: http://localhost:8000/docs

Backend membaca .env saat startup; restart launcher setelah mengganti konfigurasi.


## Pembaruan: pilihan model dan Poppins

- Dropdown model teks Gemini dimuat dari API, dengan loading/error/empty dan tombol refresh.
- Nama model disimpan per proyek dan pada snapshot job, bukan di .env.
- Proyek lama dapat memilih/mengganti model dari panel editor. Migrasi 0002 menambahkan kolom nullable.
- Poppins 400/500/600 disajikan lokal dengan lisensi OFL; berlaku untuk antarmuka, bukan font video otomatis.
- Daftar model nyata berhasil dimuat dengan API key pengguna. Tidak ada panggilan generateContent untuk pengujian.
- Build dan 24 tes backend lulus. Browser menguji font, daftar nyata, submit model, dan pemulihan error melalui fixture.
- Koneksi DB berhasil setelah aturan firewall dan pg_hba khusus Ubuntu ditambahkan serta DATABASE_URL memakai host Windows.
  Migrasi 0002 sudah diterapkan. Model proyek berhasil dibuat, dibaca, dan diubah melalui API nyata.


## Perbaikan koneksi PostgreSQL Windows–Ubuntu

- PostgreSQL Windows tetap pada instalasi yang sama, database `video_clipper`, role sesuai konfigurasi pengguna.
- DATABASE_URL menggunakan host Windows `172.20.240.1:5432` (menggantikan localhost Ubuntu).
- Firewall rule `VideoClipping-PostgreSQL-WSL` mengizinkan TCP 5432 hanya dari Ubuntu `172.20.245.227/32`
  ke alamat host WSL, dibatasi ke executable postgres.exe. Firewall tetap aktif.
- pg_hba mengizinkan hanya database/role proyek dari IP tersebut, dengan scram-sha-256.
- Backup pg_hba dibuat di folder data PostgreSQL sebelum perubahan, lalu konfigurasi di-reload tanpa restart database.
- Kredensial asli diverifikasi melalui Windows dan Ubuntu; password tidak dicetak atau diubah.
- API health database/Redis/FFmpeg/Gemini siap. Migrasi mencapai 0002.
- Pengujian create/read/update model menggunakan PostgreSQL nyata lulus; fixture proyek telah dihapus.
- Alamat WSL NAT dapat berubah setelah restart Windows/WSL. Jika itu terjadi, cocokkan host DATABASE_URL,
  RemoteAddress pada firewall rule proyek, dan alamat pada baris pg_hba bertanda video_clipping.
  Jangan membuka semua alamat atau mengganti autentikasi menjadi trust.

## Pengujian video nyata (18 Oktober 2026, sedang berlangsung)

- Sumber: https://youtu.be/K-iDtHzEzu8 (22 menit 44 detik), proyek a6f2c6fa-b1a7-4473-92b9-1c8fec6dbc07.
- Unduhan YouTube dan ekstraksi audio berhasil; model Whisper base tersimpan lokal.
- Ditemukan PyAV 19 tidak kompatibel dengan pemanggilan metadata_errors faster-whisper 1.2.1.
  PyAV dibatasi >=16,<17 dan lock diperbarui ke 16.0.1. Tes decode WAV nyata ditambahkan.
- 29 tes backend lulus; pip check tidak menemukan dependensi rusak.
- Subtitle dikelompokkan berdasarkan jeda, batas kalimat, jumlah karakter, dan durasi.
- Batas clip diselaraskan ke timestamp kata; prompt meminta cerita tuntas dan topik tidak tumpang tindih.
- Tahap persiapan model dibedakan dari transkripsi, serta unduhan menampilkan progres file.
- Job lanjutan: fc637e24-8490-4412-9cf6-81d005aeee83. Hasil render belum dinyatakan lulus sebelum ditinjau.

### Pengujian Gemini nyata

Transkripsi sumber selesai dalam sekitar 6 menit. Permintaan awal mengungkap:
- SDK menolak exclusiveMinimum saat response_schema memakai tipe Schema lama. Permintaan sekarang
  memakai response_json_schema, dengan validasi Pydantic tetap dilakukan pada hasil.
- Katalog Gemini mencantumkan 2.5 Flash, tetapi generateContent mengembalikan 404 untuk akun ini.
  Proyek sampel diubah ke gemini-3.8-flash sesuai respons penyedia; model tetap pilihan per proyek.
- Analisis dengan model pengganti berhasil dan menghasilkan tiga clip. Tidak ada pengulangan transkripsi.
- Error Gemini 400/403/404/429 sekarang dijelaskan secara aman dalam bahasa Indonesia.
- Tes SDK menggunakan transport yang dimock, sehingga menguji serialisasi nyata tanpa panggilan berbayar.
- Preview 9:16 berhasil. Subtitle sumber masih mengandung kesalahan ASR; sedang diperiksa ulang
  dengan Whisper small khusus pada tiga clip terpilih. Belum diklaim sebagai subtitle sempurna.

## Hasil final pengujian video (18 Oktober 2026)

- Analisis nyata sukses dengan gemini-3.8-flash: job acf7a798-9439-4969-939a-ecaa04a6867f.
- Tiga MP4 1080x1920 (H.264 + AAC) selesai: 40.23, 47.57, dan 51.00 detik.
- Seluruh ekspor lolos decode video/audio penuh FFmpeg; durasi cocok dengan timeline (toleransi 0.15 detik).
- Crop tengah mengikuti potongan kamera sumber. Wajah dan subtitle ditinjau pada sampel frame tiap clip.
- Subtitle sampel dikoreksi dengan audio asli via Gemini (94 koreksi token), kemudian batas pembukaan
  dua clip dirapikan. Koreksi audio ini dilakukan untuk sampel melalui skrip QA, belum menjadi fitur UI.
- Unduhan model Whisper small dihentikan karena lambat; tidak digunakan dalam hasil final.
- Subtitle tetap hasil ASR + koreksi AI, bukan transkripsi manusia terverifikasi penuh.
- Preview ketiga clip sudah diperbarui ke revisi 3. Ekspor dapat diunduh dari halaman editor.
- 30 tes backend lulus dan pip check bersih. Browser nyata: Poppins termuat, tidak ada error JavaScript.
- Laporan teknis: storage/qa/video-test/exports.json; salinan MP4 dan laporan ada pada outputs chat.
- Skrip scripts/*sample*.py dan scripts/review_corrections.py adalah QA khusus video ini,
  bukan perintah yang perlu dijalankan ulang untuk pemakaian aplikasi biasa.
