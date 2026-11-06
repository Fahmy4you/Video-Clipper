# Usulan highlight dan persetujuan

Home mengirim workflow=review, URL, model, jumlah (1–5), serta arahan opsional.
Klien lama tanpa workflow tetap menggunakan alur legacy.

Analisis awal mengunduh sumber dan membuat transkrip bertahap, lalu satu permintaan
Gemini mengusulkan rentang 30–90 detik. Tidak ada subtitle refinement, Mix,
EditPlan atau persiapan studio pada tahap ini. Menunggu persetujuan tidak
menggunakan slot antrean.

Pada detail proyek, tinjau judul, ringkasan, alasan dan tautan YouTube bertimestamp.
Revisi manual menggunakan HH:MM:SS.mmm atau detik, dinormalisasi ke 30 fps.
Minimum satu detik, maksimum akhir sumber. Transkrip baca saja tersedia dalam
halaman kelompok kata. Revisi tidak meminta Gemini lagi.

Siapkan video menyimpan draft rasio, subtitle, Podcast/Mix, instansi dan Global,
serta hashtag AND per usulan. Simpan pengaturan untuk memproses beberapa usulan
melalui mode seleksi. Proses video mengambil snapshot konfigurasi, revisi serta
kandidat Mix. Rasio terkunci sejak diterima.

Satu pekerjaan build_highlight memperbaiki subtitle, membuat satu clip, menyusun
Mix bila diminta, dan menggunakan kembali media editor bersama. Clip belum
tersedia di studio sampai seluruh tahap selesai. Retry menggunakan snapshot dan
checkpoint; revisi baru tidak memakai plan parsial lama. Pembatalan aktif
menunggu worker berhenti sebelum membuka draft.

API baru:
- GET/POST /api/projects/{id}/proposals
- GET/PATCH/DELETE /api/proposals/{id}
- POST /api/projects/{id}/proposals/process (items: id dan revision)
- GET /api/projects/{id}/transcript-range (start/end frame, offset/limit)

Rasio studio dan ekspor membaca clip.aspect_ratio. Migrasi 0013 menyalin
konfigurasi proyek lama ke clip tanpa mengubah plan atau file. Ekspor tetap
360/720/1080p dari sumber asli, melalui mode penyimpanan yang sudah dikonfigurasi.
