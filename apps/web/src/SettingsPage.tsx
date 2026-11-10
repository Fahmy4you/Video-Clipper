import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Database,
  Server,
  KeyRound,
  Film,
  ChevronDown,
  Download,
  FolderOpen,
} from 'lucide-react';
import { api, type Health } from './api';
import { Button } from './components/ui/button';
import { ThemeSelect } from './components/Theme';
import './queue.css';
import { RouterSettings } from './components/RouterSettings';
type ExportConfig = {
  mode: string;
  local_dir: string | null;
  ready: boolean;
  error: string | null;
};
function ExportSettings() {
  const [config, setConfig] = useState<ExportConfig | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  async function reload() {
    setBusy(true);
    setError('');
    try {
      setConfig(await api<ExportConfig>('/export-config'));
    } catch (e) {
      setConfig(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  const local = config?.mode === 'local';
  const known = local || config?.mode === 'global';
  return (
    <section
      className="panel settings-services settings-export"
      aria-labelledby="export-settings-title"
    >
      <header className="section-heading">
        <div>
          <h2 id="export-settings-title">Penyimpanan hasil ekspor</h2>
          <p>Mode yang sedang digunakan oleh backend.</p>
        </div>
        <Button
          variant="secondary"
          aria-label="Periksa mode ekspor"
          disabled={busy}
          onClick={() => void reload()}
        >
          <RefreshCw size={16} className={busy ? 'spin' : ''} />
          Periksa ulang
        </Button>
      </header>
      <div className="service-row" role="status">
        <span className="service-icon" aria-hidden="true">
          {local ? <FolderOpen size={20} /> : <Download size={20} />}
        </span>
        <div>
          <strong>
            {config
              ? local
                ? 'Lokal'
                : known
                  ? 'Global'
                  : 'Mode tidak dikenal'
              : busy
                ? 'Memeriksa mode ekspor…'
                : 'Mode belum diketahui'}
          </strong>
          {known && (
            <p>
              {local
                ? 'Hasil ekspor disimpan otomatis ke folder tujuan.'
                : 'Hasil ekspor diunduh melalui browser.'}
            </p>
          )}
        </div>
        {config && (
          <span className={'service-status ' + (config.ready && known ? 'ready' : 'pending')}>
            {config.ready && known ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
            {busy ? 'Memeriksa…' : config.ready && known ? 'Siap' : 'Perlu diperiksa'}
          </span>
        )}
      </div>
      {local && (
        <div className="settings-export-folder">
          <strong>Folder tujuan</strong>
          <p>{config.local_dir || 'Folder tujuan belum diatur.'}</p>
        </div>
      )}
      {(error || config?.error) && (
        <p className="notice" role="alert">
          <AlertCircle size={18} />
          {error || config?.error}
        </p>
      )}
      <p className="field-help">
        Mode diatur melalui <code>EXPORT_MODE</code> di <code>.env</code>. Setelah mengubahnya,
        restart backend dan worker, lalu periksa ulang.
      </p>
    </section>
  );
}
export function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function reload() {
    setBusy(true);
    setError('');
    try {
      const h = await api<Health>('/health');
      setHealth(h);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  const services = [
    [
      'PostgreSQL Windows',
      'Penyimpanan proyek dan metadata',
      health?.database === 'ready',
      Database,
    ],
    ['Redis lokal', 'Antrean pemrosesan video', health?.redis, Server],
    ['FFmpeg', 'Pemrosesan media dan ekspor', health?.ffmpeg, Film],
    ['9Router', 'Analisis dan pemilihan highlight', health?.router, KeyRound],
  ] as const;
  return (
    <main className="settings-page page-container">
      <header className="page-heading">
        <div>
          <h1>Pengaturan</h1>
          <p>Tampilan aplikasi dan kesiapan layanan workspace.</p>
        </div>
      </header>
      {error && (
        <p className="notice" role="alert">
          <AlertCircle size={18} />
          {error}
        </p>
      )}
      {health?.worker && health.worker.status !== 'ready' && (
        <p className="notice" role="status">
          <AlertCircle size={18} />
          {health.worker.message}
        </p>
      )}
      <section className="panel settings-appearance">
        <div>
          <h2>Tampilan</h2>
          <p>Tema mengikuti sistem atau pilihanmu di browser ini.</p>
        </div>
        <ThemeSelect />
      </section>
      <ExportSettings />
      <section className="panel settings-services">
        <header className="section-heading">
          <div>
            <h2>Status layanan</h2>
            <p>Konfigurasi koneksi disimpan pada backend Ubuntu.</p>
          </div>
          <Button variant="secondary" disabled={busy} onClick={() => void reload()}>
            <RefreshCw size={16} className={busy ? 'spin' : ''} />
            Periksa ulang
          </Button>
        </header>
        {services.map(([name, desc, ready, Icon]) => (
          <div className="service-row" key={name}>
            <span className="service-icon">
              <Icon size={20} />
            </span>
            <div>
              <strong>{name}</strong>
              <p>{desc}</p>
            </div>
            <span className={'service-status ' + (ready ? 'ready' : 'pending')}>
              {ready ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}{' '}
              {!health
                ? 'Memeriksa'
                : ready
                  ? name === '9Router'
                    ? 'Terhubung'
                    : 'Siap'
                  : 'Perlu diperiksa'}
            </span>
          </div>
        ))}
      </section>
      <RouterSettings />
      <details className="panel mt-5 setup-help">
        <summary>
          Hubungkan PostgreSQL dan 9Router
          <ChevronDown size={18} />
        </summary>
        <div>
          <ol>
            <li>Buka pgAdmin Windows dan siapkan database khusus video_clipping.</li>
            <li>Ikuti panduan docs/SETUP.md untuk koneksi WSL.</li>
            <li>Isi DATABASE_URL, 9router_base_url, dan 9router_key pada .env.</li>
            <li>
              Perubahan koneksi 9Router langsung berlaku. Konfigurasi database memerlukan restart.
            </li>
          </ol>
          <pre>npm run dev</pre>
          <p className="field-help">
            Jangan masukkan password atau API key ke chat. API key tidak ditampilkan kembali setelah
            disimpan.
          </p>
        </div>
      </details>
    </main>
  );
}
