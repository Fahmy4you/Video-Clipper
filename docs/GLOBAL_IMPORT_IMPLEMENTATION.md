# Impor Global dan pencocokan konteks — 23 Oktober 2026

## Hasil

- 59 tautan, 59 ID sumber unik, 59 video Global siap digunakan; tidak ada kegagalan atau duplikat dalam batch ini.
- 250 rentang adegan pada grid 30 fps; 7 rentang penutup/layar akhir dikecualikan dari pilihan otomatis.
- 55 video yang ada saat impor dimulai tetap utuh (54 Cryptowave, 1 Akademi Crypto). Audit membandingkan seluruh metadata, scenes, hashtag, kepemilikan, dan SHA-256 berkas dengan snapshot sebelum impor. Total sekarang 114 video.
- Nama file deskriptif mencantumkan ID TikTok. Semua aset baru tanpa relasi instansi. Hashtag tidak otomatis diberi nama instansi.
- Tidak ada proyek/highlight pada snapshot awal. Tidak dilakukan generate ulang proyek.

## Implementasi

`backend/app/mix_generation.py` memakai petunjuk konteks yang membedakan fakta visual dari ilustrasi tematik, membaca narasi sekitarnya, meminta alasan spesifik, dan membatasi pemilihan seluruh rentang pada adegan yang relevan. Tidak cocok berarti podcast tetap ditampilkan. Filter sumber dan hashtag AND, validator durasi/rentang, edit manual, serta renderer tetap dipertahankan.

`scripts/import_global_collection.py` menerima manifest yang sudah ditinjau. Memeriksa checksum, identitas sumber, metadata, scenes, dan rentang penutup; deduplikasi berdasarkan sumber/hash; menyimpan snapshot sebelum impor; menyalin sumber; membuat proxy/thumbnail melalui mekanisme koleksi yang ada. Impor ulang tidak menimpa koreksi pengguna.

Tidak ada skema database, endpoint, atau halaman baru untuk pekerjaan ini. Penjelasan konteks disimpan di `explain` dan `scenes[].explain`.

## Penggunaan importer dari root proyek WSL

```sh
PYTHONPATH=backend .venv/bin/python scripts/import_global_collection.py storage/imports/global-2026-10-23/approved.json
PYTHONPATH=backend .venv/bin/python scripts/import_global_collection.py storage/imports/global-2026-10-23/approved.json --commit
```

Perintah pertama hanya memeriksa; kedua mengimpor. Jalankan satu proses impor pada satu waktu. Manifest ini sudah diimpor; tidak perlu mengulang untuk menggunakan koleksi.

## Verifikasi

- Seluruh suite backend: 147 pengujian lulus, termasuk 5 pengujian importer baru.
- Build frontend TypeScript/Vite lulus; `git diff --check` lulus.
- Audit seluruh 59 aset: sumber cocok checksum, metadata/scenes/hashtag sesuai, proxy H.264 30 fps, thumbnail tersedia, durasi dan rentang valid.
- Impor ulang nyata menghasilkan 59 `existing` dan `ready`; tidak menambah baris atau mengubah metadata.
- Gemini: 8/8 kasus fixture positif/negatif lulus (masa depan, kemiskinan, sekolah, nafkah, bank salah, ateisme, burnout, klaim peristiwa).
- Gemini dengan metadata koleksi nyata: 6/6 kasus lulus (masa depan, kemiskinan, nostalgia, nafkah, kekayaan, penolakan asosiasi ateisme).
- Browser: API 59 Global, pencarian, pemilihan/reload adegan, playback 8 sampel, pilihan Global/hashtag; mobile 390×844 terang/gelap tanpa overflow dan tanpa page error. Model selector dimock kosong dalam uji browser agar tidak memicu pemeriksaan model berbayar; uji semantik memanggil Gemini nyata.
- Renderer aktual: sisipan Global pada podcast fixture 6 detik, preview 360×640 dan ekspor 1080×1920; audio podcast 300 Hz tetap terjaga. Rentang melintasi penutup ditolak validator.
- Pencocokan AI bersifat generatif. Pengujian memverifikasi contoh-contoh tersebut, bukan menjamin semua narasi selalu dipilih sempurna. Pengguna tetap dapat meninjau/mengganti pilihan dan memperbaiki metadata di koleksi.

## Artefak

- `docs/GLOBAL_COLLECTION_2026-10-23.md`: laporan manusia per video dengan URL, detail koleksi, file, durasi, hashtag, adegan, konteks, batas, dan ketidakpastian.
- `docs/global_collection_2026-10-23.json`: manifest metadata lengkap.
- `storage/imports/global-2026-10-23/`: inventory, hasil unduhan/review, manifest approved, snapshot sebelum impor, hasil impor awal/ulang, audit, semantic-qa, semantic-real-qa, render-qa, export-qa.
- `storage/video-clips/<id>/import-source.json`: provenance sumber dan penutup yang dikecualikan.

Video unduhan sementara dan bukti review tetap disimpan agar dapat diaudit. Sumber lama tidak dipindah atau dihapus. Kartu penutup dikecualikan melalui adegan yang tersedia untuk Mix; berkas asli tetap utuh untuk pemeriksaan manual.
