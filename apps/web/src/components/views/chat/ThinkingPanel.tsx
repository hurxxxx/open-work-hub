import { useState } from 'react';
import { Brain, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';

import type { ChatStreamStatus } from '@/src/domains/ai/agent-events';

export interface ThinkingPanelProps {
  reasoning: string;
  status: ChatStreamStatus;
}

function labelFor(status: ChatStreamStatus): string {
  switch (status) {
    case 'streaming':
      return '생각 중…';
    case 'error':
      return '생각 실패';
    case 'cancelled':
    case 'done':
      return '생각 완료';
    default:
      return '생각';
  }
}

export function ThinkingPanel({ reasoning, status }: ThinkingPanelProps) {
  const [open, setOpen] = useState(false);
  if (!reasoning) {
    return null;
  }
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-app-border bg-app-bg">
      <button
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left app-text-micro text-gray-500 transition-colors hover:text-app-ink"
        onClick={() => setOpen((prev) => !prev)}
        type="button"
      >
        <span className="flex items-center gap-2">
          {status === 'streaming' ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Brain size={12} />
          )}
          <span>{labelFor(status)}</span>
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <pre className="m-0 max-h-60 overflow-y-auto whitespace-pre-wrap break-words border-t border-app-border px-3 py-2 font-mono text-xs text-gray-600 dark:text-gray-300">
          {reasoning}
        </pre>
      )}
    </div>
  );
}
