> Alur navigasi dan pengelolaan highlight telah direvisi. Ikuti [PROJECT_FLOW.md](PROJECT_FLOW.md).

# Editor visual per highlight — EditPlan v2

Diperbarui 19 Oktober 2026. Implementasi mengikuti upgrade editor visual yang disetujui.

## Mulai menggunakan

Jalankan Start-VideoClipping.ps1 dari folder proyek Windows, atau `bash scripts/launch.sh`
di `/home/fahmy_root/projects/video_clipping`, lalu buka http://localhost:5173.
PostgreSQL tetap memakai instalasi Windows. DATABASE_URL dan GEMINI_API_KEY tetap di .env Ubuntu;
model Gemini dipilih dari antarmuka, bukan .env. Poppins disajikan lokal.

1. Isi URL YouTube, pilih model, jumlah highlight 1–5 (default 3), rasio dan prompt opsional.
2. Rasio terkunci setelah proyek dibuat. Semua highlight dan ekspor mengikuti rasio proyek.
3. Pilih satu highlight di kiri. Klik ruler timeline untuk menuju momen tertentu.
4. Space untuk play/pause; panah kiri/kanan maju/mundur satu frame; S untuk split;
   Delete untuk hapus pilihan; Ctrl/Cmd+Z dan Shift+Ctrl/Cmd+Z untuk undo/redo.
   Shortcut tidak mengganggu input teks. Hapus video menutup celah; audio ikut video.
5. Tarik tepi potongan untuk trim, termasuk memperpanjang ke sumber di luar pilihan AI.
   Tarik badan potongan ke potongan lain untuk mengubah urutan.
6. Klik subtitle untuk memperbaiki kata, mengubah waktu dan gaya. Geser di kanvas untuk
   memindahkan seluruh subtitle; pilih “Blok ini saja” untuk override dan reset bila diperlukan.
7. Tambah teks atau unggah gambar PNG/JPEG/WebP statis maksimal 20 MB.
   Geser/resize elemen di kanvas; inspector menyediakan posisi, ukuran, rotasi, opacity dan lapisan.
8. Tunggu status Tersimpan sebelum menutup. Gagal menyimpan mempertahankan draft lokal.
   Konflik revisi meminta keputusan eksplisit; unduh draft sebelum memilih versi server.
9. Ekspor memakai video asli. Render final preview tersedia untuk memeriksa hasil encoding.

## Implementasi

- Formulir: rasio 9:16, 16:9, 1:1, 4:5, 4:3; jumlah 1–5; prompt maksimal 4.000 karakter.
  Prompt topik diprioritaskan dalam jumlah pilihan, timestamp menjadi petunjuk konteks.
  Highlight pemenuhan prompt diberi tanda dan laporan permintaan yang belum terpenuhi ditampilkan.
- Workspace: daftar highlight/media, kanvas langsung, inspector dan timeline lima track.
  Thumbnail, waveform, playhead, snapping, zoom, scroll, panel lipat dan panel bergantian di mobile.
- EditPlan v2: frame 30 fps, ID stabil, daftar segmen dengan pemetaan source_in/duration;
  subtitle dan overlay memakai waktu relatif segmen. Split/trim/reorder/delete membawa elemen terkait.
  Ekstensi trim mengambil transkrip tambahan sambil mempertahankan koreksi yang sudah tersimpan.
- Undo satu langkah per drag. Autosave setelah jeda satu detik di luar gesture.
  Revisi optimistis mencegah silent overwrite; localStorage menyimpan draft belum tersimpan.
- Preview video browser + Canvas mengikuti requestVideoFrameCallback, dengan fallback animation frame.
  Proxy H.264 beresolusi rendah, thumbnail dan waveform dibuat worker dan disimpan dalam cache.
- Ekspor FFmpeg memotong audio/video per segmen, menyambung sesuai urutan, menerapkan framing,
  lalu mengomposisikan subtitle/teks/gambar. Font yang sama dibundel untuk Canvas dan Pillow.
  PNG transparan, urutan lapisan dan perubahan warna kata didukung.
- Resolusi final: 1080×1920, 1920×1080, 1080×1080, 1080×1350, 1440×1080.
  Dimensi ditentukan backend dari rasio proyek, bukan payload klien.
- API: editor-media manifest/preparation, asset list/upload dan media milik proyek.
  Gambar dirujuk UUID milik proyek; path bebas tidak diterima. Tipe TypeScript berasal dari OpenAPI.
- Migrasi 0003 memberi default proyek lama, mengonversi plan berdasarkan versi dan menyimpan legacy_plan.
  Rentang, subtitle, styling dan layout lama dipertahankan; ekspor lama tetap tersedia.
  Analisis ulang tidak mengganti clip yang telah ada. Snapshot job mempertahankan input analisis.

## Verifikasi

- Suite backend: 51 kasus, termasuk pilihan jumlah/prompt, migrasi, validasi timeline dan renderer.
- Ekspor FFmpeg diuji untuk kelima rasio pada resolusi final, termasuk split 4:5 dengan panel 675 px.
- Audio uji 300/900 Hz dipotong dan direorder bersama video; durasi dan warna frame diperiksa.
- Tes model frontend: split, linked caption/overlay, ripple delete, reorder, trim tambahan,
  koreksi subtitle, pemisahan kata dan perubahan timing.
- Browser Edge nyata: playback, canvas drag, undo/redo, native reorder, PNG transparan,
  subtitle global/per-blok, autosave/reload, konflik revisi, kegagalan simpan dan keyboard.
- Lebar 1440/1024/768/390 diperiksa; tidak ada horizontal overflow atau error JavaScript pada alur uji.
- API nyata menolak perubahan rasio melalui endpoint penggantian model.
- Ekspor uji video sumber: enam detik, dua segmen yang diubah urutannya dan dihapus bagian tengah,
  teks serta PNG transparan. H.264 1080×1920 + AAC, decode penuh berhasil.
  Video 179 frame, audio 6 detik: selisih akhir satu frame dalam toleransi yang disepakati.
- Sampel frame live/export diperiksa untuk kesamaan posisi teks dan gambar.
- Highlight lama 40,233 detik berhasil diekspor ulang: 1.207 frame, audio 40,233 detik, decode penuh lulus.
- Mode Fit yang digeser ke tepi diuji agar posisi preview dan ekspor mengikuti aturan yang sama.
- Build produksi TypeScript/Vite dan pip check lulus.

Tes prompt upgrade memakai respons Gemini yang dimock; kemampuan semantik model tidak dijamin
oleh tes tersebut. Pipeline Gemini nyata sebelumnya sudah berhasil pada video contoh pengguna.
Subtitle tetap memerlukan pemeriksaan manusia untuk akurasi kata. Perbandingan preview/ekspor
dilakukan pada sampel frame, bukan pembuktian piksel identik untuk setiap kombinasi gaya.

## Batas versi ini

Belum ada overlay video, musik/voice-over tambahan, effects, transition library, keyframe,
atau timeline video panjang terpisah. Proxy pertama membutuhkan waktu persiapan;
ekspor memakai sumber asli dan satu worker untuk mengendalikan penggunaan CPU/RAM.
Model yang tercantum oleh penyedia bisa saja menolak generateContent untuk akun tertentu;
pesan error memberi opsi memilih model lain tanpa mengulang transkripsi.
