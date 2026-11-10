import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw, Network, AlertCircle, CheckCircle2 } from 'lucide-react';
import { api, type ModelCatalog } from '../api';
import { Button } from './ui/button';
type Status = {
  configured: boolean;
  connected: boolean;
  connection_status: 'unconfigured' | 'configured' | 'checking' | 'connected' | 'unavailable';
  base_url?: string;
  masked_key?: string;
  error?: string;
  catalog: ModelCatalog;
};
export function RouterSettings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      setStatus(await api<Status>('/ai/status'));
      setError('');
    } catch (error) {
      setError((error as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  useEffect(() => {
    if (!status?.catalog.refreshing) return;
    const timer = setTimeout(() => void load(), 2000);
    return () => clearTimeout(timer);
  }, [status]);
  async function refresh() {
    setBusy(true);
    try {
      await api('/model-catalog/refresh', 'POST', {});
      await load();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const connection = status?.catalog.connections[0];
  return (
    <section className="panel settings-services settings-router" aria-labelledby="router-title">
      <header className="section-heading">
        <div>
          <h2 id="router-title">
            <Network size={20} aria-hidden="true" />
            <span>9Router</span>
          </h2>
          <p>Combo, akun, dan perpindahan model dikelola melalui dashboard 9Router.</p>
        </div>
        <Button
          variant="secondary"
          disabled={busy || !!status?.catalog.refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw size={16} className={busy || status?.catalog.refreshing ? 'spin' : ''} />
          Periksa koneksi
        </Button>
      </header>
      <div className="router-content">
        <div className="router-connection" role="status">
          <p className={'router-status ' + (status?.connected ? 'is-connected' : '')}>
            {status?.connected ? (
              <CheckCircle2 size={18} aria-hidden="true" />
            ) : (
              <Network size={18} aria-hidden="true" />
            )}
            <span>
              {!status
                ? error
                  ? 'Status koneksi belum diketahui'
                  : 'Memuat status koneksi…'
                : status.connection_status === 'connected'
                  ? 'Terhubung ke 9Router'
                  : status.connection_status === 'checking'
                    ? 'Memeriksa koneksi 9Router…'
                    : status.configured
                      ? 'Konfigurasi terpasang · koneksi belum berhasil'
                      : 'Konfigurasi belum lengkap'}
            </span>
          </p>
          {connection?.fetched_at && (
            <p className="router-updated">
              Katalog terakhir: {new Date(connection.fetched_at).toLocaleString('id-ID')}
            </p>
          )}
        </div>
        {status?.base_url && (
          <dl className="router-details">
            <div>
              <dt>Alamat</dt>
              <dd>{status.base_url}</dd>
            </div>
            <div>
              <dt>API key</dt>
              <dd>{status.masked_key || 'Belum diatur'}</dd>
            </div>
          </dl>
        )}
        {(error || status?.error || connection?.error) && (
          <p className="notice" role="alert">
            <AlertCircle size={16} />
            {error || status?.error || connection?.error}
          </p>
        )}
        <div className="router-catalog">
          <h3>Combo tersedia</h3>
          <p>
            {status?.catalog.refreshing
              ? 'Memeriksa katalog…'
              : connection?.error
                ? 'Katalog belum berhasil dibaca. Perbaiki koneksi lalu tekan Periksa koneksi.'
                : status?.connected
                  ? status.catalog.models.length
                    ? 'Katalog berhasil diakses.'
                    : 'Koneksi berhasil, tetapi katalog 9Router tidak memuat combo.'
                  : 'Katalog belum diperiksa.'}{' '}
            Pemeriksaan ini tidak mengirim prompt.
          </p>
          {!!status?.catalog.models.length && (
            <ul>
              {status.catalog.models.map((combo) => (
                <li key={combo.id}>{combo.name}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="router-help">
          <p>
            Isi <code>9router_base_url</code> dan <code>9router_key</code> di <code>.env</code>.
            Perubahan berlaku pada permintaan berikutnya tanpa restart.
          </p>
          <p>
            Jika backend memakai WSL dan 9Router berjalan di Windows, gunakan alamat host Windows
            yang dapat dijangkau dari WSL.
          </p>
        </div>
        <a
          className="button secondary router-dashboard"
          href={status?.base_url ? new URL('/', status.base_url).href : 'http://localhost:20128'}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={16} />
          Dashboard 9Router
        </a>
      </div>
    </section>
  );
}
