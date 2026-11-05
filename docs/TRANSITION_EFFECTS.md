# Kilatan dan Camera shutter

Pilih sisipan pada timeline, kemudian atur **Transisi masuk** atau **Transisi keluar** pada dock kanan. Animasi dan suara dapat dipilih terpisah. Default tetap Pudar hitam, 0,30 detik, tanpa suara. Memilih Kilatan mengatur durasi awal 0,40 detik; gradasi krem-peach dua dimensi menyapu video secara lembut dan memuncak pada cut (opacity maksimum 60%). Subtitle/overlay tetap di atas cahaya. Durasi efektif dipendekkan jika berbenturan dengan batas terdekat.

Camera shutter diekstrak dari berkas yang disediakan pengguna menjadi WAV PCM stereo 48 kHz: 12.261 sampel per kanal (0,2554375 detik). Berkas sumber di Downloads tetap utuh. Panjang suara tidak mengikuti slider animasi. Titik tengah berkas tepat pada cut, dengan toleransi pembulatan paling banyak setengah sampel. Misalnya pada detik 10, awal ekspor berada pada sampel 473.870 dan panjangnya 12.261 sampel.

Suara dipotong pada batas awal/akhir highlight tanpa menggeser pusat atau menambah durasi video. Pada batas bersama, transisi keluar yang memiliki suara diprioritaskan. Suara tidak berbunyi saat scrub dalam keadaan pause; playback dari tengahnya melanjutkan bagian tersisa. Pause/seek/buffering/pergantian kualitas menghentikan atau menjadwalkan ulang audio.

Aset bawaan: `backend/app/assets/effects/camera_shutter.wav`. Katalog `GET /api/transition-effects` menyediakan ID, nama, URL, jumlah sampel, sample rate dan durasi. Endpoint audio hanya menerima ID bawaan. EditPlan v2 menambahkan jenis `flash`, `sound` (`none` atau `camera_shutter`) dan `sound_volume` (0–1). Plan lama default tanpa suara, tanpa migrasi database.

Pengujian: `node scripts/test-transition-effects.cjs` membandingkan raster dan waktu Python/TypeScript serta operasi split/duplikat. `pytest backend/tests/test_transition_effects.py` memeriksa pusat sampel, batas, validasi, lapisan visual, lima rasio dan hasil encoding nyata.
