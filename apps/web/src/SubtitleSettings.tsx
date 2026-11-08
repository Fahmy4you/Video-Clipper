import { useEffect, useRef, useState, createContext, useContext } from 'react';
import type { Style, Caption } from './editorModel';
import { templates, motions, modernStyle, drawSubtitle } from './subtitleTemplates';
import './video-prepare.css';

type Active = {
  selected: string;
  hover: string | null;
  setSelected: (s: string) => void;
  setHover: (s: string | null) => void;
};
export const PreviewEnabled = createContext(true);
export const usePreviewScope = () => useContext(PreviewContext)!;
const PreviewContext = createContext<Active | null>(null);
export function PreviewScope({ children }: { children: React.ReactNode }) {
  const [selected, setSelected] = useState('template:sentence'),
    [hover, setHover] = useState<string | null>(null);
  return (
    <PreviewContext.Provider value={{ selected, hover, setSelected, setHover }}>
      {children}
    </PreviewContext.Provider>
  );
}
const demo: Caption = {
  id: 'demo',
  start: 0,
  end: 90,
  style: null,
  words: [
    { id: '1', text: 'Aku', start: 0, end: 18 },
    { id: '2', text: 'ingin', start: 18, end: 36 },
    { id: '3', text: 'mulai', start: 36, end: 60 },
    { id: '4', text: 'hari ini', start: 60, end: 90 },
  ],
};
function PreviewCard({
  id,
  label,
  checked,
  onSelect,
  style,
}: {
  id: string;
  label: string;
  checked: boolean;
  onSelect: () => void;
  style: Style;
}) {
  const scope = useContext(PreviewContext)!;
  const canvas = useRef<HTMLCanvasElement>(null),
    card = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false),
    [reduced, setReduced] = useState(false),
    [manual, setManual] = useState(false);
  useEffect(() => {
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(query.matches);
    change();
    query.addEventListener('change', change);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(card.current!);
    return () => {
      query.removeEventListener('change', change);
      observer.disconnect();
    };
  }, []);
  const enabled = useContext(PreviewEnabled);
  const active =
    enabled && (scope.hover || scope.selected) === id && visible && (!reduced || manual);
  const styleKey = JSON.stringify(style);
  useEffect(() => {
    const previewStyle: Style = JSON.parse(styleKey);
    let raf = 0,
      start = 0,
      ready = false,
      disposed = false;
    const draw = (frame: number) => {
      const c = canvas.current;
      if (!c) return;
      const ctx = c.getContext('2d')!;
      ctx.clearRect(0, 0, c.width, c.height);
      if (frame >= demo.end) return;
      drawSubtitle(
        ctx,
        demo,
        { ...previewStyle, x: 0.5, y: 0.5, width: 0.92, size: 68 },
        frame,
        c.width,
        c.height,
      );
    };
    const tick = (now: number) => {
      if (!ready) return;
      if (!start) start = now;
      draw((((now - start) / 1000) * 30) % 111);
      if (active && !document.hidden) raf = requestAnimationFrame(tick);
    };
    const startLoop = () => {
      cancelAnimationFrame(raf);
      start = 0;
      if (active && !document.hidden) raf = requestAnimationFrame(tick);
      else draw(48);
    };
    const visibility = () => startLoop();
    void document.fonts.load(`600 68px "${previewStyle.font}"`).then(() => {
      if (disposed) return;
      ready = true;
      startLoop();
    });
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      ready = false;
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [active, styleKey]);
  return (
    <div
      ref={card}
      className={'subtitle-card ' + (checked ? 'selected' : '')}
      onPointerEnter={(e) => {
        if (e.pointerType === 'mouse') scope.setHover(id);
      }}
      onPointerLeave={() => scope.setHover(null)}
      onFocus={() => scope.setHover(id)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) scope.setHover(null);
      }}
    >
      <label>
        <input
          type="radio"
          name={id.split(':')[0]}
          checked={checked}
          onChange={() => {
            onSelect();
            scope.setSelected(id);
            scope.setHover(null);
          }}
        />
        <span>{label}</span>
        <canvas ref={canvas} width={540} height={200} aria-hidden="true" />
      </label>
      {reduced && (
        <button
          type="button"
          className="button secondary"
          onClick={() => {
            scope.setSelected(id);
            setManual(!manual);
          }}
        >
          {manual ? 'Hentikan contoh' : 'Putar contoh'}
        </button>
      )}
    </div>
  );
}
export function SubtitleSettings({
  value,
  onChange,
}: {
  value: Style | null;
  onChange: (s: Style) => void;
}) {
  const style = value || modernStyle(),
    legacy = value && value.subtitle_version !== 1;
  const scope = useContext(PreviewContext)!;
  const previous = useRef<{
    template: Style['subtitle_template'];
    motion: Style['subtitle_motion'];
  } | null>(null);
  useEffect(() => {
    const old = previous.current;
    if (!old || old.template !== style.subtitle_template) {
      scope.setSelected('template:' + (style.subtitle_template || 'sentence'));
    } else if (old.motion !== style.subtitle_motion) {
      scope.setSelected('motion:' + (style.subtitle_motion || 'none'));
    }
    previous.current = { template: style.subtitle_template, motion: style.subtitle_motion };
  }, [style.subtitle_template, style.subtitle_motion]);

  const update = (patch: Partial<Style>) =>
    onChange({
      ...style,
      ...patch,
      subtitle_version: legacy && !patch.subtitle_template ? style.subtitle_version : 1,
    });
  return (
    <div className="subtitle-settings">
      {legacy && (
        <p className="notice">Gaya lama dipertahankan sampai Anda memilih template baru.</p>
      )}
      <fieldset>
        <legend>Template subtitle</legend>
        <div className="subtitle-grid">
          {templates.map(([id, label]) => (
            <PreviewCard
              key={id}
              id={'template:' + id}
              label={label}
              checked={!legacy && style.subtitle_template === id}
              onSelect={() => update({ subtitle_template: id })}
              style={{ ...style, subtitle_version: 1, subtitle_template: id }}
            />
          ))}
        </div>
      </fieldset>
      <div className="prepare-fields">
        <label>
          Font
          <select
            value={style.font}
            onChange={(e) => update({ font: e.target.value as Style['font'] })}
          >
            {['DejaVu Sans', 'Liberation Sans', 'Poppins'].map((f) => (
              <option key={f}>{f}</option>
            ))}
          </select>
        </label>
        <label>
          Ukuran
          <input
            type="number"
            min={12}
            max={180}
            value={style.size}
            onChange={(e) => update({ size: Math.max(12, Math.min(180, +e.target.value)) })}
          />
        </label>
        <label>
          Outline
          <input
            type="number"
            min={0}
            max={12}
            step={0.5}
            value={style.outline}
            onChange={(e) => update({ outline: Math.max(0, Math.min(12, +e.target.value)) })}
          />
        </label>
        <label>
          {style.subtitle_template === 'karaoke' || style.subtitle_template === 'karaoke_active'
            ? 'Warna awal'
            : 'Warna teks'}
          <input
            type="color"
            value={style.color}
            onChange={(e) => update({ color: e.target.value })}
          />
        </label>
        {(style.subtitle_template === 'karaoke' ||
          style.subtitle_template === 'karaoke_active') && (
          <label>
            Warna penekanan
            <input
              type="color"
              value={style.highlight}
              onChange={(e) => update({ highlight: e.target.value })}
            />
          </label>
        )}
        {style.subtitle_template === 'background' && (
          <label>
            Warna latar
            <input
              type="color"
              value={style.background || '#FACC15'}
              onChange={(e) => update({ background: e.target.value })}
            />
          </label>
        )}
      </div>
      <fieldset>
        <legend>Animasi masuk & keluar</legend>
        <div className="subtitle-grid">
          {motions.map(([id, label]) => (
            <PreviewCard
              key={id}
              id={'motion:' + id}
              label={label}
              checked={!legacy && (style.subtitle_motion || 'none') === id}
              onSelect={() => update({ subtitle_motion: id })}
              style={{ ...style, subtitle_version: 1, subtitle_motion: id }}
            />
          ))}
        </div>
      </fieldset>
    </div>
  );
}
