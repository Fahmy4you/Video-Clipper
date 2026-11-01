# Katalog Gemini tanpa prompt pengujian

Pengambilan model memakai `models.list` saja. Membuka halaman, menyimpan/mengganti key, refresh katalog,
validasi pembuatan proyek, dan memilih koneksi cadangan tidak mengirim prompt uji. Generate hanya
berjalan untuk pekerjaan pengguna yang sebenarnya. Batas koneksi tetap lima melalui apikey.json.

## Katalog dan status

Metadata diambil dengan page_size 1000 dan pagination, maksimal dua koneksi bersamaan (termasuk
beberapa proses backend yang memakai storage bersama). Setiap permintaan dibatasi 15 detik;
satu siklus koneksi dibatasi 30 detik untuk pengambilan seluruh halaman. Model digabung berdasarkan ID.
Model khusus gambar, audio, live, video dan embedding tidak ditawarkan untuk highlight teks.

Cache berversi disimpan di storage/model-catalog-v1 menurut fingerprint key, tanpa key asli.
Masa segar 24 jam, tetap ada setelah restart. Cache kedaluwarsa tetap tampil sambil diperbarui.
Hasil koneksi cepat langsung tersedia meskipun koneksi lain belum selesai. Halaman/pagination yang
belum lengkap tidak menggantikan cache lengkap. Permintaan bersamaan memakai satu pemeriksaan
per key; dua slot filesystem membatasi metadata secara global. Rename/reorder tidak membatalkan cache.

Refresh gagal mempertahankan cache; pemeriksaan berikutnya dari halaman atau worker baru memenuhi
syarat setelah 1, 5, lalu 15 menit. Retry-After yang lebih lama tetap dihormati. Tidak ada loop
pemeriksaan tanpa pengguna/job yang memerlukan katalog. Tombol refresh juga tidak melewati backoff.

Status metadata, hasil penggunaan nyata, dan cooldown disimpan terpisah. Katalog 200 OK bukan bukti
izin inferensi, billing, kuota tersedia, atau kompatibilitas JSON aplikasi. Cache uji versi sebelumnya
tidak dihitung sebagai riwayat pekerjaan berhasil. Status 'pernah berhasil digunakan' baru dicatat
setelah hasil analisis/Mix nyata lolos validasi skema. JSON/payload gagal tidak memutar key.

Koneksi dipilih menurut prioritas, katalog dan cooldown, dengan model yang sama. Koneksi yang ditolak
untuk satu model tidak menolak model lain. Retry pekerjaan secara eksplisit boleh menghapus penolakan
model yang tersimpan agar pekerjaan asli dicoba kembali; tidak menghapus tenggat cooldown yang diketahui.
Refresh metadata tidak menghapus penolakan/cooldown atau mengaktifkan key yang sudah diketahui invalid.
Jika worker belum memiliki metadata, job menunggu layanan dan melepas slot, sementara katalog dimuat.

## API

- GET /api/model-catalog: snapshot langsung dengan models, connections, refreshing, stale. Jika perlu,
  menjadwalkan metadata di latar belakang. Per koneksi: fetched_at, next_attempt_at, error, model_count.
- POST /api/model-catalog/refresh: 202; body opsional {connection_id}. Frontend membaca snapshot tiap
  dua detik hanya selama pembaruan berjalan. Tidak melewati backoff metadata.
- GET /api/models tetap berbentuk array kompatibel; refresh=true hanya menjadwalkan metadata.
- POST /api/gemini-config/{id}/test: 202 metadata saja; menerima body kosong atau parameter model lama,
  yang tidak memicu inferensi. UI menamainya Periksa katalog.
- Model berisi status catalog/used/waiting_quota/waiting_service/denied, selectable, stale, serta status
  tiap koneksi. Semua ditolak -> selectable=false; kuota menunggu -> tetap dapat masuk antrean.
- Validasi submit hanya membaca katalog lokal (cache kedaluwarsa boleh). Katalog belum ada -> 409;
  model tidak tercantum/semua koneksi menolak -> 422. Tidak menunggu pemeriksaan jaringan.

Lihat [Models](https://ai.google.dev/api/models),
[penjelasan metadata vs izin inferensi](https://ai.google.dev/gemini-api/docs/troubleshooting),
[rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
Kuota berlaku per proyek Google, bukan per API key. Sisa kuota tidak ditebak dari metadata;
lihat Google AI Studio untuk batas dan penggunaan proyek.

## Verifikasi implementasi, 30 Oktober 2026

- Seluruh 197 tes backend lulus; 26 tes katalog/fallback lulus setelah perbaikan konsistensi snapshot.
- Tipe OpenAPI diregenerasi; build TypeScript/Vite lulus.
- Empat koneksi nyata mengembalikan 17 model teks gabungan melalui metadata saja. Tidak menjalankan
  inferensi nyata untuk pengujian. Cache tetap terbaca setelah launcher dimulai ulang; tiga pengukuran
  HTTP lokal cache adalah 63,9 / 7,0 / 6,7 ms (bukan jaminan waktu jaringan pengguna).
- Browser 1366x768 dan 390x844, light/dark: tidak ada overflow atau error console; model baru dapat
  dipilih, penolakan semua koneksi menonaktifkan pilihan, model menunggu kuota tetap dapat dipilih,
  hasil parsial tampil dan polling berhenti. Skenario status/progres memakai fixture browser terisolasi.
- File key tetap diabaikan Git, tidak ada di respons/bundle, dan akses Vite ke file key tetap ditolak.
- Laporan lokal: storage/qa/model-catalog-report.json dan storage/qa/catalog-browser-report.json.
