# Revisi alur proyek dan studio — 19 Oktober 2026

## Alur yang berlaku

- `/`: dashboard khusus generate (YouTube, rasio, model, jumlah, prompt).
- Setelah submit, job analisis masuk antrean dan aplikasi membuka `/projects`.
- `/projects`: daftar proyek dan status antrean/proses/gagal/siap, diperbarui otomatis.
- `/projects/:id`: daftar highlight proyek. Pilih highlight untuk membuka studio.
- `/projects/:id/clips/:clipId`: studio khusus satu highlight. Daftar highlight, generate dan model
  tidak lagi berada di studio. Panel kiri hanya teks, unggah gambar dan aset gambar.
- Tombol Daftar highlight menyimpan perubahan sebelum kembali. Pindah highlight dilakukan dari daftar.

## Pengelolaan highlight

Jumlah 1–5 pada generate membatasi hasil AI awal. Dari daftar highlight, pengguna bisa menambah
highlight manual dengan judul dan rentang sumber, menduplikasi, mengganti nama, mengedit di studio,
dan menghapusnya. Highlight manual dan duplikat boleh menambah jumlah setelah generate.

DELETE /api/clips/:id menghapus row clip, seluruh job terkait, berkas MP4 preview/ekspor,
partial MP4 dan direktori kerja render berdasarkan UUID job. Video sumber, proxy, transkrip,
aset milik proyek dan highlight lain tetap dipertahankan karena digunakan bersama.
Saat proyek masih memiliki job aktif, hapus ditolak dengan 409 agar worker tidak menulis ulang berkas.
Berkas dipindahkan sementara sebelum transaksi database; jika transaksi gagal berkas dikembalikan.

## Preview dan scrollbar

Scrollbar visual disembunyikan; wheel, touch dan keyboard tetap berfungsi.
Studio memakai tinggi layar tanpa topbar global. Kanvas dihitung dari ruang yang tersedia
dengan ResizeObserver, mempertahankan rasio. Tombol Perbesar preview membuka area video besar
dan dapat dikembalikan dengan Kecilkan preview. Panel samping tetap bisa dilipat.

Uji 1366×768: kanvas 9:16 tinggi 334 px dengan timeline lengkap, dan 612 px pada mode besar.
Highlight baru memakai Fill supaya sumber horizontal mengisi kanvas; highlight lama tidak diubah.
Untuk highlight lama yang masih memiliki letterbox, pilih framing Fill di inspector bila diinginkan.

## Pemilihan model

Daftar model diambil dari API, disaring untuk generateContent teks, lalu diperiksa dengan request
JSON sangat singkat menggunakan skema hasil highlight. Hanya respons valid yang masuk dropdown.
Pemeriksaan ini menggunakan kuota API. Hasil disimpan di cache yang dipisah menurut hash API key;
key dan pesan error mentah tidak disimpan. Keberhasilan di-cache 1 jam, kegagalan 5 menit;
tombol muat ulang memeriksa kembali akses. Pemeriksaan paralel dibatasi empat request.
Error provider 400/403/404/429 pada analisis membatalkan status akses model tersebut di cache.

Pada pengujian akun terpasang, 10 model lolos; gemini-4-argon tidak lolos dan tidak ditampilkan.
Pemeriksaan membuktikan akses dan respons JSON saat diperiksa, bukan jaminan kuota selalu tersedia
atau seluruh transcript panjang pasti diterima. Daftar dapat berubah sesuai akses provider.

## Verifikasi

- 56 tes backend lulus, termasuk akses model/cache per key, penghapusan file, rollback DB,
  larangan delete saat render, serta tes timeline/render terdahulu.
- Tes analisis tambahan memastikan default Fill pada hasil baru.
- Build TypeScript/Vite, regenerasi OpenAPI dan tes operasi editor frontend lulus.
- Browser Edge: generate → antrean → highlight (respons analisis disimulasikan agar tidak
  mengunduh/menganalisis ulang video), lalu studio nyata dengan media dan PostgreSQL asli.
- CRUD nyata: tambah manual, edit teks, simpan saat keluar, rename, duplikat, delete;
  semua highlight pengguna sebelum uji tetap ada, termasuk Clip manual.
- Render nyata satu detik lalu delete: row clip/job hilang, MP4 di filesystem hilang,
  URL media menjadi 404; source tetap dapat dibaca. Delete saat job aktif ditolak.
- Studio dan daftar diperiksa pada lebar 1440/1366/1024/768/390; tidak ditemukan horizontal
  overflow atau page error pada alur uji. Toolbar mobile dan kelima track diperiksa ulang.

Jalankan memakai Start-VideoClipping.ps1 seperti sebelumnya, lalu buka http://localhost:5173.

## Pembaruan preview ringkas — 19 Oktober 2026

- Sidebar navigasi aplikasi disembunyikan khusus di studio; tersedia lagi di daftar highlight/proyek.
- Playback, langkah frame, undo/redo, split, hapus dan render preview berada pada satu baris ikon setinggi 34 px. Tooltip dan aria-label menjelaskan fungsi tombol.
- Riwayat render menjadi menu di header player, tanpa mengurangi tinggi video saat dibuka.
- Tinggi preview 9:16 tanpa mode zoom: 303 px pada viewport 1366×597; 456 px pada 1366×768; 738 px pada 1920×1080; 554 px pada 390×844.
- Scrollbar horizontal timeline memakai bilah tema hijau yang tetap terlihat, tidak bergantung pada auto-hide scrollbar OS. Drag, klik track, panah, Home/End dan PageUp/PageDown menggeser timeline; wheel tetap berfungsi.
- Verifikasi browser Edge pada keempat viewport: playback nyata, langkah frame, popover hasil render, scrollbar drag/wheel/keyboard, sidebar kembali saat keluar studio, tanpa horizontal overflow halaman atau error JavaScript.
- Build TypeScript/Vite lulus. Perubahan ini hanya pada UI; data highlight dan backend tidak diubah.

### Timeline lebih tinggi

Timeline kini setinggi 364 px: track video 78 px, audio 48 px, subtitle/teks/gambar masing-masing 52 px. Halaman studio dapat di-scroll vertikal; tinggi preview dipertahankan. Scrollbar horizontal tetap tersedia, dan timeline bisa diperbesar lagi dengan resize vertikal. Browser diverifikasi pada 1366×597, 1366×768, dan 390×844, termasuk playback dan drag scrollbar.
