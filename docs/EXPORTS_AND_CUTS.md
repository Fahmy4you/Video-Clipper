# Ekspor, preview, dan transisi antar-potongan

## Konfigurasi developer

Root .env:
- EXPORT_MODE=global: default, hasil di storage proyek dan tombol Unduh MP4.
- EXPORT_MODE=local: hasil juga disalin otomatis ke folder EXPORT_LOCAL_DIR.
- EXPORT_LOCAL_DIR=C:/Documents/video-clips-ekspor: contoh Windows/WSL, wajib absolut, sudah ada, dapat ditulis.
- Linux native dapat memakai /home/nama/Videos/exports.

.env.example mencantumkan nilai default konfigurasi yang didukung beserta komentar bahasa Indonesia. DATABASE_URL, 9router_base_url, dan 9router_key sengaja kosong dan harus diisi sesuai lingkungan; kredensial asli hanya disimpan di .env. EXPORT_LOCAL_DIR boleh kosong untuk mode global. Konfigurasi backend opsional yang kosong tetap memakai default aplikasi. Perubahan .env memerlukan restart backend dan worker; apikey.json tetap dapat dikelola tanpa restart.

Local selalu menunjuk filesystem komputer backend. Backend WSL menerjemahkan drive Windows menggunakan wslpath; backend Linux remote tidak dapat menulis drive C: pengunjung. Tidak ada path tujuan dari payload browser. Kesalahan konfigurasi hanya memblokir ekspor.

Pekerjaan menyimpan snapshot tujuan. Pemeriksaan folder dilakukan sebelum antre, saat mulai, dan sebelum publikasi. File disalin ke .part, di-flush/fsync, kemudian dipublikasikan tanpa menimpa file yang sudah ada. Nama berisi judul, revisi, dan ID render. Checkpoint render membuat retry penyalinan tidak perlu encoding ulang. Folder pilihan pengguna tidak ikut dihapus saat proyek dihapus.

GET /api/export-config bersifat baca saja. GET /api/exports/{jobId}/download mengirim Content-Disposition attachment. URL media tetap menyediakan playback/range. Browser menentukan lokasi unduhan mode Global.

## Preview stabil

Rendering ringan menggunakan proxy sisipan; rendering berat menggunakan sumber asli sisipan. Preferensi browser lama tetap dibaca. Podcast tetap memakai proxy. Keduanya hanya memengaruhi preview; ekspor menggunakan sumber asli.

Status buffering/kualitas menjadi overlay absolut sehingga tidak mengubah ukuran kanvas. Decoder menunggu timestamp frame hasil decode; target seek terakhir dipakai ketika drag berlangsung cepat. Selama buffering, frame komposisi terakhir ditahan dan semua jalur audio ikut berhenti.

## Transisi

Kotak track Video memilih satu batas aktual dan membuka dock Transisi. Tanpa transisi memakai garis vertikal, pudar hitam Blend, crossfade Layers2, kilatan Zap; Camera menandai shutter. Kotak mendukung keyboard Enter/Space.

EditPlan v2 diperluas dengan transition_version=1 dan transitions yang menyimpan pasangan ID visual kiri/kanan serta value animasi/suara. Waktu batas dihitung dari susunan potongan. visual_id mempertahankan kesinambungan sisipan yang terpecah secara internal karena segmen podcast. Split manual membuat ID visual baru dan batas tanpa efek. Trim mengikuti batas; pasangan baru setelah reorder/hapus tidak mewarisi efek pasangan lama.

Konversi lama mempertahankan pengaturan, memilih keluar dahulu jika aktif lalu masuk, dan tidak mengubah durasi. Cadangan legacy_plan dipertahankan. Tampilan maupun renderer memakai normalisasi yang sama; pembukaan tidak menulis ke database.

Split dan trim podcast/sisipan minimal 30 frame. Potongan lama pendek tetap dapat dibuka dan diekspor; perubahan panjang wajib memenuhi minimum. Penolakan tidak masuk undo/autosave. Filter/subtitle/overlay/audio tidak terikat aturan satu detik.

Renderer menggabungkan visual pada 30 fps dengan transisi simetris di sekitar cut dan durasi keluaran tetap. Crossfade membaca handles sumber kedua sisi; keterbatasan sumber memicu pudar hitam dan pemberitahuan dock. Efek visual berada di bawah subtitle dan overlay. Audio podcast tidak mendapat crossfade otomatis. Camera shutter tetap menggunakan penjadwalan berbasis sampel 48 kHz yang berpusat pada cut.

## Verifikasi

- pytest backend/tests/test_boundaries.py backend/tests/test_export_delivery.py
- node scripts/test-boundaries.cjs
- Build frontend, seluruh regresi backend, browser desktop/laptop/mobile.
- Periksa bounding box kanvas selama buffering, 29/30-frame split/trim, autosave/reload, undo, export/download, dan penyalinan Windows/WSL.


## Pilihan resolusi ekspor

Dialog Ekspor menyediakan 360p, 720p, dan 1080p (default). Dimensi mengikuti rasio proyek. Mode Global memulai unduhan otomatis sekali saat aplikasi terbuka. Jika selesai ketika aplikasi ditutup, gunakan tautan Unduh MP4 saat kembali atau Riwayat ekspor dalam dialog.

Permintaan POST ekspor menerima JSON opsional `{"resolution":360}`. Nilai yang diterima 360, 720, 1080. Permintaan tanpa body tetap memakai 1080. Snapshot pekerjaan mempertahankan resolusi untuk retry. Mode Local menggunakan tujuan .env dan tidak memulai unduhan browser.

Preview studio menyiapkan posisi masuk media di awal, memakai ulang maksimal empat decoder visual, dan menyimpan frame terpilih sampai 64 MiB. Pesan menunggu baru terlihat setelah 400 ms. Persiapan memeriksa posisi penting, lalu decoding berjalan bertahap selama playback.
