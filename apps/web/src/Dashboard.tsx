import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Link2, Plus, Loader2, ArrowRight, Film, AlertCircle } from 'lucide-react';
import { api, type Project, type Health } from './api';

import { Button } from './components/ui/button';
import { ModelSelect } from './components/ModelSelect';
import { Dialog } from './components/Ui';
import { QueueOverview } from './components/QueueStatus';
export function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null),
    [error, setError] = useState(''),
    [url, setUrl] = useState(''),
    [model, setModel] = useState(''),
    [busy, setBusy] = useState(false),
    [count, setCount] = useState(3),
    [prompt, setPrompt] = useState('');
  const [checking, setChecking] = useState(false);
  const [sourceInfo, setSourceInfo] = useState<{ title: string; duration: number } | null>(null);
  const [existing, setExisting] = useState<{ id: string; title: string }[]>([]);
  const nav = useNavigate(),
    submission = useRef<{ body: string; id: string } | null>(null);
  useEffect(() => {
    api<Health>('/health')
      .then(setHealth)
      .catch(() => setError('Backend belum terhubung.'));
  }, []);
  async function submit(projectId?: string) {
    setBusy(true);
    setError('');
    try {
      const body = {
        url,
        ai_combo: model,
        highlight_count: count,
        additional_prompt: prompt,
        workflow: 'review',
        enqueue_analysis: true,
      };
      const text = JSON.stringify({ ...body, projectId });
      if (submission.current?.body !== text)
        submission.current = { body: text, id: crypto.randomUUID() };
      if (projectId) {
        await api('/projects/' + projectId + '/searches', 'POST', {
          request_id: submission.current.id,
          ai_combo: model,
          highlight_count: count,
          additional_prompt: prompt,
          policy_version: 2,
        });
        nav('/transcriptions/' + projectId);
      } else {
        await api<Project>('/projects', 'POST', { ...body, request_id: submission.current.id });
        nav('/transcriptions');
      }
      setExisting([]);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function create(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      setChecking(true);
      try {
        const info = await api<{ title: string; duration: number }>('/sources/inspect', 'POST', {
          url,
        });
        setSourceInfo(info);
      } finally {
        setChecking(false);
      }
      const found = await api<{ id: string; title: string }[]>(
        '/source-projects?url=' + encodeURIComponent(url),
      );
      if (found.length) {
        setExisting(found);
        return;
      }
      await submit();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard page-container">
      <header className="page-heading">
        <div>
          <h1>Buat proyek</h1>
          <p>Temukan bagian penting, tinjau usulannya, lalu proses yang kamu setujui.</p>
        </div>
        <Link className="button secondary" to="/transcriptions">
          <Film size={16} />
          Lihat proyek
        </Link>
      </header>
      {error && (
        <div role="alert" className="notice">
          <AlertCircle size={18} />
          {error}
        </div>
      )}
      <QueueOverview />
      <div className="generation-layout">
        <form className="generation-form panel" onSubmit={create}>
          <section className="form-section">
            <div className="section-heading">
              <h2>Video sumber</h2>
              <span className="step-badge">01</span>
            </div>
            <label htmlFor="youtube">URL YouTube</label>
            <div className="url-field">
              <Link2 size={18} />
              <input
                id="youtube"
                type="url"
                placeholder="https://youtube.com/watch?v=…"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setSourceInfo(null);
                }}
                required
                disabled={busy}
              />
            </div>
            {checking && <p role="status">Memeriksa durasi dan ketersediaan video YouTube…</p>}
            {sourceInfo && (
              <p className="field-help">
                {sourceInfo.title} · {Math.floor(sourceInfo.duration / 60)} menit{' '}
                {Math.floor(sourceInfo.duration % 60)} detik
              </p>
            )}
            <div className="ingest-options">
              <ModelSelect value={model} onChange={setModel} disabled={busy} />
              <label>
                Jumlah highlight
                <select
                  aria-label="Jumlah highlight"
                  value={count}
                  disabled={busy}
                  onChange={(e) => setCount(+e.target.value)}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n} highlight
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>
          <section className="form-section">
            <div className="section-heading">
              <h2>Arahan tambahan</h2>
              <span className="optional-label">Opsional</span>
            </div>
            <label htmlFor="additional-prompt" className="sr-only">
              Prompt tambahan
            </label>
            <textarea
              id="additional-prompt"
              maxLength={4000}
              rows={3}
              disabled={busy}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Contoh: Cari pembahasan tentang disiplin sekitar 12:30, hindari promosi."
            />
            <div className="field-meta">
              <span>Topik ini termasuk dalam jumlah highlight pilihanmu.</span>
              <span>{prompt.length}/4000</span>
            </div>
          </section>
          <footer className="form-actions">
            <span>Usulan akan muncul di Proyek Transkripsi.</span>
            <Button disabled={busy || health?.database !== 'ready' || !model}>
              {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}Buat proyek
            </Button>
          </footer>
        </form>
        <aside className="generation-guide">
          <div className="guide-icon">
            <Film size={24} />
          </div>
          <h2>Dari percakapan ke cerita</h2>
          <ol>
            <li>
              <span>1</span>
              <div>
                <strong>Analisis video</strong>
                <p>AI memilih momen berdasarkan konteks percakapan.</p>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <strong>Pilih highlight</strong>
                <p>Periksa transkrip dan revisi rentang sebelum menyusun video.</p>
              </div>
            </li>
            <li>
              <span>3</span>
              <div>
                <strong>Proses dan edit</strong>
                <p>Tentukan tampilan, proses video, lalu lanjutkan ke studio.</p>
              </div>
            </li>
          </ol>
          <p className="guide-note">Video dan hasil ekspor tersimpan di perangkatmu.</p>
        </aside>
      </div>
      {health && health.database !== 'ready' && (
        <div className="notice">
          <AlertCircle size={18} />
          <div>
            <strong>Database belum terhubung</strong>
            <p>Periksa koneksi PostgreSQL sebelum membuat proyek.</p>
            <Link to="/settings">
              Buka pengaturan <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      )}
      <Dialog
        open={existing.length > 0}
        onClose={() => {
          if (!busy) setExisting([]);
        }}
        title="Sumber ini sudah memiliki proyek"
        description="Gunakan proyek yang sudah ada atau buat proyek terpisah. Audio dan transkrip yang valid dapat digunakan kembali."
        footer={
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setExisting([])}>
              Batal
            </Button>
            <Button disabled={busy} onClick={() => void submit()}>
              Buat proyek terpisah
            </Button>
          </>
        }
      >
        <div className="mg-dialog-form">
          {existing.map((project) => (
            <div className="panel mg-dialog-form" key={project.id}>
              <strong>{project.title}</strong>
              <Button disabled={busy} onClick={() => void submit(project.id)}>
                Gunakan proyek ini
              </Button>
            </div>
          ))}
          {error && (
            <p className="notice" role="alert">
              {error}
            </p>
          )}
        </div>
      </Dialog>
    </main>
  );
}
