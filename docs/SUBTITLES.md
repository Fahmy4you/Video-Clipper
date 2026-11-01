# Subtitle highlight dan animasi

Podcast lengkap tetap memakai Whisper base. Sesudah highlight dipilih, audio sumber highlight beserta dua detik konteks diperiksa ulang dengan Whisper small CPU INT8. Model pertama kali perlu diunduh ke storage/models; progres menampilkan tahap persiapan. Kedua model tidak dimuat bersamaan. Ini proses lokal tanpa permintaan Gemini tambahan.

Hasil disimpan per sumber/rentang/model/konfigurasi di storage/projects/<id>/subtitle-refinement. Satu bagian memuat maksimal 120 detik inti. Proses mengikuti antrean berat dan batas memori yang sama. Jika perbaikan gagal, subtitle awal tetap tersedia dengan pemberitahuan di studio. Hasil tidak dijamin bebas kesalahan; nilai keyakinan dipakai untuk menandai kata yang perlu didengarkan kembali.

## Highlight lama

Klik Perbaiki subtitle. Simpan draft sebelum mengantrekan. Setelah selesai, Tinjau hasil menampilkan teks tersimpan dan hasil audio, serta playback sumber. Pilih blok yang disetujui lalu Terapkan. Hasil tidak diterapkan otomatis. Revisi yang berbeda menolak penerapan dan meminta pemeriksaan ulang, memakai cache audio. Subtitle yang telah dihapus tidak dihidupkan kembali.

POST /api/clips/{id}/subtitle-refinement menerima revision dan mengembalikan JobView (202). POST /api/clips/{id}/subtitle-refinement/apply menerima revision, job_id, caption_ids; respons ClipView. Konflik menghasilkan 409. Penerapan hanya mengubah caption terpilih.

## Tampilan

Pembuatan proyek menyediakan subtitle_mode sentence/word dan subtitle_animation none/soft_zoom. Default proyek lama maupun baru: sentence + none. Preferensi disimpan di proyek, snapshot pekerjaan, dan subtitle_style EditPlan v2. Studio dapat mengubahnya untuk seluruh subtitle atau blok tertentu, tanpa transkripsi ulang.

Kata per kata hanya menampilkan kata aktif, dengan celah hening kosong. Zoom memakai maksimal empat frame masuk/keluar, dipendekkan untuk kata singkat, 90% ke 100% lalu 96% sebelum hilang. Aturan frame/easing identik di TypeScript dan Python. Animasi konten video tidak mengikuti tema atau preferensi reduced-motion aplikasi karena merupakan bagian hasil video yang dipilih pengguna.

Edit jumlah kata mempertahankan timing kata yang cocok; kata tambahan diberi timing perkiraan lokal dan ditandai untuk diperiksa. Tidak ada penggantian otomatis mass menjadi emas.

Verifikasi otomatis: pytest backend/tests/test_subtitle_refinement.py; node scripts/test-editor-model.cjs; node scripts/test-subtitle-presentation.cjs. Laporan uji lokal audio berada di storage/qa/subtitle-quality.json jika berhasil dijalankan.

## Menyiapkan model sebelum pekerjaan pertama

Unduhan bobot small sekitar 484 MB. Pada internet lambat, siapkan cache tanpa memuat model atau mengambil slot encoding:

```bash
PYTHONPATH=backend .venv/bin/python scripts/prepare_subtitle_model.py
```

Periksa cache tanpa internet dengan menambahkan `--offline`. Pengunduhan tetap dapat dilanjutkan melalui cache unduhan; jangan menaruh file unduhan sebagian sebagai model selesai. Setelah cache siap, pekerjaan berikutnya langsung memuat model lokal. Ini tidak memerlukan restart aplikasi atau API key Gemini.

## Hasil verifikasi lokal — 31 Oktober 2026

- Lima rentang audio sumber diuji dengan Whisper small CPU INT8, dua thread. Uji awal tanpa cache audio memerlukan 68,53 detik untuk 64 detik inti, dengan puncak 678.768.640 byte RAM. Percobaan frasa konteks terakhir menggunakan cache rentang contoh dan selesai 49,19 detik. Angka ini bukan estimasi untuk seluruh podcast.
- Petunjuk kosakata umum masih menghasilkan “mas”. Petunjuk frasa yang dibatasi konteks sumber kemudian menghasilkan “mining emas” dan “tambang emas” pada sampel pendek. Tidak ada penggantian kata global.
- Pemeriksaan highlight asli melalui antrean menghasilkan 33 usulan blok, termasuk “mining emas”. Ada kata lain yang masih perlu didengarkan kembali; hasil tidak diterapkan otomatis. Revisi edit pengguna tetap 2.
- Browser: desktop 1366×768, mobile 390×844, tema terang/gelap, dialog tinjauan, penerapan blok pada fixture terisolasi, autosave mode/animasi, Escape, dan playback podcast asli. Tidak ditemukan page error atau overflow horizontal pada pemeriksaan tersebut.
- Ekspor uji: 1080×1920, 60 frame, video dan audio masing-masing 2,000 detik. Batas teks preview/ekspor pada frame pembanding berbeda satu piksel setelah acuan ink baseline disamakan.
- Seluruh enam impor Global siap, proxy tersedia, checksum sama, tanpa instansi. Snapshot memverifikasi metadata koleksi dan edit highlight sebelumnya tidak berubah. Dua URL tetap tertunda sesuai laporan impor.
- Berkas potongan unduhan sementara di Temp Windows masih ada karena pemeriksaan persetujuan otomatis menolak penghapusannya; bobot utama yang dipakai aplikasi sudah diverifikasi SHA-256.
