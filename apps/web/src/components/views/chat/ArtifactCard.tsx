import { FileText, Loader2 } from 'lucide-react';

import type { ArtifactBuffer } from '@/src/domains/ai/agent-events';
import { cn } from '@/src/lib/utils';

export interface ArtifactCardProps {
  artifact: ArtifactBuffer;
  isActive: boolean;
  onOpen: (artifactId: string) => void;
}

// Small inline summary card rendered below a chat bubble. Mirrors the
// ToolCallCard layout so the two types feel consistent when a turn has both.
// Clicking routes to the artifact panel — the full body never lives in the
// chat flow itself.
export function ArtifactCard({ artifact, isActive, onOpen }: ArtifactCardProps) {
  const streaming = artifact.status === 'open';
  const label = artifact.title?.trim() || '(제목 없는 문서)';
  const preview = buildPreview(artifact.content);

  return (
    <button
      type="button"
      onClick={() => onOpen(artifact.id)}
      className={cn(
        'mt-2 flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left transition-colors',
        isActive
          ? 'border-app-accent bg-app-bg'
          : 'border-app-border bg-app-surface hover:border-app-accent',
      )}
      aria-pressed={isActive}
      data-testid={`artifact-card-${artifact.id}`}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
        {streaming ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <FileText size={14} />
        )}
      </div>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="app-text-control-sm truncate text-app-ink">{label}</div>
        <div className="app-text-micro truncate text-gray-500">
          {streaming
            ? '생성 중…'
            : preview || `${artifact.type} · ${artifact.content.length}자`}
        </div>
      </div>
      <div className="app-text-micro shrink-0 self-center text-gray-500">
        {isActive ? '열림' : '열기'}
      </div>
    </button>
  );
}

function buildPreview(content: string): string {
  // First non-empty line, trimmed; keeps the card compact without leaking
  // markdown formatting characters into the tiny subtitle slot.
  const trimmed = content.trim();
  if (!trimmed) {
    return '';
  }
  const firstLine = trimmed.split('\n').find((line) => line.trim().length > 0) ?? '';
  const cleaned = firstLine.replace(/^[#>\-*`\s]+/, '').trim();
  return cleaned.length > 80 ? `${cleaned.slice(0, 80)}…` : cleaned;
}
