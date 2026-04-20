import ReactMarkdown from 'react-markdown';
import { X } from 'lucide-react';

import type { ArtifactBuffer } from '@/src/domains/ai/agent-events';

export interface ArtifactPanelProps {
  artifact: ArtifactBuffer | null;
  onClose: () => void;
}

// Right-hand read-only document viewer. Mounted as a fixed slide-over so the
// surrounding chat layout doesn't reshuffle when opening/closing. Content is
// safe-by-default — react-markdown ignores raw HTML so the rendered output
// can't carry script tags even if the model tried to inject them.
export function ArtifactPanel({ artifact, onClose }: ArtifactPanelProps) {
  const open = artifact !== null;
  return (
    <>
      {/* Dimmed backdrop doubles as the click-to-close affordance. */}
      <div
        aria-hidden={!open}
        onClick={open ? onClose : undefined}
        className={`fixed inset-0 z-40 bg-black/10 transition-opacity ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        role="dialog"
        aria-label={artifact?.title ?? '아티팩트 패널'}
        aria-hidden={!open}
        className={`fixed right-0 top-0 z-50 flex h-full w-[min(560px,100vw)] flex-col border-l border-app-border bg-app-surface shadow-xl transition-transform ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {artifact ? (
          <>
            <header className="flex items-start justify-between gap-3 border-b border-app-border px-5 py-4">
              <div className="min-w-0 space-y-0.5">
                <div className="app-text-caption text-gray-500">
                  {artifact.type}
                </div>
                <h2 className="app-text-title-md truncate text-app-ink">
                  {artifact.title?.trim() || '(제목 없는 문서)'}
                </h2>
              </div>
              <button
                type="button"
                aria-label="패널 닫기"
                onClick={onClose}
                className="shrink-0 rounded-md p-1 text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
              >
                <X size={18} />
              </button>
            </header>
            <div className="custom-scrollbar flex-1 overflow-y-auto px-5 py-4">
              {artifact.content.trim() ? (
                <div className="app-markdown prose prose-sm max-w-none dark:prose-invert">
                  <ReactMarkdown>{artifact.content}</ReactMarkdown>
                </div>
              ) : (
                <div className="app-text-body-sm text-gray-500">
                  아직 내용이 없습니다.
                </div>
              )}
            </div>
          </>
        ) : null}
      </aside>
    </>
  );
}
