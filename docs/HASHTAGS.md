# Hashtag bersama dan relasi video

Buka /hashtags melalui ikon # pada sidebar untuk menambah, mencari, mengganti nama, atau menghapus hashtag. Nama unik disimpan tanpa awalan #, huruf kecil; spasi tidak diperbolehkan.

## Struktur PostgreSQL

- hashtags: id (UUID string, primary key), name_tag (unik).
- video_clip_hashtags: video_clip_id dan hashtag_id menjadi composite primary key. Kedua foreign key memakai ON DELETE CASCADE hanya pada baris pivot.
- video_clip tidak lagi menyimpan kolom array hashtags. Migrasi 0006 memindahkan seluruh label dan relasi lama sebelum membuang kolom tersebut.
- Tidak ada cascade dari hashtag ke video_clip. Menghapus satu-satunya hashtag video menghasilkan video tanpa hashtag, bukan menghapus video atau berkasnya.

Di Koleksi video, pilih Edit & tandai adegan. Tombol Tambah #nama menambahkan pilihan, tombol × melepas pilihan dari video aktif; Simpan informasi menyimpan relasi. Daftar global tetap tersedia untuk video lain. Mengganti nama hashtag berlaku pada semua video terhubung. Perubahan global menaikkan revisi video terkait, sehingga draft lama akan ditolak dengan konflik 409, bukan menimpa relasi diam-diam.

API /api/hashtags menyediakan GET, POST, PATCH /{id}, DELETE /{id}. Koleksi menerima hashtag_ids pada PATCH /api/video-clips/{id}; ID yang sudah dihapus ditolak. Response hashtags berupa daftar nama untuk tampilan dan kompatibilitas; daftar ini dihitung dari join, bukan kolom JSON video. Input nama lama masih diterima untuk label yang sudah terdaftar, tanpa membuat label baru secara diam-diam.

Filter Mix tetap opsional, memakai kecocokan minimal satu nama. mix_hashtags pada proyek dan metadata job adalah snapshot pengaturan analisis, bukan penyimpanan label milik video; retry mempertahankan kandidat historisnya. Label yang dihapus tidak lagi tersedia pada koleksi aktif. Tanpa kecocokan, tidak mengambil video di luar filter.

Verifikasi: 94 tes backend lulus, build dan regenerasi OpenAPI lulus. Pengujian browser mencakup tambah/ubah/hapus hashtag, pasang/lepas relasi, video dan scenes tetap utuh setelah penghapusan, serta layar kecil tanpa overflow horizontal. Migrasi menjaga 11 video, 37 label unik, dan 56 relasi awal.
