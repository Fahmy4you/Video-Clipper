import { useEffect, useId, useState, type ReactNode } from 'react';
import { ChevronRight, ChevronDown } from 'lucide-react';
import { PreviewEnabled } from './SubtitleSettings';

export function PrepareAccordion({
  title,
  summary,
  disabled = false,
  children,
}: {
  title: string;
  summary: string;
  disabled?: boolean;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const [mounted, setMounted] = useState(false);
  const id = useId();
  const open = expanded && !disabled;
  useEffect(() => {
    if (disabled) setExpanded(false);
    if (open) {
      setMounted(true);
      return;
    }
    const timer = window.setTimeout(() => setMounted(false), 220);
    return () => clearTimeout(timer);
  }, [open, disabled]);
  return (
    <section className={'panel prepare-accordion' + (disabled ? ' is-disabled' : '')}>
      <button
        type="button"
        className="prepare-accordion-heading"
        disabled={disabled}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => {
          setMounted(true);
          setExpanded(!open);
        }}
      >
        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        <strong>{title}</strong>
        <span>{summary}</span>
      </button>
      <div
        id={id}
        className={'prepare-collapse' + (open ? ' is-open' : '')}
        inert={!open}
        aria-hidden={!open}
      >
        <div>
          <div className="prepare-accordion-body">
            <PreviewEnabled value={open}>{mounted && children}</PreviewEnabled>
          </div>
        </div>
      </div>
    </section>
  );
}
