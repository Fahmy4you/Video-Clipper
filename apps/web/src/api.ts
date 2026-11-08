export type { Word, Plan, Project, Clip } from './editorModel';
export { blankPlan } from './editorModel';
export type Job = {
  telemetry?: Record<string, number | string | null | Record<string, number>>;
  heartbeat_at?: string | null;
  queue_position?: number | null;
  next_attempt_at?: string | null;
  wait_reason?: string | null;
  connection_label?: string | null;
  queue_at?: string;
  id: string;
  project_id: string | null;
  clip_id: string | null;
  kind: string;
  status: string;
  stage: string;
  progress: number;
  error: string | null;
  payload: Record<string, unknown>;
  result: {
    successor_job_id?: string;
    resolution?: number;
    width?: number;
    height?: number;
    download_url?: string;
    local_path?: string;
    export_mode?: string;
    delivery_status?: string;
    filename?: string;
    url?: string;
    revision?: number;
    proposals?: unknown[];
  };
  created_at: string;
};
export type ModelOption = {
  id: string;
  name: string;
  status: string;
  selectable: boolean;
  stale: boolean;
  connections: { id: string; label: string; status: string; next_attempt_at: string | null }[];
};
export type ModelCatalog = {
  models: ModelOption[];
  connections: {
    id: string;
    label: string;
    refreshing: boolean;
    stale: boolean;
    fetched_at: string | null;
    next_attempt_at: string | null;
    error: string | null;
    model_count: number;
  }[];
  refreshing: boolean;
  stale: boolean;
};
export type Health = {
  router?: boolean;
  router_configured?: boolean;
  router_status?: string;
  router_error?: string | null;
  worker?: { status: string; message: string };
  gemini_error?: string | null;
  database: string;
  redis: boolean;
  ffmpeg: boolean;
  gemini: boolean;
};
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch('/api' + path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) {
    const d = data.detail;
    throw Object.assign(
      new Error(
        typeof d === 'string'
          ? d
          : Array.isArray(d)
            ? d.map((x: { msg: string }) => x.msg).join('; ')
            : 'Permintaan gagal.',
      ),
      { status: r.status },
    );
  }
  return data;
}
export function stamp(t: number) {
  return `${Math.floor(t / 60)
    .toString()
    .padStart(2, '0')}:${Math.floor(t % 60)
    .toString()
    .padStart(2, '0')}`;
}
