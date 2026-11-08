import { ExportDownloads } from './ExportDownloads';
import { lazy, Suspense, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  createBrowserRouter,
  RouterProvider,
  NavLink,
  Link,
  Outlet,
  useLocation,
} from 'react-router-dom';
import {
  FileText,
  Building2,
  Scissors,
  Plus,
  Settings2,
  FolderOpen,
  Film,
  Hash,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
} from 'lucide-react';
import { ProjectsPage, HighlightsPage } from './ProjectPages';
import { InstansiPage } from './InstansiPage';
import { HashtagsPage } from './HashtagsPage';
import { VideoLibrary } from './VideoLibrary';
const LibraryDetail = lazy(() =>
  import('./LibraryDetail').then((m) => ({ default: m.LibraryDetail })),
);
const VisualEditor = lazy(() =>
  import('./VisualEditor').then((m) => ({ default: m.VisualEditor })),
);
import { Dashboard } from './Dashboard';
import { SettingsPage } from './SettingsPage';
import { ThemeProvider, ThemeSelect } from './components/Theme';
import { ConfirmProvider } from './components/Ui';
import './style.css';
import './project-pages.css';
function AppLayout() {
  const location = useLocation(),
    studio = /^\/projects\/[^/]+\/clips\//.test(location.pathname);
  const [collapsed, setCollapsed] = useState(() => {
      try {
        return localStorage.getItem('vc-nav-collapsed') === 'true';
      } catch {
        return false;
      }
    }),
    [drawer, setDrawer] = useState(false);
  useEffect(() => {
    setDrawer(false);
  }, [location.pathname]);
  function toggle() {
    setCollapsed((v) => {
      try {
        localStorage.setItem('vc-nav-collapsed', String(!v));
      } catch {}
      return !v;
    });
  }
  const links = [
    ['/', 'Buat proyek', Plus],
    ['/transcriptions', 'Proyek Transkripsi', FileText],
    ['/projects', 'Proyek Video', FolderOpen],
    ['/library', 'Koleksi video', Film],
    ['/hashtags', 'Hashtag', Hash],
    ['/instansi', 'Instansi', Building2],
    ['/settings', 'Pengaturan', Settings2],
  ] as const;
  return (
    <div
      className={
        'shell ' +
        (collapsed ? 'nav-collapsed ' : '') +
        (studio ? 'is-studio ' : '') +
        (drawer ? 'drawer-open' : '')
      }
    >
      <a className="skip-link" href="#main-content">
        Lewati navigasi
      </a>
      {!studio && (
        <>
          <button
            className="drawer-backdrop"
            aria-label="Tutup navigasi"
            onClick={() => setDrawer(false)}
          />
          <aside className="rail">
            <Link className="brand" to="/" aria-label="Video Clipping">
              <span className="brand-icon">
                <Scissors size={23} />
              </span>
              <span>
                video_clipping<small>Workspace lokal</small>
              </span>
            </Link>
            <nav aria-label="Navigasi utama">
              {links.map(([to, label, Icon]) => (
                <NavLink key={to} to={to} end={to === '/'} aria-label={label} title={label}>
                  <Icon size={20} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </nav>
            <button
              className="nav-collapse"
              onClick={toggle}
              title={collapsed ? 'Perluas navigasi' : 'Lipat navigasi'}
              aria-label={collapsed ? 'Perluas navigasi' : 'Lipat navigasi'}
            >
              {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
              <span>Lipat sidebar</span>
            </button>
          </aside>
        </>
      )}
      <div className="workspace">
        {!studio && (
          <header className="topbar">
            <div>
              <button
                className="icon-button mobile-menu"
                aria-label={drawer ? 'Tutup navigasi' : 'Buka navigasi'}
                onClick={() => setDrawer(!drawer)}
              >
                {drawer ? <X size={20} /> : <Menu size={20} />}
              </button>
              <span className="workspace-title">Workspace</span>
            </div>
            <ThemeSelect />
          </header>
        )}
        <div id="main-content">
          <Suspense
            fallback={
              <div className="page-container" role="status">
                Memuat halaman…
              </div>
            }
          >
            <Outlet />
          </Suspense>
          <ExportDownloads />
        </div>
      </div>
    </div>
  );
}
const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/transcriptions', element: <ProjectsPage view="transcription" /> },
      { path: '/transcriptions/:id', element: <HighlightsPage view="transcription" /> },
      {
        path: '/transcriptions/:id/highlights/:proposalId',
        element: <HighlightsPage view="transcription" />,
      },
      { path: '/projects', element: <ProjectsPage view="video" /> },
      { path: '/projects/:id', element: <HighlightsPage /> },
      { path: '/projects/:id/clips/:clipId', element: <VisualEditor /> },
      { path: '/library', element: <VideoLibrary /> },
      { path: '/library/:videoId/*', element: <LibraryDetail /> },
      { path: '/hashtags', element: <HashtagsPage /> },
      { path: '/instansi', element: <InstansiPage /> },
      { path: '/settings', element: <SettingsPage /> },
      {
        path: '*',
        element: (
          <main className="page-container">
            <h1>Halaman tidak ditemukan</h1>
            <p>Alamat ini tidak tersedia.</p>
            <Link to="/" className="button primary">
              Kembali ke dashboard
            </Link>
          </main>
        ),
      },
    ],
  },
]);
createRoot(document.getElementById('root')!).render(
  <ThemeProvider>
    <ConfirmProvider>
      <RouterProvider router={router} />
    </ConfirmProvider>
  </ThemeProvider>,
);
