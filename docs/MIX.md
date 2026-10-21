# Fade audio dan mode Mix

HyperFrames belum digunakan. Implementasi memakai preview Canvas/browser dan ekspor FFmpeg yang sudah ada.

## Menggunakan fitur

1. Buka **Koleksi video** melalui ikon film di sidebar. Unggah video, lalu pilih **Edit & tandai adegan**.
2. Isi judul, hashtag, dan explain mengenai apa yang benar-benar terlihat. Adegan opsional dipilih dengan menyeret rentang pada preview sumber; setiap adegan punya penjelasan sendiri.
3. Dashboard menyediakan **Podcast saja** (default) atau **Mix**. Mode Mix menyusun sisipan sesudah highlight ditemukan. Hashtag opsional membatasi kandidat ke klip dengan minimal satu label terpilih (OR); tanpa pilihan memakai semua klip siap pakai. Tidak ada kandidat cocok berarti tetap podcast, tanpa keluar dari filter. Koleksi, hashtag, dan model di-snapshot pada job; hasil pilihan disimpan untuk retry.
4. Di studio, klik **Tambah video sisipan**, atau split podcast di awal/akhir rentang lalu pilih **Ganti potongan ini dengan klip**. Pilih footage, geser bagian sumber, dan konfirmasi.
5. Pilih blok sisipan untuk **Ubah bagian klip**, **Replace klip**, framing, transisi, atau **Kembalikan ke podcast**. Modal sumber mengunci durasi slot; trim dilakukan pada timeline utama. Sisipan tidak mengubah durasi, audio podcast, maupun subtitle.
6. Duplikasi sisipan meminta area kosong. Drag dapat melewati batas potongan podcast; bagian terkait tetap mengikuti potongan saat reorder. Split mempertahankan urutan frame sumber.
7. Klik waveform sumber untuk volume dan fade keseluruhan highlight. Klik audio tambahan untuk volume dan fade blok tersebut. Durasi 0 mematikan fade; split mempertahankan envelope yang sedang berjalan.

## Aturan otomatis dan penyimpanan

- Sisipan 2–5 detik, total maksimal 30%, awal/akhir minimal 2 detik podcast, jarak antarsisipan minimal 3 detik, tanpa pengulangan aset.
- Pemilihan memakai teks transkrip dan deskripsi koleksi, bukan analisis gambar. Jika ada adegan terkurasi, rentang sumber harus berada di dalam salah satunya.
- Tidak ada bahan yang cocok: gambar tetap podcast dan laporan proyek menjelaskan hasil tersebut.
- Retry hanya berlaku pada ID highlight hasil analisis terkait yang belum diedit. Penyimpanan memakai pemeriksaan revisi; hasil pilihan yang sudah diperoleh disimpan dalam payload job.
- File asli utuh untuk ekspor; proxy mute 30 fps dan thumbnail untuk editing. Hapus koleksi mengarsipkan aset agar draft, undo, job lama, dan ekspor proyek tetap dapat mengaksesnya.
- Default batas unggah 200 MB dan 30 menit. Opsional backend `LIBRARY_MAX_MB` dan `LIBRARY_MAX_DURATION` (detik) mengubah batas. Tidak perlu menambah konfigurasi agar fitur bekerja.
- Default transisi pudar hitam 9 frame, terpusat pada batas. Crossfade memakai frame penyangga yang tersedia; jika tidak cukup, pudar hitam dipakai dan dock menampilkan pemberitahuan. Transisi dipersingkat sesuai ruang yang tersedia.
- Fade audio dan bobot transisi dihitung pada 30 fps. Audio footage tidak pernah masuk ke preview maupun mix ekspor.

## Menjalankan dan memeriksa

Dari folder proyek Ubuntu: `npm run dev`. Launcher menerapkan migrasi hingga 0006 dan menjalankan API, worker, Redis, serta frontend. Jika aplikasi sudah berjalan sebelum pembaruan, hentikan launcher lama sebelum menjalankan ulang.

`npm run build`, `npm run types`, `node scripts/test-editor-model.cjs`, dan `.venv/bin/python -m pytest backend/tests -q` memeriksa tipe, operasi timeline, batas sumber, pemilihan otomatis, renderer lima rasio, audio, transisi, dan kompatibilitas proyek lama.

## Verifikasi implementasi

- Build TypeScript/Vite dan regenerasi OpenAPI lulus.
- 83 pengujian backend lulus; pengujian model timeline mencakup kelanjutan fade setelah split dan perpindahan sisipan lintas potongan.
- Gemini nyata diuji dengan metadata/transkrip fixture: topik relevan menghasilkan satu sisipan, topik tidak relevan tetap podcast. Retry menjaga revisi pengguna.
- Browser Edge desktop dan viewport 390 px: upload, penandaan adegan, source picker, playback, replace, drag, split, duplikasi, undo, autosave/reload, dan konflik revisi diperiksa. Tidak ada error JavaScript pada alur uji.
- Ekspor nyata 1080×1920: 180 frame, video 6,000 detik dan audio 6,000 detik. Selisih piksel rata-rata frame uji preview/MP4 2,12 dari skala 255.
- Pengarsipan tetap mengizinkan akses media aset yang digunakan. Seluruh fixture QA dibersihkan; tiga highlight asli tidak berubah.

Pengelolaan hashtag many-to-many dijelaskan di [HASHTAGS.md](HASHTAGS.md).
