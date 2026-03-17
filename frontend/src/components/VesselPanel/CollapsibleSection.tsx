import { useState } from 'react';

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  testId?: string;
}

export function CollapsibleSection({
  title,
  children,
  defaultExpanded = false,
  testId,
}: CollapsibleSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="border-b border-[#1F2937]" data-testid={testId}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2"
        data-testid={testId ? `${testId}-toggle` : undefined}
      >
        <span className="text-xs text-gray-400 uppercase tracking-wide font-medium">
          {title}
        </span>
        <span className="text-gray-500 text-xs">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-2">
          {children}
        </div>
      )}
    </div>
  );
}
