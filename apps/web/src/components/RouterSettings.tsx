import { useEffect, useState } from 'react';
import { ExternalLink, RefreshCw, Network, AlertCircle } from 'lucide-react';
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
    <section className="panel settings-services">
      <header className="section-heading">
        <div>
          <h2>
            <Network size={18} />
            9Router
          </h2>
          <p>Combo, akun, dan perpindahan model dikelola melalui dashboard 9Router.</p>
        </div>
        <Button
          variant="secondary"
          disabled={busy || !!status?.catalog.refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw size={16} />
          Periksa koneksi
        </Button>
      </header>
      <div className="mg-dialog-form">
        <p>
          {status?.connection_status === 'connected'
            ? 'Terhubung ke 9Router'
            : status?.connection_status === 'checking'
              ? 'Memeriksa koneksi 9Router…'
              : status?.configured
                ? 'Konfigurasi terpasang · koneksi belum berhasil'
                : 'Konfigurasi belum lengkap'}
          {connection?.fetched_at
            ? ' · Katalog terakhir ' + new Date(connection.fetched_at).toLocaleString('id-ID')
            : ''}
        </p>
        {status?.base_url && (
          <p>
            Alamat: {status.base_url} · Key: {status.masked_key}
          </p>
        )}
        {(error || status?.error || connection?.error) && (
          <p className="notice" role="alert">
            <AlertCircle size={16} />
            {error || status?.error || connection?.error}
          </p>
        )}
        <p>
          Isi <code>9router_base_url</code> dan <code>9router_key</code> di <code>.env</code>.
          Perubahan berlaku pada permintaan berikutnya tanpa restart.
        </p>
        <p className="field-help">
          Jika backend memakai WSL dan 9Router berjalan di Windows, gunakan alamat host Windows yang
          dapat dijangkau dari WSL.
        </p>
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
        <ul>
          {status?.catalog.models.map((combo) => (
            <li key={combo.id}>{combo.name}</li>
          ))}
        </ul>
        <a
          className="button secondary"
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
