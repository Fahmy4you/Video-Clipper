# Instansi dan sumber Mix

Video koleksi memiliki lingkup `global` atau `instansi`. Video khusus dapat terkait dengan satu atau beberapa instansi melalui pivot `instasi_to_video_clips` (`video_clip_id`, `instansi_id`). Global tidak memiliki relasi instansi. Pasangan ID pada pivot unik; menghapus video membersihkan relasinya tanpa menghapus instansi. Tabel `instansi` dapat digunakan fitur lain. Nama unik diperiksa tanpa membedakan huruf besar/kecil. `project_instansi` menyimpan sumber kolaborasi proyek; `projects.include_global` menyimpan izin Global.

## Penggunaan

1. Kelola daftar di `/instansi`. Tambah dan rename melalui dialog. Hapus hanya tersedia secara operasional untuk instansi tanpa relasi video maupun proyek; server menolak penghapusan yang masih dipakai.
2. Saat unggah koleksi, pilih lingkup secara eksplisit. Untuk lingkup instansi, pilih minimal satu instansi pada multiselect sebelum mengunggah. Video kolaborasi dapat memilih beberapa instansi.
3. Detail koleksi menyimpan lingkup, pemilik, informasi dan hashtag melalui Simpan perubahan dengan pemeriksaan revisi.
4. Di dashboard pilih Mix, lalu nol/satu/beberapa instansi. Tanpa pilihan berarti Global saja. Memilih instansi pertama mengaktifkan Global secara default; checkbox dapat dimatikan. Melepas seluruh instansi mengembalikan Global saja.
5. Filter hashtag opsional mempersempit kandidat dengan AND. Pilihan instansi memakai OR. Hashtag yang menjadi tidak tersedia tetap terlihat dan dapat dilepas.

| Instansi | Sertakan Global | Sumber otomatis |
|---|---|---|
| Kosong | Dinormalisasi aktif | Global saja |
| Cryptowave | Tidak | Cryptowave |
| Cryptowave | Ya | Cryptowave + Global |
| Cryptowave, Akademi Crypto | Tidak | Kedua instansi |
| Cryptowave, Akademi Crypto | Ya | Kedua instansi + Global |

Video harus siap, tidak diarsipkan, lolos batas sumber, dan memiliki seluruh hashtag yang dipilih. Untuk video khusus, cukup salah satu instansi video beririsan dengan instansi sumber proyek. Video Cryptowave + Stockwise bisa dipakai proyek Cryptowave saja maupun Stockwise saja; memilih keduanya tetap menghasilkan satu kandidat untuk video tersebut. Kandidat kosong tidak memanggil Gemini untuk pemilihan B-roll dan tetap menghasilkan podcast dengan penjelasan bahwa footage tidak tersedia. Tidak ada fallback di luar sumber.

Pemilihan manual di studio tetap menampilkan seluruh koleksi. Label pemilik/Global ditampilkan dan dialog menjelaskan perbedaan dengan pemilihan otomatis. Save, render dan ekspor tidak membatasi instansi pilihan manual.

## API dan konsistensi job

- `GET/POST /api/instansi`, `PATCH/DELETE /api/instansi/{id}`. Input `{name}`; output ID, nama, jumlah video dan jumlah proyek. Nama bentrok dan instansi yang masih dipakai menghasilkan 409.
- Input/output proyek: `instansi_ids` dan `include_global`. ID wajib valid; relasi memakai pivot. Daftar kosong dinormalisasi menjadi Global saja.
- Unggah multipart koleksi: `scope` wajib, `instansi_ids` dikirim sebagai field multipart berulang; minimal satu untuk `instansi`, kosong untuk `global`. Duplikat ID dinormalisasi sebelum menyimpan pivot.
- Metadata koleksi: `scope`, `instansi_ids`, dan `instansi_names` disertakan pada respons. PATCH mendukung lingkup dan array ID; klien lama yang tidak mengirim lingkup mempertahankan kepemilikan yang sudah tersimpan.
- Snapshot job menyimpan `source_policy_version=1`, pilihan sumber, hashtag dan kandidat dengan metadata kepemilikan. Worker memfilter kandidat kembali dan menolak cache yang memakai ID di luar kandidat. Retry mempertahankan snapshot, termasuk ketika metadata kepemilikan terkini kemudian berubah. Video yang dihapus tetap disaring dari snapshot.
- Snapshot retry lama yang belum memiliki kebijakan sumber diadaptasi menggunakan pilihan proyek dan metadata kepemilikan terkini sekali, sebelum diantrekan sebagai snapshot baru. Edit highlight pengguna tetap dipertahankan.
- Tipe `api-schema.d.ts` diregenerasikan dari OpenAPI termasuk Instansi dan respons koleksi.

## Migrasi 0007

Migrasi membuat Cryptowave dan Akademi Crypto, kemudian mengelompokkan seluruh koleksi lama sesuai instruksi pengguna. Video `80ec4727-788a-54c5-9f33-ed897f837066` masuk Akademi Crypto; seluruh lainnya Cryptowave. Hasil audit: 55 Cryptowave, 1 Akademi Crypto, 0 Global. Tidak mengubah ID, file, judul, penjelasan, scenes, hashtag atau revisi. Hash SHA-256 semua sumber dibandingkan sebelum/sesudah dan cocok.

Proyek Mix lama, bila ada, diberi kedua instansi tanpa Global. Tidak menjalankan analisis ulang. Status revisi Alembic mencegah klasifikasi ulang pada `upgrade head` berikutnya.

## Migrasi 0008 dan kolaborasi video

Pivot `instasi_to_video_clips` menggantikan kolom tunggal `video_clip.instansi_id`. Semua relasi lama disalin satu kali sebelum kolom dihapus. Audit setelah migrasi memastikan tetap 56 video dan 56 relasi: 55 Cryptowave, 1 Akademi Crypto, tanpa Global dan tanpa kolaborasi buatan. Hash file, informasi, scenes, hashtag, revisi, dan edit highlight tidak berubah.

Snapshot job lama yang menyimpan `instansi_id` tunggal tetap dibaca sebagai satu keanggotaan; snapshot baru memakai `instansi_ids`. Riwayat retry tetap mengikuti kandidat yang dibekukan ketika job dibuat.

Detail dan unggah koleksi memakai multiselect instansi, menampilkan seluruh pilihan, dan memblokir penyimpanan lingkup khusus tanpa instansi. Daftar koleksi dan pemilih manual studio menampilkan seluruh nama instansi terkait. Mengganti lingkup ke Global melepas seluruh relasi; menghapus satu pilihan instansi hanya melepas relasi tersebut.

Downgrade 0008 ditolak apabila sudah ada video dengan beberapa instansi agar tidak membuang relasi secara diam-diam.

## Verifikasi

- Suite backend terbaru: 142 tes lulus, termasuk 19 kasus instansi/migrasi, upload beberapa instansi, duplikat relasi, lepas relasi, Global, snapshot lama, dan rollback migrasi yang mencegah kehilangan data.
- Pengujian mencakup CRUD, duplikat nama, relasi yang masih dipakai, validasi unggah, kepemilikan, konflik revisi, semua kombinasi sumber, AND hashtag, kandidat kosong, cache di luar sumber dan pembekuan snapshot retry.
- Browser menggunakan respons mutasi fixture terisolasi: formulir/payload kolaborasi, Global default/reset, hashtag yang tidak tersedia, detail/draft/tab/reload/konflik, seluruh hashtag dan sorting, upload eksplisit, CRUD Instansi, pagination/pencarian, keyboard/Escape, playback nyata, seluruh koleksi manual studio, serta scrollbar.
- Visual diperiksa pada 1366x768 dan 390x844, tema terang dan gelap. Tidak ada overflow horizontal halaman atau page error pada skenario uji.
- Pengujian tidak menjalankan generate Gemini berbayar; pemilihan AI menggunakan fixture dan validator server. Render FFmpeg tercakup dalam suite backend.
