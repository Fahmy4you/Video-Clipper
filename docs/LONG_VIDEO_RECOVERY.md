# Transkripsi panjang dan API key JSON — 27 Oktober 2026

## Diagnosis terverifikasi

Video niXAuUhK-tw berdurasi 4691,321 detik (78 menit 11 detik). Sumber 1,34 GB sudah tersedia.
Kernel WSL menghentikan Python karena OOM pada 04:08:57 dan 05:30:26 WIB, dengan RSS sekitar 3 GB.
Ubuntu mendapat sekitar 3,5 GiB RAM dan swap 1 GiB; laptop memiliki RAM fisik sekitar 8 GB.
Kegagalan terjadi pada transkripsi, sebelum pemilihan highlight/Mix. Snapshot Mix berisi 113 kandidat.

Pengujian menemukan pula putusnya koneksi PostgreSQL sementara, serta tekanan RAM Windows ketika
build/tes berat berlangsung bersamaan. Pemeriksaan status sebelumnya membuka koneksi baru dan
memuat payload besar berulang kali. Kini status dibaca ringan, koneksi dibatasi dan digunakan ulang,
heartbeat tulis yang gagal dibedakan dari hilangnya koneksi pemilik advisory lock.

## Perubahan

- Sumber tetap 1080p. Whisper tetap base CPU INT8 dengan dua thread; batas thread BLAS mengikuti dua thread.
- Inti 120 detik + konteks dua detik per sisi, satu proses anak yang menggunakan ulang model.
- Kata ditempatkan menurut titik tengah terhadap batas inti, timestamp dikembalikan ke sumber.
- Checkpoint tiap bagian atomik; hash sumber + konfigurasi menentukan validitas. Hash sumber dicache
  berdasarkan ukuran/mtime dan dihitung streaming sambil melepaskan clean page cache milik sumber.
  Cache sumber juga dilepas setelah ekstraksi bagian agar WSL tidak menahan keseluruhan MP4 di RAM.
- Batas memori proses transkripsi min(2 GiB, 60% RAM Ubuntu); dua percobaan per bagian termasuk awal.
  Cancel/putus database yang ditangani tertib mengembalikan jatah percobaan bagian yang belum selesai.
  Retry manual membuka siklus percobaan baru, mempertahankan checkpoint yang valid.
- Worker berhenti tidak menjatuhkan API/UI. Supervisor restart maksimal tiga kali/10 menit (5,15,30 detik).
  Proses anak menerima sinyal ketika parent mati serta mewarisi file lock untuk mencegah overlap.
- Status pekerjaan meliputi telemetry tahap, waktu, byte/kecepatan unduh, bagian transkripsi, RAM,
  progres batch Mix dan estimasi setelah pengukuran cukup. Log tidak menyimpan key atau transkrip lengkap.
- Gangguan DB menunggu layanan dan mempertahankan checkpoint. Kehilangan lock menghentikan anak sebelum
  melepas slot. Operasi tulis yang diulang hanya assignment idempotent di transaksi dengan row lock.
- Key JSON berada di root, dimigrasikan sekali dari .env bila file belum ada; perubahan langsung berlaku.
  UI menyediakan tambah/edit/hapus/prioritas/uji. File rusak tidak memakai key lama secara diam-diam.

## Hasil pengujian

- Seluruh 184 tes backend lulus dalam 56,32 detik. Build TypeScript/Vite final dan tipe OpenAPI lulus.
- UI desktop 1366x768 dan mobile 390x844, tema terang/gelap, CRUD/prioritas/uji key,
  konfirmasi hapus, status proyek nyata, serta console browser diperiksa tanpa error JavaScript.
- Worker nyata dihentikan sengaja: API/UI tetap HTTP 200, worker pengganti muncul otomatis,
  dan lima checkpoint sebelumnya dipertahankan. Gangguan PostgreSQL yang ditemukan selama uji
  menjadi kasus regresi: menunggu layanan, tidak menghabiskan jatah kegagalan model.
- Dua proses OS/PostgreSQL: FIFO, tanpa eksekusi ganda, pemulihan pemilik yang dimatikan,
  checkpoint dipertahankan. Ekspor fixture 1080x1920 dan proxy koleksi nyata lulus.
- Video pengguna selesai: 40 bagian, 12156 kata, bahasa Indonesia.
  Timestamp dan kepemilikan batas inti valid; transkrip gabungan cocok dengan seluruh checkpoint.
  Sumber tetap 1920x1080, 1344547586 byte.
  Puncak RSS proses anak transkripsi pada eksekusi akhir 495.3 MiB;
  angka ini tidak mencakup API, worker pengawas, browser, atau cache sistem operasi.
- Tiga highlight + enam sisipan selesai menggunakan Cryptowave + Global, hashtag/prompt kosong.
  Seluruh sisipan berada di adegan dan sumber yang diizinkan. Tidak membuat proyek baru.
- Sampel ekspor 1440x1080 mengikuti rasio proyek 4:3,
  durasi 32.6 detik tepat sesuai timeline, H.264 + AAC, selisih durasi audio/video 0 detik.
  Korelasi suara podcast saat B-roll 0.99924, pergeseran terukur 0 ms.
  Tidak ada rentang hitam dengan ambang deteksi 0,12 detik; frame B-roll dan subtitle ditinjau.
- Playback MP4 ekspor dan playback studio dengan sumber/edit plan asli lulus. Pada tes studio,
  permintaan persiapan proxy dicegat di browser agar tidak menjalankan encoding ulang 78 menit;
  tidak ada perubahan edit yang dikirim ke backend. Pengujian proxy nyata memakai fixture terisolasi.
- Key asli diabaikan Git dan tidak terlacak; template tidak diabaikan. Vite mengembalikan 403
  untuk file key. Tidak ada key asli dalam respons konfigurasi maupun bundle frontend.
- Hanya satu key nyata tersedia. Kuota 429 dan gangguan 503 benar-benar terjadi saat Mix dan
  pulih tanpa mengulang transkripsi. Failover tiga key diuji dengan provider simulasi, bukan tiga akun nyata.

Pengujian video menggunakan sumber unduhan dan lima checkpoint yang sudah tersedia. Waktu selama
pengembangan juga mencakup jeda deploy, tes crash, dan pemeriksaan lain; jangan memakainya sebagai
benchmark proyek baru. Transkripsi CPU tetap memerlukan waktu sesuai durasi sumber.

Laporan privat (diabaikan Git) berada di storage/qa: worker-recovery-report.json,
queue-postgres-report.json, key-security-report.json, transcription-real-report.json,
long-video-live.json, real-highlight-export.json, export-black-frame-report.json.
Perubahan ini tidak mengubah alokasi RAM WSL. Key asli .env tidak dihapus otomatis; JSON menjadi
sumber aktif. Penanda migrasi nonrahasia mencegah key lama hidup kembali jika JSON dihapus.
