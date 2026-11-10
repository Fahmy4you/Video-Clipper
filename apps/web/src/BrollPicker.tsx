import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, Film, Search, X } from 'lucide-react';
import { type VideoAsset } from './editorModel';
import { api } from './api';
import { durationLabel } from './timeRange';
import { BrollFilter } from './BrollFilter';
import { brollOptions, matchesBroll } from './brollFilters';
import './broll-picker.css';
import { SourcePicker } from './SourcePicker';
export function BrollPicker({
  assets,
  length,
  assetId,
  sourceIn,
  onCancel,
  onUse,
}: {
  assets: VideoAsset[];
  length: number;
  assetId?: string;
  sourceIn?: number;
  onCancel: () => void;
  onUse: (a: VideoAsset, start: number) => void;
}) {
  const [chosen, setChosen] = useState<VideoAsset | undefined>(
      assets.find((a) => a.id === assetId),
    ),
    [q, setQ] = useState(''),
    [tags, setTags] = useState<string[]>([]),
    [owners, setOwners] = useState<string[]>([]),
    [filter, setFilter] = useState<'tags' | 'owners' | null>(null);
  const toggleTags = useCallback((open: boolean) => setFilter(open ? 'tags' : null), []);
  const toggleOwners = useCallback((open: boolean) => setFilter(open ? 'owners' : null), []);
  const available = useMemo(
    () => assets.filter((a) => a.status === 'ready' && !a.archived),
    [assets],
  );
  const [ownersCatalog, setOwnersCatalog] = useState<{ id: string; name: string }[]>([]);
  const [ownerError, setOwnerError] = useState('');
  const [ownerRetry, setOwnerRetry] = useState(0);
  useEffect(() => {
    if (!available.some((a) => a.scope === 'instansi')) return;
    let live = true;
    setOwnerError('');
    // Asset owner IDs and display names are independently sorted by the API.
    // Use the existing catalog to preserve the correct ID/name association.
    api<{ id: string; name: string }[]>('/instansi')
      .then((items) => {
        if (live) setOwnersCatalog(items);
      })
      .catch((e) => {
        if (live) setOwnerError(e.message);
      });
    return () => {
      live = false;
    };
  }, [available, ownerRetry]);
  const options = useMemo(() => brollOptions(available, ownersCatalog), [available, ownersCatalog]);
  const matches = available.filter((a) => matchesBroll(a, q, tags, owners));
  const active = tags.length + owners.length > 0;
  function reset() {
    setTags([]);
    setOwners([]);
  }

  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!chosen) dialog.current?.showModal();
    return () => dialog.current?.close();
  }, [chosen]);
  if (chosen)
    return (
      <SourcePicker
        asset={chosen}
        length={length}
        initial={sourceIn || 0}
        onCancel={onCancel}
        onUse={(a) => onUse(chosen, a)}
      />
    );
  return createPortal(
    <dialog
      ref={dialog}
      className="source-modal broll-picker-modal"
      onCancel={(e) => {
        e.preventDefault();
        if (filter) setFilter(null);
        else onCancel();
      }}
      aria-labelledby="broll-picker-title"
    >
      <header>
        <div>
          <h2 id="broll-picker-title">Pilih video sisipan</h2>
          <p>
            Durasi slot {durationLabel(length)}. Pilih video untuk menentukan bagian yang digunakan.
            Pilihan manual dapat memakai seluruh koleksi; batas instansi berlaku untuk Mix otomatis.
          </p>
        </div>
        <button onClick={onCancel} aria-label="Tutup pemilih video" title="Tutup pemilih video">
          <X size={18} />
        </button>
      </header>
      <div className="broll-filter-toolbar">
        <div className="broll-search">
          <Search size={16} />
          <input
            aria-label="Cari video sisipan"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Cari judul, deskripsi, atau hashtag…"
          />
        </div>

        <BrollFilter
          label="Hashtag"
          options={options.hashtags}
          value={tags}
          onChange={setTags}
          open={filter === 'tags'}
          onOpen={toggleTags}
        />
        <BrollFilter
          label="Instansi"
          options={options.instansi}
          value={owners}
          onChange={setOwners}
          open={filter === 'owners'}
          onOpen={toggleOwners}
        />
        {ownerError && (
          <span className="broll-filter-error" role="alert">
            Filter instansi belum dapat dimuat.
            <button type="button" onClick={() => setOwnerRetry((n) => n + 1)}>
              Coba lagi
            </button>
          </span>
        )}
        <span role="status">
          {matches.length} dari {available.length} video
        </span>
        {active && (
          <button type="button" className="broll-reset" onClick={reset}>
            Reset filter
          </button>
        )}
      </div>
      <div className="broll-picker-list">
        {matches.map((a) => (
          <button
            className="broll-choice"
            key={a.id}
            disabled={a.frames < length}
            onClick={() => {
              setFilter(null);
              setChosen(a);
            }}
          >
            <img src={a.thumbnail_url} alt="" />
            <div>
              <strong>{a.title}</strong>
              <p>{a.explain}</p>
              <span className="broll-tags">
                {a.hashtags.slice(0, 3).map((tag) => (
                  <span key={tag}>#{tag}</span>
                ))}
                {a.hashtags.length > 3 && <span>+{a.hashtags.length - 3}</span>}
              </span>
              <span className="broll-choice-meta">
                <span className="source-owner-label">
                  {a.scope === 'global' ? 'Global' : a.instansi_names.join(' · ') || 'Instansi'}
                </span>
                <span>{durationLabel(a.frames)}</span>
              </span>
              {a.frames < length && (
                <small className="broll-short">Terlalu pendek untuk slot</small>
              )}
            </div>
            <span className="broll-choice-duration">
              {a.frames >= length && <ArrowRight size={18} />}
            </span>
          </button>
        ))}
        {!matches.length && (
          <div className="broll-empty">
            <Film size={28} />
            <strong>
              {available.length ? 'Video tidak ditemukan' : 'Belum ada video siap pakai'}
            </strong>
            <p>
              {available.length
                ? 'Coba ubah pencarian, hashtag, atau instansi yang dipilih.'
                : 'Tambahkan footage melalui halaman Koleksi video, lalu tunggu pemrosesan selesai.'}
            </p>
            {active && (
              <button type="button" onClick={reset}>
                Reset filter
              </button>
            )}
          </div>
        )}
      </div>
      <footer>
        <span>Video sisipan menggunakan audio podcast yang sedang diedit.</span>
        <button onClick={onCancel}>Batal</button>
      </footer>
    </dialog>,
    document.body,
  );
}
