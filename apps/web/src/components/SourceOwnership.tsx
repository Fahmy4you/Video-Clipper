import { TagSelect } from './Ui';
export type Instansi = { id: string; name: string; video_count: number; project_count: number };
export function SourceOwnership({
  scope,
  instansiIds,
  instansi,
  onChange,
  disabled = false,
}: {
  scope: string;
  instansiIds: string[];
  instansi: Instansi[];
  onChange: (scope: 'global' | 'instansi', ids: string[]) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="source-ownership">
      <legend>Lingkup penggunaan</legend>
      <label>
        Lingkup video
        <select
          aria-label="Lingkup video"
          required
          disabled={disabled}
          value={scope}
          onChange={(e) => onChange(e.target.value as 'global' | 'instansi', [])}
        >
          <option value="" disabled>
            Pilih lingkup video
          </option>
          <option value="global">Global</option>
          <option value="instansi">Khusus instansi</option>
        </select>
      </label>
      {scope === 'instansi' && (
        <TagSelect
          label="Instansi pemilik"
          options={instansi.map((item) => ({ id: item.id, label: item.name }))}
          value={instansiIds}
          onChange={(ids) => onChange('instansi', ids)}
          disabled={disabled}
          prefix=""
          noun="instansi"
          max={100}
          showAllSelected
        />
      )}
      <p className="field-help">
        {scope === 'global'
          ? 'Video ini boleh menjadi sumber Global untuk semua proyek.'
          : 'Pilih satu atau beberapa instansi yang terkait dengan video. Mix dapat memakai video ini jika salah satunya dipilih sebagai sumber.'}
      </p>
    </fieldset>
  );
}
