import { useEffect, useId, useRef, useState } from 'react';
import { Filter, Search } from 'lucide-react';
import type { BrollOption } from './brollFilters';

export function BrollFilter({
  label,
  options,
  value,
  onChange,
  open,
  onOpen,
}: {
  label: string;
  options: BrollOption[];
  value: string[];
  onChange: (value: string[]) => void;
  open: boolean;
  onOpen: (open: boolean) => void;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  useEffect(() => {
    if (!open) return;
    const node = panel.current!;
    function position() {
      const rect = trigger.current!.getBoundingClientRect();
      const width = Math.min(340, window.innerWidth - 32);
      node.style.width = width + 'px';
      node.style.left = Math.max(16, Math.min(rect.left, window.innerWidth - width - 16)) + 'px';
      node.style.top = Math.min(rect.bottom + 8, window.innerHeight - 220) + 'px';
      node.style.maxHeight =
        Math.max(180, window.innerHeight - parseFloat(node.style.top) - 16) + 'px';
    }
    node.showPopover();
    position();
    node.querySelector('input')?.focus();
    function outside(e: PointerEvent) {
      if (!node.contains(e.target as Node) && !trigger.current?.contains(e.target as Node))
        onOpen(false);
    }
    function escape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape, true);
    window.addEventListener('resize', position);
    return () => {
      node.hidePopover();
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape, true);
      window.removeEventListener('resize', position);
    };
  }, [open, onOpen]);
  const matches = options.filter((o) =>
    o.label.toLowerCase().includes(query.trim().replace(/^#/, '').toLowerCase()),
  );
  return (
    <div className="broll-filter">
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        className={value.length ? 'is-active' : ''}
        onClick={() => {
          setQuery('');
          onOpen(!open);
        }}
      >
        <Filter size={16} />
        {label}
        {value.length > 0 && <span>· {value.length}</span>}
      </button>
      {open && (
        <div
          ref={panel}
          id={id}
          popover="manual"
          className="broll-filter-panel"
          role="group"
          aria-label={'Filter ' + label}
        >
          <div className="broll-filter-search">
            <Search size={16} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label={'Cari ' + label.toLowerCase()}
              placeholder={'Cari ' + label.toLowerCase() + '…'}
            />
          </div>
          <div className="broll-filter-options">
            {matches.map((o) => (
              <label key={o.id}>
                <input
                  type="checkbox"
                  checked={value.includes(o.id)}
                  onChange={() =>
                    onChange(
                      value.includes(o.id) ? value.filter((id) => id !== o.id) : [...value, o.id],
                    )
                  }
                />
                <span>
                  {label === 'Hashtag' ? '#' : ''}
                  {o.label}
                </span>
              </label>
            ))}
            {!matches.length && <p>Tidak ada {label.toLowerCase()} yang cocok.</p>}
          </div>
          <div className="broll-filter-footer">
            <span>{value.length} dipilih</span>
            <button type="button" disabled={!value.length} onClick={() => onChange([])}>
              Bersihkan pilihan
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
