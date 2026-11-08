import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Film, LoaderCircle, Pencil, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react';
import { api } from './api';
import { timecode, type VideoAsset } from './editorModel';
import { SourceOwnership, type Instansi } from './components/SourceOwnership';
import { ActionItem, ActionMenu, Dialog, Pagination, useConfirm } from './components/Ui';
import {
  BulkBar,
  SelectionToggle,
  SelectCheckbox,
  useBulkSelection,
  deleteSelected,
  deletionMessage,
} from './components/BulkSelection';
import { FilterDock, SortSelect } from './components/ListFilters';
import { TagSelect } from './components/Ui';
import { compareDates, compareNames } from './listFilters';
import './library.css';

const statusLabel = (status: string) =>
  status === 'ready'
    ? 'Siap digunakan'
    : status === 'failed'
      ? 'Gagal diproses'
      : 'Sedang diproses';
export function VideoLibrary() {
  const [assets, setAssets] = useState<VideoAsset[]>([]),
    [query, setQuery] = useState(''),
    [page, setPage] = useState(1),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [uploading, setUploading] = useState(false),
    [busy, setBusy] = useState<string | null>(null),
    [deleting, setDeleting] = useState(false),
    [progress, setProgress] = useState(0),
    [result, setResult] = useState('');
  const [filterTags, setFilterTags] = useState<string[]>([]),
    [filterSources, setFilterSources] = useState<string[]>([]),
    [sort, setSort] = useState('created-desc');
  const sortOptions = [
    { value: 'created-desc', label: 'Tanggal dibuat · terbaru' },
    { value: 'created-asc', label: 'Tanggal dibuat · terlama' },
  ];
  const filterActive =
    !!(query || filterTags.length || filterSources.length) || sort !== 'created-desc';
  function resetFilters() {
    setQuery('');
    setFilterTags([]);
    setFilterSources([]);
    setSort('created-desc');
    setPage(1);
  }
  const tagOptions = useMemo(
    () =>
      [...new Set(assets.flatMap((a) => a.hashtags))]
        .sort(compareNames)
        .map((t) => ({ id: t, label: t })),
    [assets],
  );
  const selection = useBulkSelection(assets.map((a) => a.id));
  const confirm = useConfirm(),
    navigate = useNavigate();
  const [instansi, setInstansi] = useState<Instansi[]>([]),
    [uploadOpen, setUploadOpen] = useState(false),
    [uploadFile, setUploadFile] = useState<File | null>(null),
    [uploadScope, setUploadScope] = useState<'global' | 'instansi' | ''>(''),
    [uploadOwners, setUploadOwners] = useState<string[]>([]);
  const sourceOptions = [
    { id: 'global', label: 'Global' },
    ...instansi.map((i) => ({ id: i.id, label: i.name })),
  ];
  useEffect(() => {
    void api<Instansi[]>('/instansi')
      .then(setInstansi)
      .catch((e) => setError(e.message));
  }, []);
  function openUpload() {
    setUploadFile(null);
    setUploadScope('');
    setUploadOwners([]);
    setError('');
    setUploadOpen(true);
    void api<Instansi[]>('/instansi')
      .then(setInstansi)
      .catch((e) => setError(e.message));
  }
  async function refresh() {
    try {
      setAssets(await api<VideoAsset[]>('/video-clips'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);
  const filtered = useMemo(() => {
    const text = query.trim().toLowerCase();
    return assets
      .filter(
        (asset) =>
          (
            asset.title +
            ' ' +
            asset.hashtags.map((tag) => '#' + tag).join(' ') +
            ' ' +
            asset.explain
          )
            .toLowerCase()
            .includes(text) &&
          filterTags.every((tag) => asset.hashtags.includes(tag)) &&
          (!filterSources.length ||
            (asset.scope === 'global'
              ? filterSources.includes('global')
              : asset.instansi_ids.some((id) => filterSources.includes(id)))),
      )
      .sort(
        (a, b) =>
          compareDates(a.created_at, b.created_at, sort === 'created-asc') ||
          compareNames(a.title, b.title) ||
          a.id.localeCompare(b.id),
      );
  }, [assets, query, filterTags, filterSources, sort]);
  const currentPage = Math.min(page, Math.max(1, Math.ceil(filtered.length / 25))),
    visible = filtered.slice((currentPage - 1) * 25, currentPage * 25);
  async function action(id: string, fn: () => Promise<unknown>) {
    setBusy(id);
    setError('');
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function add(file: File) {
    setUploading(true);
    setError('');
    try {
      const data = new FormData();
      data.append('file', file);
      data.append('scope', uploadScope);
      if (uploadScope === 'instansi') uploadOwners.forEach((id) => data.append('instansi_ids', id));
      data.append('title', file.name.replace(/\.[^.]+$/, ''));
      const response = await fetch('/api/video-clips', { method: 'POST', body: data }),
        result = await response.json();
      if (!response.ok)
        throw Error(
          typeof result.detail === 'string' ? result.detail : 'Periksa file dan lingkup video.',
        );
      setUploadOpen(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  async function remove(asset: VideoAsset) {
    if (
      await confirm({
        title: 'Hapus video permanen?',
        description:
          '“' +
          asset.title +
          '” beserta file sumber, proxy, thumbnail, adegan, dan relasi hashtag akan dihapus permanen. Hashtag bersama tetap tersedia. Video yang masih dipakai highlight tidak dapat dihapus.',
        confirmLabel: 'Hapus permanen',
        danger: true,
      })
    )
      void action(asset.id, async () => {
        const result = await api<{ cleanup_pending?: boolean }>(
          '/video-clips/' + asset.id,
          'DELETE',
        );
        setResult(
          result.cleanup_pending
            ? 'Data video dihapus. Sebagian berkas lokal belum berhasil dibersihkan.'
            : 'Video dan berkas koleksinya telah dihapus permanen.',
        );
      });
  }
  async function removeSelected() {
    const ids = [...selection.selected];
    if (!ids.length || deleting) return;
    if (
      !(await confirm({
        title: 'Hapus ' + ids.length + ' video dari koleksi?',
        description:
          'Data video terpilih beserta file sumber, proxy, thumbnail, adegan, dan relasi hashtag akan dihapus permanen. Video yang masih dipakai highlight atau pekerjaan aktif tetap disimpan dan dilaporkan sebagai gagal dihapus.',
        confirmLabel: 'Hapus permanen',
        danger: true,
      }))
    )
      return;
    setDeleting(true);
    setProgress(0);
    setError('');
    setResult('');
    try {
      const outcome = await deleteSelected(ids, (id) => '/video-clips/' + id, setProgress);
      setAssets((rows) => rows.filter((a) => !outcome.deleted.includes(a.id)));
      selection.remove(outcome.deleted);
      setResult(deletionMessage(outcome));
      await refresh();
    } finally {
      setDeleting(false);
    }
  }
  return (
    <main className="library-page page-container">
      <header className="library-heading selection-page-header">
        <div>
          <h1>Koleksi video</h1>
          <p>Bahan visual untuk Mix. Kelola informasi dan adegan setiap video.</p>
        </div>
        <div className="page-header-actions">
          <SelectionToggle
            active={selection.selecting}
            onToggle={selection.toggleMode}
            disabled={
              loading || uploading || !!busy || deleting || (!selection.selecting && !assets.length)
            }
          />
          <button
            type="button"
            className="primary"
            disabled={uploading || deleting}
            onClick={openUpload}
          >
            {uploading ? <LoaderCircle size={17} className="spin" /> : <Upload size={17} />}
            <span>{uploading ? 'Mengunggah…' : 'Video'}</span>
          </button>
        </div>
      </header>
      {result && (
        <p className="bulk-result" role="status">
          {result}
        </p>
      )}
      {error && (
        <div role="alert" className="library-message is-error">
          <span>{error}</span>
          <button
            type="button"
            title="Tutup pesan"
            aria-label="Tutup pesan"
            onClick={() => setError('')}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <div className="library-list-toolbar">
        <label className="library-search">
          <Search size={18} />
          <input
            aria-label="Cari koleksi"
            placeholder="Cari judul, hashtag, atau isi visual…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
          />
          {query && (
            <button
              type="button"
              aria-label="Kosongkan pencarian"
              title="Kosongkan pencarian"
              onClick={() => {
                setQuery('');
                setPage(1);
              }}
            >
              <X size={15} />
            </button>
          )}
        </label>
        <span>{filtered.length} video</span>
      </div>
      <FilterDock
        active={filterActive}
        summary={`${filtered.length} dari ${assets.length} video · ${sortOptions.find((o) => o.value === sort)?.label}${filterTags.length ? ' · ' + filterTags.length + ' hashtag' : ''}${filterSources.length ? ' · ' + filterSources.length + ' sumber' : ''}`}
        onReset={resetFilters}
      >
        <div>
          <TagSelect
            label="Filter hashtag"
            options={tagOptions}
            value={filterTags}
            max={tagOptions.length}
            onChange={(v) => {
              setFilterTags(v);
              setPage(1);
            }}
            showAllSelected
          />
          <p className="filter-help">Video harus memiliki semua hashtag yang dipilih.</p>
        </div>
        <div>
          <TagSelect
            label="Filter instansi / Global"
            options={sourceOptions}
            value={filterSources}
            max={sourceOptions.length}
            prefix=""
            noun="sumber"
            onChange={(v) => {
              setFilterSources(v);
              setPage(1);
            }}
            showAllSelected
          />
          <p className="filter-help">
            Kosong berarti semua sumber. Beberapa pilihan memakai salah satu sumber.
          </p>
        </div>
        <SortSelect
          value={sort}
          onChange={(v) => {
            setSort(v);
            setPage(1);
          }}
          options={sortOptions}
        />
      </FilterDock>
      {selection.selecting && !loading && assets.length > 0 && (
        <BulkBar
          selected={selection.selected}
          visibleIds={visible.map((a) => a.id)}
          onTogglePage={() => selection.togglePage(visible.map((a) => a.id))}
          onClear={selection.clear}
          onDelete={() => void removeSelected()}
          disabled={uploading || !!busy}
          deleting={deleting}
          progress={progress}
        />
      )}
      {loading ? (
        <div className="library-empty" role="status">
          <LoaderCircle size={24} className="spin" />
          <h2>Memuat koleksi</h2>
          <p>Informasi video sedang disiapkan.</p>
        </div>
      ) : visible.length ? (
        <>
          <div className="library-list" aria-label="Daftar video koleksi">
            {visible.map((asset) => (
              <article
                className={
                  'library-row ' +
                  (selection.selecting ? 'has-select ' : '') +
                  (selection.selected.has(asset.id) ? 'is-selected' : '')
                }
                key={asset.id}
              >
                {selection.selecting && (
                  <SelectCheckbox
                    label={'Pilih video ' + asset.title}
                    checked={selection.selected.has(asset.id)}
                    disabled={deleting || !!busy}
                    onChange={() => selection.toggle(asset.id)}
                  />
                )}
                <Link
                  className="library-thumb"
                  to={'/library/' + asset.id}
                  aria-label={'Buka ' + asset.title}
                >
                  {asset.status === 'ready' && asset.thumbnail_url ? (
                    <img src={asset.thumbnail_url} alt="" loading="lazy" />
                  ) : (
                    <Film size={28} />
                  )}
                  <span className="timecode">{timecode(asset.frames)}</span>
                </Link>
                <div className="library-row-content">
                  <span className="source-owner-label">
                    {asset.scope === 'global'
                      ? 'Global'
                      : asset.instansi_names.join(' · ') || 'Instansi'}
                  </span>
                  <Link
                    className="library-video-title line-clamp-2"
                    to={'/library/' + asset.id}
                    title={asset.title}
                  >
                    {asset.title}
                  </Link>
                  <p className="library-description line-clamp-2">
                    {asset.explain || 'Belum ada penjelasan isi visual.'}
                  </p>
                  <div className="library-tags">
                    {asset.hashtags.slice(0, 3).map((tag) => (
                      <span className="library-tag" key={tag}>
                        #{tag}
                      </span>
                    ))}
                    {asset.hashtags.length > 3 && (
                      <span
                        className="library-tag"
                        title={asset.hashtags
                          .slice(3)
                          .map((tag) => '#' + tag)
                          .join(', ')}
                      >
                        +{asset.hashtags.length - 3}
                      </span>
                    )}
                    {!asset.hashtags.length && (
                      <span className="library-no-tags">Tanpa hashtag</span>
                    )}
                  </div>
                </div>
                <div className="library-row-meta">
                  <span
                    className={
                      'library-status ' +
                      (asset.status === 'ready'
                        ? 'is-ready'
                        : asset.status === 'failed'
                          ? 'is-failed'
                          : 'is-processing')
                    }
                  >
                    {asset.status !== 'ready' && asset.status !== 'failed' && (
                      <LoaderCircle size={12} className="spin" />
                    )}
                    {statusLabel(asset.status)}
                  </span>
                  <small>
                    {asset.status === 'ready'
                      ? asset.scenes.length + ' adegan · ' + asset.width + ' × ' + asset.height
                      : asset.status === 'failed'
                        ? asset.error || 'Proses Ulang ulang video ini.'
                        : 'Menyiapkan preview dan thumbnail'}
                  </small>
                </div>
                <div className="library-row-actions">
                  <ActionMenu label={'Aksi ' + asset.title}>
                    <ActionItem
                      disabled={deleting || busy === asset.id}
                      onClick={() => navigate('/library/' + asset.id)}
                    >
                      <Pencil size={16} />
                      Edit video
                    </ActionItem>
                    {asset.status === 'failed' && (
                      <ActionItem
                        disabled={deleting || busy === asset.id}
                        onClick={() =>
                          void action(asset.id, () =>
                            api('/video-clips/' + asset.id + '/retry', 'POST'),
                          )
                        }
                      >
                        <RefreshCw size={16} />
                        Proses Ulang ulang
                      </ActionItem>
                    )}
                    <ActionItem
                      danger
                      disabled={deleting || busy === asset.id}
                      onClick={() => void remove(asset)}
                    >
                      <Trash2 size={16} />
                      Hapus permanen
                    </ActionItem>
                  </ActionMenu>
                </div>
              </article>
            ))}
          </div>
          <Pagination page={currentPage} total={filtered.length} pageSize={25} onChange={setPage} />
        </>
      ) : (
        <div className="library-empty">
          <Film size={28} />
          <h2>{filterActive ? 'Video tidak ditemukan' : 'Belum ada video koleksi'}</h2>
          <p>
            {filterActive
              ? 'Coba kata kunci, hashtag, atau sumber lain.'
              : 'Unggah video pertama untuk digunakan sebagai sisipan Mix.'}
          </p>
          {filterActive ? (
            <button type="button" onClick={resetFilters}>
              Reset filter
            </button>
          ) : (
            <button type="button" className="primary" onClick={openUpload}>
              <Upload size={16} />
              Video
            </button>
          )}
        </div>
      )}
      <Dialog
        open={uploadOpen}
        onClose={() => {
          if (!uploading) setUploadOpen(false);
        }}
        title="Unggah video koleksi"
        description="Pilih video dan tentukan lingkup penggunaannya."
        footer={
          <>
            <button
              className="button secondary"
              disabled={uploading}
              onClick={() => setUploadOpen(false)}
            >
              Batal
            </button>
            <button
              className="primary"
              form="library-upload"
              disabled={
                uploading ||
                !uploadFile ||
                !uploadScope ||
                (uploadScope === 'instansi' && !uploadOwners.length)
              }
            >
              {uploading ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}Video
            </button>
          </>
        }
      >
        <form
          id="library-upload"
          className="mg-dialog-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (uploadFile && uploadScope && (uploadScope === 'global' || uploadOwners.length))
              void add(uploadFile);
          }}
        >
          <label>
            File video
            <input
              aria-label="File video"
              type="file"
              accept="video/*"
              required
              disabled={uploading}
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </label>
          <SourceOwnership
            scope={uploadScope}
            instansiIds={uploadOwners}
            instansi={instansi}
            onChange={(scope, id) => {
              setUploadScope(scope);
              setUploadOwners(id);
            }}
            disabled={uploading}
          />
          {error && (
            <p role="alert" className="mg-form-error">
              {error}
            </p>
          )}
        </form>
      </Dialog>
    </main>
  );
}
