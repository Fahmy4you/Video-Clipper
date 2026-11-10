# Video Clipping

**Dari video YouTube menjadi highlight yang bisa ditinjau, diedit, dan diekspor.**

Studio lokal dengan transkripsi Whisper, analisis highlight melalui 9Router, koleksi video sisipan, dan editor timeline. Tinjau hasil AI terlebih dahulu, siapkan gaya video, lalu ekspor MP4 sesuai kebutuhan.

**React · TypeScript · FastAPI · Celery · Redis · PostgreSQL · FFmpeg**

[Mulai cepat](#mulai-cepat) · [Alur penggunaan](#alur-penggunaan) · [Konfigurasi](#konfigurasi) · [Dokumentasi](#dokumentasi) · [Pengembangan](#pengembangan)

---

## Fitur utama

| Area                    | Yang tersedia                                                                                            |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Transkripsi & highlight | Whisper lokal, pemilihan combo 9Router, usulan highlight, dan peninjauan transkrip.                      |
| Revisi melalui audio    | Pemutar ringkas, waveform dalam modal, dan pilihan rentang tanpa mengikuti scroll playback.              |
| Persiapan video         | Mode Podcast/Mix, rasio video, tujuh template subtitle, preview transisi, dan preferensi gaya workspace. |
| Koleksi sisipan         | Metadata adegan, hashtag, instansi/Global, serta pencarian dan filter saat memilih video di studio.      |
| Studio                  | Timeline, trim/split, subtitle, teks, audio, filter, transisi, undo/redo, dan scroll mengikuti playback. |
| Ekspor                  | MP4 360p, 720p, atau 1080p; unduhan browser atau penyimpanan ke folder lokal.                            |

> **Pembagian proses:** Whisper mentranskripsikan audio secara lokal. Teks transkrip dikirim melalui 9Router untuk analisis highlight. Combo, akun penyedia, dan fallback dikelola pada dashboard 9Router; aplikasi tidak memerlukan `GEMINI_API_KEY`.

## Mulai cepat

### 1. Siapkan lingkungan

Alur pengembangan saat ini menggunakan **Ubuntu melalui WSL2**, dengan **PostgreSQL 17 di Windows**.

| Kebutuhan          | Keterangan                                                                |
| ------------------ | ------------------------------------------------------------------------- |
| Node.js 22         | Frontend dan perintah npm; contoh di bawah memakai nvm.                   |
| Python 3.12 + venv | Backend dan worker dalam lingkungan `.venv`.                              |
| FFmpeg             | Tersedia di Ubuntu, dengan dukungan libass dan libx264.                   |
| Redis              | Executable `redis-server` tersedia; launcher menjalankan instance proyek. |
| PostgreSQL 17      | Database dapat dijangkau dari backend WSL.                                |
| 9Router            | Layanan aktif, API key terpasang, dan combo sudah disiapkan.              |

Untuk koneksi database Windows–WSL, lihat [panduan setup](docs/SETUP.md). Alamat IP dan catatan mesin di dokumen tersebut adalah contoh lingkungan, bukan nilai yang harus disalin.

### 2. Pasang dependensi

Jalankan dari **root repository** di terminal Ubuntu:

```bash
source ~/.nvm/nvm.sh
nvm use 22
bash scripts/setup.sh
```

Setup memasang dependensi backend/frontend dan membuat `.env` dari [`.env.example`](.env.example) bila belum ada. File `.env` yang sudah ada dipertahankan.

### 3. Isi konfigurasi

Edit `.env` pada root repository. Isi tiga nilai berikut sesuai lingkunganmu:

- `DATABASE_URL` — koneksi PostgreSQL.
- `9router_base_url` — alamat API 9Router yang dapat dijangkau backend, diakhiri `/v1`.
- `9router_key` — API key dari dashboard 9Router.

Nilai default lainnya beserta komentar bahasa Indonesia tersedia dalam [`.env.example`](.env.example). Simpan kredensial asli hanya di `.env`, yang sudah diabaikan Git.

### 4. Jalankan aplikasi

```bash
npm run dev
```

| Layanan         | Alamat / port                                     |
| --------------- | ------------------------------------------------- |
| Aplikasi        | [localhost:5173](http://localhost:5173)           |
| Dokumentasi API | [localhost:8000/docs](http://localhost:8000/docs) |
| Redis proyek    | `127.0.0.1:6381`                                  |

Launcher menjalankan Redis, API, dispatcher, worker, dan frontend, serta mencoba migrasi database bila koneksi dikonfigurasi. Buka **Pengaturan** untuk memeriksa kesiapan layanan dan koneksi 9Router.

**Hentikan dengan `Ctrl+C`** pada terminal launcher. Gunakan satu launcher agar port tidak bertabrakan.

## Alur penggunaan

1. **Buat proyek** — masukkan URL YouTube, pilih combo 9Router, lalu minta highlight.
2. **Tinjau hasil** — baca ringkasan dan transkrip di Detail highlight; dengarkan audio sumber untuk memeriksa potongan.
3. **Revisi bila perlu** — buka **Revisi bagian melalui audio**, atur area dengar, pilih highlight, lalu simpan. Judul dan ringkasan diubah melalui **Ubah informasi**.
4. **Siapkan video** — pilih Podcast/Mix, rasio, subtitle, dan transisi sisipan. **Simpan pengaturan** menyimpan draft; **Proses video** memasukkan pekerjaan ke antrean.
5. **Edit di studio** — rapikan potongan, ganti sisipan, sesuaikan subtitle, dan periksa preview.
6. **Ekspor** — pilih resolusi MP4. Tujuan hasil mengikuti mode ekspor yang terlihat di **Pengaturan**.

### Batas yang perlu diketahui

| Pengaturan         | Aturan                                                                                                                                           |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sumber proyek      | Minimum bawaan 10 detik; maksimum 5 jam.                                                                                                         |
| Satu highlight     | 10 detik–20 menit. Usulan otomatis tanpa rentang khusus menargetkan 30–90 detik, menyesuaikan sumber pendek.                                     |
| Area dengar revisi | Awalnya sekitar 10 menit di sekitar highlight; menyesuaikan sumber dan pilihan, maksimal 20 menit. Area dengar terpisah dari pilihan highlight.  |
| Mix otomatis       | Sisipan 3–5 detik; anggaran maksimal 30% setiap blok menit, termasuk sisa menit; maksimal lima sisipan per menit sesuai kapasitas dan relevansi. |

Preferensi gaya terakhir diperbarui setelah **Proses video** individual diterima. Menyimpan draft, retry, proses batch, dan perubahan studio tidak menimpa preferensi tersebut.

## Konfigurasi

Semua key yang didukung beserta default dan penjelasannya tercantum dalam [`.env.example`](.env.example). Gaya subtitle dan pengaturan highlight dikelola melalui aplikasi.

| Key                           | Fungsi                                                           | Bawaan                     |
| ----------------------------- | ---------------------------------------------------------------- | -------------------------- |
| `DATABASE_URL`                | Koneksi database PostgreSQL                                      | Wajib diisi                |
| `REDIS_URL`                   | Koneksi antrean                                                  | `redis://127.0.0.1:6381/0` |
| `9router_base_url`            | Endpoint 9Router, diakhiri `/v1`                                 | Wajib diisi                |
| `9router_key`                 | Autentikasi 9Router                                              | Wajib diisi                |
| `WHISPER_PROFILE`             | `standard` = small; `light` = base                               | `standard`                 |
| `WHISPER_MODEL`               | Kompatibilitas lama; dipakai hanya jika profil tidak diisi       | `small`                    |
| `WHISPER_THREADS`             | Jumlah thread CPU Whisper                                        | `2`                        |
| `SOURCE_MIN_DURATION_SECONDS` | Minimum durasi sumber, dalam detik; batas bawah efektif 10       | `10`                       |
| `LIBRARY_MAX_MB`              | Maksimum ukuran file koleksi                                     | `200`                      |
| `LIBRARY_MAX_DURATION`        | Maksimum durasi video koleksi, dalam detik                       | `1800`                     |
| `EXPORT_MODE`                 | `global` = unduh browser; `local` = salin ke folder              | `global`                   |
| `EXPORT_LOCAL_DIR`            | Folder absolut yang sudah ada dan dapat ditulis untuk mode lokal | Kosong                     |

**Setelah mengubah `.env`, restart backend dan worker.** Pengecualian: alamat dan key 9Router dibaca pada permintaan berikutnya tanpa restart; permintaan yang sedang berjalan tetap memakai konfigurasi sebelumnya.

### Whisper dan penyimpanan ekspor

- **Standar (`small`)** memakai model lebih besar; **Ringan (`base`)** mengurangi kebutuhan sumber daya. Mengganti profil tidak menulis ulang transkrip tersimpan dan tidak menghapus model yang sudah diunduh.
- **Global** berarti hasil diunduh melalui browser, bukan diunggah ke hosting.
- **Lokal** berarti hasil disalin ke filesystem komputer backend. Backend WSL mendukung path Windows; folder Windows pengunjung tidak otomatis tersedia bagi backend di mesin lain.
- Indikator **Global/Lokal**, kesiapan, dan folder tujuan tersedia di **Pengaturan → Penyimpanan hasil ekspor**.

## Dokumentasi

### Penggunaan sehari-hari

| Panduan                                                                                     | Isi                                                                       |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| [Proyek transkripsi dan video](docs/TRANSCRIPTION_PROJECTS.md)                              | Peninjauan highlight, revisi audio, persiapan video, dan preferensi gaya. |
| [Studio visual](docs/VISUAL_EDITOR.md)                                                      | Timeline, elemen, dan struktur editor.                                    |
| [Subtitle](docs/SUBTITLES.md)                                                               | Akurasi transkrip dan tinjauan koreksi.                                   |
| [Koleksi video](docs/VIDEO_COLLECTION.md) · [Adegan](docs/VIDEO_SCENES.md)                  | Aset sisipan dan metadata adegan.                                         |
| [Hashtag](docs/HASHTAGS.md) · [Instansi](docs/INSTANSI.md) · [Mix](docs/MIX.md)             | Pengelompokan koleksi dan penggunaan sisipan.                             |
| [Transisi](docs/TRANSITION_EFFECTS.md) · [Filter](docs/FILTERS.md) · [Audio](docs/AUDIO.md) | Efek visual dan pengaturan audio studio.                                  |
| [Ekspor dan potongan](docs/EXPORTS_AND_CUTS.md)                                             | Resolusi, tujuan MP4, dan transisi antar-potongan.                        |

### Operasional dan pengembangan

| Panduan                                                                     | Isi                                                              |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| [Setup lokal](docs/SETUP.md)                                                | Database, WSL, dan dependensi.                                   |
| [Antrean dan 9Router](docs/QUEUE_AND_ROUTER.md)                             | Pemrosesan, penggunaan ulang sumber, dan pemulihan pekerjaan.    |
| [Katalog combo](docs/MODEL_CATALOG.md)                                      | Metadata combo, cache, dan pemeriksaan koneksi tanpa prompt.     |
| [Pemulihan video panjang](docs/LONG_VIDEO_RECOVERY.md)                      | Checkpoint, penggunaan RAM, worker, dan diagnosis gangguan.      |
| [Rancangan proyek](docs/PROJECT_PLAN.md) · [Riwayat status](docs/STATUS.md) | Konteks rancangan dan catatan implementasi/pengujian bertanggal. |

Catatan status dan laporan koleksi bertanggal merupakan riwayat. Penyebutan Gemini atau konfigurasi mesin lama dalam arsip tidak menggantikan alur 9Router dan konfigurasi aktif di atas.

## Pengembangan

### Struktur repository

```text
apps/web/       Antarmuka React dan studio
backend/        API, worker, renderer, migrasi, dan tes
scripts/        Launcher, setup, pemeriksaan, dan utilitas
docs/          Panduan fitur dan catatan teknis
storage/        Media, cache, model, log, dan hasil render (diabaikan Git)
.env.example    Contoh konfigurasi tanpa kredensial asli
```

### Perintah yang tersedia

Jalankan dari root repository. Untuk alat format pengembangan, pasang dependensi tambahan satu kali:

```bash
npm install
.venv/bin/python -m pip install -r backend/requirements-dev.txt
```

| Perintah               | Fungsi                                                                 |
| ---------------------- | ---------------------------------------------------------------------- |
| `npm run dev`          | Menjalankan layanan lokal.                                             |
| `npm run build`        | Memeriksa TypeScript dan membangun frontend.                           |
| `npm test`             | Menjalankan tes backend, termasuk validasi timeline dan render FFmpeg. |
| `npm run types`        | Membuat ulang tipe OpenAPI; API pada port 8000 harus aktif.            |
| `npm run format:check` | Memeriksa format frontend dan Python.                                  |
| `npm run format`       | Memformat kode dengan Prettier dan Ruff.                               |

<details>
<summary><strong>Browser smoke test</strong></summary>

`scripts/ui-smoke.cjs` memakai Playwright dan Edge headless. Jalankan ketika aplikasi aktif, menggunakan lingkungan Node yang menyediakan Playwright. Jika modul berada di luar repository, arahkan `PLAYWRIGHT_MODULE` ke modul tersebut.

```bash
node scripts/ui-smoke.cjs
```

Screenshot dan laporan disimpan di `storage/qa/`. Data editor memakai fixture browser terisolasi; tes ini tidak membuktikan integrasi YouTube, 9Router, atau database nyata.

</details>

## Data dan pemecahan masalah

Metadata dan edit plan berada di PostgreSQL; media, model, cache, serta hasil render berada di `storage/`. **Cadangkan database dan storage bersama-sama.** `.env`, media, dan kredensial tidak masuk Git.

| Gejala                                      | Yang diperiksa                                                                                                                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Aplikasi gagal dimulai karena port terpakai | Hentikan launcher sebelumnya; periksa port 5173, 8000, dan 6381.                                                                            |
| Database/9Router tidak terhubung dari WSL   | Periksa alamat host Windows yang aktif, konfigurasi `.env`, dan akses jaringan. Lihat panduan setup/9Router.                                |
| Persiapan Whisper pertama terasa lama       | Model perlu diunduh sekali ke `storage/models/`; pemakaian berikutnya menggunakan cache.                                                    |
| Worker berhenti saat video panjang          | Baca `storage/logs/worker.log` dan panduan pemulihan. Hindari build atau tes encoding berat bersamaan dengan transkripsi pada RAM terbatas. |
| Ekspor lokal belum siap                     | Periksa folder absolut, keberadaan folder, izin tulis, lalu restart backend/worker setelah mengubah `.env`.                                 |

Log layanan tersedia di `storage/logs/`: `api.log`, `worker.log`, `dispatcher.log`, `web.log`, dan `redis.log`.
