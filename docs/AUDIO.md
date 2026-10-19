# Audio studio — revisi 19 Oktober 2026

Panel kiri hanya untuk menambahkan teks, gambar, dan audio. Klik **Tambah audio** untuk membuka modal dengan empat sumber: unggah audio, ekstrak video lokal, YouTube, dan TikTok. Setelah proses selesai, audio otomatis masuk ke posisi playhead pada highlight aktif. Tidak ada daftar pustaka audio pada dock. Status impor disimpan per highlight agar reload tidak menggandakan hasil.

Pilih blok **Audio tambahan** di timeline untuk mengatur volume, waktu, dan sumber melalui dock kanan. Pilih video atau waveform **Audio sumber** untuk mengatur volume video asli di dock kanan. Split, trim, undo/redo, autosave, preview, dan ekspor tetap didukung.

Input dan textarea tetap dapat diseleksi, tetapi outline/box-shadow saat fokus dihilangkan. Border tetap berubah warna untuk membantu navigasi keyboard. Teks biasa tidak dapat diseleksi.

## Koneksi database

Saat insiden 503, proses API masih hidup, PostgreSQL Windows berjalan, dan koneksi baru berhasil melakukan query. Permintaan pada proses API lama tertahan. Backend sekarang membuka koneksi per sesi (NullPool), memakai batas waktu koneksi/query/lock serta TCP keepalive, dan polling editor tidak menumpuk permintaan saat permintaan sebelumnya belum selesai. Draft lokal tetap dipertahankan. Settings membedakan layanan belum diperiksa dari koneksi database terganggu, sehingga kegagalan health tidak ditampilkan seolah seluruh konfigurasi hilang.

## TikTok

Error `Unexpected response from webpage request` berhasil diatasi pada tautan uji menggunakan dukungan curl-cffi/browser impersonation resmi yt-dlp. Downloader memilih video dengan audio, mengecualikan format musik-only, format download, dan format bertanda watermarked. FFmpeg mengekstrak stream audio dari video yang diunduh. Tidak memakai katalog musik TikTok dan tidak memotong beberapa detik terakhir secara sembarang. Pemilihan playback video menghindari outro versi download TikTok; outro yang sudah menyatu dalam konten kreator tidak dideteksi otomatis.

Batas tetap 200 MB dan 30 menit. URL privat atau pembatasan platform lain dapat gagal; kegagalan impor ditampilkan sebagai error job tanpa menghentikan API.

## Pemeriksaan

- 69 tes backend lulus, termasuk pemilihan format TikTok yang menolak musik-only dan download.
- Build frontend dan tes model timeline lulus.
- Browser desktop/mobile: modal, fokus input, kontrol volume kanan, upload otomatis sekali, autosave/reload, tanpa error JavaScript.
- Dua putaran masing-masing 32 permintaan database bersamaan berhasil.
- Tautan TikTok @wan_284k/video/7674155560157367559 berhasil diunduh, diekstrak (19,2215 detik), otomatis masuk ke timeline, dan tersimpan kembali setelah volume diubah.
- Audio hasil uji berada pada bukti pengujian, tanpa mengubah edit highlight pengguna.

## Revisi closing dan timeline

- Modal TikTok menampilkan Buang closing akhir (detik), awal 2 detik, rentang 0–10. Nilai 0 mengambil seluruh audio. Ini pemotongan eksplisit berdasarkan durasi, bukan klaim pendeteksian logo otomatis. Video @wan_284k/7674155560157367559 memiliki transisi penutup sekitar 17,4 detik; potongan dua detik menghasilkan audio 17,216 detik. Aset lama tidak dimodifikasi diam-diam: impor ulang dengan pengaturan ini, atau trim ujung audio lama.
- Nama highlight hanya diedit di halaman daftar highlight proyek. Dock studio hanya menampilkan pengaturan elemen aktif.
- Duplikat: ikon salin di toolbar / Ctrl+D. Video disalin sesudah potongan asli beserta subtitle, gambar, teks, dan audionya dengan ID baru. Teks/gambar disalin pada waktu yang sama di lapisan lebih atas. Audio/subtitle ditempatkan sesudah elemen asli bila masih muat pada potongan; jika tidak, salinan berada pada waktu yang sama dan dapat digeser. Semua salinan dapat diubah secara independen, di-undo, dan disimpan.
- Klik elemen menjaga playhead jika masih di dalam rentangnya. Sebelum rentang menuju awal; setelah rentang menuju frame terakhir yang masih terlihat (akhir minus satu frame pada 30 fps). Drag tidak lagi diikuti lompatan playhead akibat event klik.
- Verifikasi: 70 tes backend, tes model duplikasi/batas seleksi, dan browser nyata untuk sebelum/di dalam/sesudah elemen, penghapusan input judul, duplikat, undo/redo, autosave/reload. Impor TikTok aktual dipotong sebelum normalisasi/waveform.
