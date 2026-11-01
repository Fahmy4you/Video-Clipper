# Filter dan urutan daftar — 23 Oktober 2026

Semua halaman memiliki tombol Lucide **Filter & urutkan** untuk membuka/menutup dock. Perubahan langsung diterapkan, pengaturan aktif ditandai, dan Reset mengembalikan nilai awal. Menutup dock mempertahankan pilihan selama halaman tetap terbuka.

- Proyek: pencarian nama tanpa membedakan huruf besar/kecil; rentang tanggal dibuat dan terakhir diperbarui; urutan terbaru/terlama untuk kedua tanggal. Rentang memakai kalender lokal perangkat, termasuk kedua tanggal batas. Dua rentang yang diisi berlaku bersamaan.
- Koleksi: hashtag AND, instansi/Global OR, dan tanggal dibuat terbaru/terlama. Sumber kosong berarti seluruh koleksi. Filter dan sorting berjalan sebelum pagination; perubahan mengembalikan halaman ke 1.
- Hashtag: jumlah video terbanyak/tersedikit; default nama A–Z.
- Instansi: jumlah proyek atau video terbanyak/tersedikit; default nama A–Z.
- Nilai sort yang sama dipecahkan dengan nama lalu ID agar urutan stabil. Pilih semua proyek hanya memilih hasil filter yang boleh dihapus; pilihan tersembunyi tetap ditunjukkan oleh bulk toolbar yang sudah ada.

Migrasi `0009` menambahkan `projects.updated_at`. Proyek lama memakai `created_at` sebagai titik awal karena tidak ada riwayat waktu edit yang tersimpan. Perubahan proyek serta pembuatan, penyuntingan, atau penghapusan highlight memperbarui waktu dalam transaksi yang sama. Pembacaan/polling tidak mengubah tanggal. API dan tipe OpenAPI diperbarui; logic Mix/render tidak berubah.

Verifikasi: 149 pengujian backend lulus, termasuk migrasi dan pencatatan waktu serta rollback; build TypeScript/Vite lulus. Uji browser menggunakan fixture terisolasi untuk proyek/hashtag/instansi dan koleksi Global nyata dalam mode baca saja. Search, tanggal lokal inklusif, rentang terbalik, arah sort, hashtag AND, sumber OR, reset pagination, toggle/Escape, serta tema terang/gelap pada 390×844 lulus tanpa page error/overflow horizontal. Desktop 1366×768 dan mobile ditinjau visual. Tidak membuat atau menghapus data pengguna untuk pengujian.
