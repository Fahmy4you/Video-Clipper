# Transcription and video projects

A project owns a YouTube source reference, saved transcript version, proposal searches,
proposals and editable clips. Two routes provide separate views of that data.

- /transcriptions lists projects and opens raw proposals for review.
- /projects lists projects with video processing or editable clips.
- /transcriptions/:id and /projects/:id refer to the same parent project.
- Existing studio URLs remain /projects/:id/clips/:clipId.

Home accepts URL, combo, count (1–5, default 3) and optional prompt. A source match offers
existing projects or a separate project. Both can reuse valid cached source media.

Inside a project, Add proposal defaults to one result. It accepts a topic/time prompt,
combo, count and an optional avoidance filter (enabled initially). Avoidance includes
active proposal ranges and the podcast source ranges in saved clips. AI may adjust prompt
timestamps for conversational context. Users review the actual result before approval.

Each search is additive and idempotent. At most one proposal search per project is pending.
The full transcript is preserved when a proposal becomes a video. Successfully built
proposals move to review history. Failed/cancelled builds retain their proposal for retry.

API additions:

- GET /api/source-projects?url=... finds existing projects by canonical video URL.
- GET/POST /api/projects/:id/searches lists/submits searches.
- GET /api/projects?view=transcription|video selects a project view.
- POST /api/jobs/:id/router explicitly continues an interrupted job using ai_combo.

Project submission supports ai_combo. The historical gemini_model field remains readable
for old records. New requests and job snapshots use provider=9router and ai_combo.


## Permintaan highlight dan peninjauan

Home **Buat proyek** menerima 1–5 permintaan (default 3). Sebelum antrean dibuat,
backend memeriksa metadata YouTube: minimum 10 detik, maksimum 5 jam.
`SOURCE_MIN_DURATION_SECONDS` dapat mengubah minimum; kosong memakai 10.
Restart backend dan worker setelah mengubahnya.

**Tambah highlight** dalam proyek selalu meminta satu usulan melalui combo 9Router.
Tentukan waktu bersifat opsional. Fix time aktif mengunci kedua batas persis;
ketika mati, tiap batas boleh bergeser maksimal 60 detik dan hasil harus tetap
beririsan dengan rentang acuan. Prompt atau waktu eksplisit membolehkan bagian lama;
tanpa keduanya, bagian terpakai dihindari. Data waktu API memakai frame 30 fps.

Setiap permintaan memiliki kartu tetap, termasuk hasil belum terpenuhi atau gagal.
Analisis ulang memilih combo dan mengisi kartu yang sama. Penghapusan menyimpan
penanda agar checkpoint tidak menghidupkan kartu kembali. Gagal menyusun video
tidak menghapus hasil analisis.

Detail usulan tersedia di
`/transcriptions/:projectId/highlights/:proposalId`. Transkrip baca saja tersedia
langsung dengan pagination; revisi rentang memakai kolom Jam/Menit/Detik.
Siapkan video tetap memerlukan persetujuan. Studio dan ekspor memakai alur sebelumnya.

API baru: POST /api/sources/inspect, GET /api/projects/:id/highlight-requests,
POST /api/highlight-requests/:id/reanalyze dan DELETE /api/highlight-requests/:id.
Retry memerlukan request_id, revision dan ai_combo; hapus memerlukan query revision.
Pencarian baru memakai policy_version=2 dengan time_range opsional
(start_frame, end_frame, fix_time). Antrean lama tetap memakai snapshot versi lamanya.


## Batas highlight dan kepadatan Mix

Permintaan dan persetujuan baru memakai rentang 10 detik–20 menit (300–36.000
frame). Usulan otomatis tanpa rentang tetap 30–90 detik; sumber pendek 10–30
detik memakai sumber utuh. Batas sumber maksimum tetap lima jam. Potongan internal
studio tetap mengikuti aturan editing yang sudah ada.

Mix otomatis baru memakai sisipan 3–5 detik. Setiap blok menit, termasuk sisa
menit, memiliki anggaran 30% durasinya. Maksimal lima sisipan dihitung dari waktu
mulai; durasi lintas menit dibebankan pada kedua blok. Pengaturan opsional
`mix_max_per_minute` (null atau integer 1–5) dapat menurunkan batas, tanpa
mewajibkan pemenuhan jumlah. Jeda tiga detik dan pembukaan/penutup dua detik tetap
berlaku. Kandidat yang tidak muat dilepas, bukan dipotong otomatis.

Versi aturan disimpan server pada snapshot pekerjaan. Pekerjaan lama dan retry
snapshot lama dipertahankan; video lama tidak dihasilkan ulang. Draft batas
menyesuaikan penurunan kapasitas ketika durasi direvisi dan disimpan manual.

## Video style preparation

The preparation page is /transcriptions/:projectId/highlights/:proposalId/prepare.
Save settings stores a proposal draft. Process video saves first and snapshots the
approved style before enqueueing. GET /api/video-preferences returns workspace
style defaults. Only a new single approval with remember_style=true updates them;
batch processing, retries, draft saves, and studio edits do not.

Subtitle templates: sentence, word, background, reveal (down), reveal_up, karaoke (persistent), karaoke_active (current word only). Paired entrance/exit
motions: none, fade, zoom, zoom_fade, down, down_fade. New styles use subtitle_version=1;
unversioned plans retain the original presentation. Preferences include subtitle style
and incoming/outgoing insertion transitions, but exclude source selection and ratio.

Modern subtitle motion uses smooth acceleration, 96–100% zoom and 12% font-size travel. Existing version-1 styles adopt the smoother curves on playback and new exports; existing MP4s are retained.

### Pemilih gaya pada Siapkan video

Tindakan reset, simpan, dan proses berada pada header sebagai tombol ikon. Panel subtitle dan transisi memakai accordion beranimasi dengan konten tertutup nonaktif. Kartu menggunakan CSS Grid rata kiri, tiga/dua/satu kolom sesuai lebar komponen. Transisi selalu terlihat tetapi nonaktif pada mode Podcast; pergantian mode mempertahankan draft Mix.

Contoh transisi memakai aset bawaan dua foto kucing, fungsi bobot transisi studio, dan pola Kilatan yang sama. Preview visual bersifat senyap dan berbagi satu pemutar aktif dengan subtitle. Audisi shutter hanya diputar melalui klik pengguna, memakai katalog serta cache audio yang sama dengan studio, dan dihentikan ketika panel/halaman tidak aktif.
