import type { VideoAsset } from './editorModel';
import { compareNames } from './listFilters';

export type BrollOption = { id: string; label: string };
export const GLOBAL_SOURCE = 'scope:global';

export function brollOptions(assets: VideoAsset[], owners: { id: string; name: string }[] = []) {
  const hashtags = new Map<string, string>();
  const instansi = new Map<string, string>([[GLOBAL_SOURCE, 'Global']]);
  for (const a of assets) {
    a.hashtag_ids.forEach((id, i) => hashtags.set(id, a.hashtags[i] || id));
    a.instansi_ids.forEach((id) => {
      const owner = owners.find((o) => o.id === id);
      if (owner) instansi.set(id, owner.name);
    });
  }
  const options = (map: Map<string, string>) =>
    [...map].map(([id, label]) => ({ id, label })).sort((a, b) => compareNames(a.label, b.label));
  return { hashtags: options(hashtags), instansi: options(instansi) };
}

export function matchesBroll(a: VideoAsset, query: string, tags: string[], owners: string[]) {
  const text = [a.title, a.explain, ...a.hashtags.map((t) => '#' + t)].join(' ').toLowerCase();
  return (
    text.includes(query.trim().toLowerCase()) &&
    (!tags.length || tags.some((id) => a.hashtag_ids.includes(id))) &&
    (!owners.length ||
      owners.some((id) =>
        id === GLOBAL_SOURCE
          ? a.scope === 'global'
          : a.scope === 'instansi' && a.instansi_ids.includes(id),
      ))
  );
}
