import { useState, useRef, useEffect, createContext, useContext, type ReactNode } from 'react';

const MenuCloseContext = createContext<(() => void) | null>(null);

/** Hook for children to close their parent MenuDropdown. */
export function useMenuClose() {
  return useContext(MenuCloseContext);
}

interface MenuDropdownProps {
  label: string;
  icon: 'filter' | 'layers' | 'tools';
  children: ReactNode;
  countBadge?: number;
}

const ICONS: Record<string, ReactNode> = {
  filter: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />
    </svg>
  ),
  layers: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  ),
  tools: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  ),
};

export function MenuDropdown({ label, icon, children, countBadge }: MenuDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const close = () => setOpen(false);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <MenuCloseContext.Provider value={close}>
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen(!open)}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded text-xs transition-colors ${
            open
              ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
              : 'bg-[#0A0E17]/80 text-slate-400 hover:text-white hover:bg-[#111827]/90 border border-[#1F2937]'
          }`}
        >
          {ICONS[icon]}
          <span className="font-medium">{label}</span>
          {countBadge != null && countBadge > 0 && (
            <span className="px-1 py-0.5 rounded text-[0.55rem] font-mono bg-blue-500/20 text-blue-400 leading-none">
              {countBadge}
            </span>
          )}
        </button>
        {open && (
          <div
            className="absolute top-full left-0 mt-1 min-w-[220px] rounded-lg border border-slate-700/50 shadow-xl overflow-hidden"
            style={{ backgroundColor: 'rgba(10, 14, 23, 0.95)' }}
          >
            {children}
          </div>
        )}
      </div>
    </MenuCloseContext.Provider>
  );
}
