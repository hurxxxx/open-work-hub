import { X } from 'lucide-react';
import 'highlight.js/styles/github.css';

import type { ArtifactBuffer } from '@/src/domains/ai/agent-events';

import {
  CodeArtifact,
  DocumentArtifact,
  HtmlArtifact,
  SvgArtifact,
} from './artifacts';

export interface ArtifactPanelProps {
  artifact: ArtifactBuffer | null;
  onClose: () => void;
}

// Right-hand read-only artifact viewer. Mounted as a fixed slide-over so the
// surrounding chat layout doesn't reshuffle when opening/closing. The body
// is dispatched by `artifact.type` into one of four renderers: markdown
// document / HTML preview + source / code with syntax highlight / SVG. The
// panel always opens at the wide layout — rendered HTML, long code, and
// data tables all need the room, and a maximize toggle was just friction
// for no real gain since nothing displayed well at 560px anyway.
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
        className={`fixed right-0 top-0 z-50 flex h-full w-[min(1200px,96vw)] flex-col border-l border-app-border bg-app-surface shadow-xl transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {artifact ? (
          <>
            <header className="flex items-start justify-between gap-3 border-b border-app-border px-5 py-4">
              <div className="min-w-0 space-y-0.5">
                <div className="app-text-caption text-gray-500">
                  {artifact.type}
                  {artifact.language ? ` · ${artifact.language}` : ''}
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
                <ArtifactBody artifact={artifact} />
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

function ArtifactBody({ artifact }: { artifact: ArtifactBuffer }) {
  switch (artifact.type) {
    case 'html':
      return (
        <HtmlArtifact
          key={artifact.id}
          content={artifact.content}
          title={artifact.title}
        />
      );
    case 'code':
      return (
        <CodeArtifact
          content={artifact.content}
          language={artifact.language ?? null}
        />
      );
    case 'svg':
      return <SvgArtifact content={artifact.content} />;
    case 'document':
    default:
      // Unknown/future types fall back to the document renderer —
      // markdown tolerates arbitrary content gracefully, and that keeps
      // the client forward-compatible with server-side type expansions
      // (mermaid, react, etc.) without a hard crash in the meantime.
      return <DocumentArtifact content={artifact.content} />;
  }
}
