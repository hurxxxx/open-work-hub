import { useState } from 'react';
import { Brain, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ChatStreamStatus } from '../../api/agent-events';

export interface ThinkingPanelProps {
  reasoning: string;
  status: ChatStreamStatus;
}

function labelFor(status: ChatStreamStatus, t: (key: string) => string): string {
  switch (status) {
    case 'streaming':
      return t('ai.thinking.streaming');
    case 'error':
      return t('ai.thinking.error');
    case 'cancelled':
      return t('ai.thinking.cancelled');
    case 'done':
      return t('ai.thinking.done');
    default:
      return t('ai.thinking.idle');
  }
}

export function ThinkingPanel({ reasoning, status }: ThinkingPanelProps) {
  const { t } = useTranslation('apps');
  const [open, setOpen] = useState(false);
  if (!reasoning) {
    return null;
  }
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-app-border bg-app-bg">
      <button
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left app-text-micro text-app-ink/55 transition-colors hover:text-app-ink"
        onClick={() => setOpen((prev) => !prev)}
        type="button"
      >
        <span className="flex items-center gap-2">
          {status === 'streaming' ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Brain size={12} />
          )}
          <span>{labelFor(status, t)}</span>
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <pre className="m-0 max-h-60 overflow-y-auto whitespace-pre-wrap break-words border-t border-app-border px-3 py-2 font-mono text-xs text-app-ink/70 dark:text-app-ink/80">
          {reasoning}
        </pre>
      )}
    </div>
  );
}
