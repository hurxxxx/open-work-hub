import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Download, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from '@open-work-hub/ui';
import 'highlight.js/styles/github.css';

import { DocumentArtifact } from '@/src/components/artifacts/DocumentArtifact';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import type { ArtifactBuffer } from '../../api/agent-events';
import type { ChatbotArtifactRenderer } from '../chatbot-experience';

import { CodeArtifact } from './artifacts/CodeArtifact';
import { HtmlArtifact } from './artifacts/HtmlArtifact';
import { SvgArtifact } from './artifacts/SvgArtifact';
import { artifactDownloadSpec } from './artifacts/artifact-download';

export interface ArtifactPanelProps {
  artifact: ArtifactBuffer | null;
  artifacts?: readonly ArtifactBuffer[];
  renderers?: readonly ChatbotArtifactRenderer[];
  onClose: () => void;
}

// Right-hand read-only artifact viewer. Mounted as a fixed slide-over so the
// surrounding chat layout doesn't reshuffle when opening/closing. The body
// is dispatched by `artifact.type` into one of four renderers: markdown
// document / HTML preview + source / code with syntax highlight / SVG. The
// panel always opens at the wide layout — rendered HTML, long code, and
// data tables all need the room, and a maximize toggle was just friction
// for no real gain since nothing displayed well at 560px anyway.
export function ArtifactPanel({
  artifact,
  artifacts = [],
  renderers = [],
  onClose,
}: ArtifactPanelProps) {
  const { t } = useTranslation('apps');
  const open = artifact !== null;
  const [copied, setCopied] = useState(false);
  const downloadSpec = useMemo(
    () => (artifact ? artifactDownloadSpec(artifact) : null),
    [artifact],
  );
  const hasCustomRenderer = Boolean(
    artifact && renderers.some((renderer) => renderer.type === artifact.type),
  );

  useEffect(() => {
    setCopied(false);
  }, [artifact?.id, artifact?.content]);

  const handleCopyArtifact = async () => {
    if (!artifact?.content) {
      return;
    }
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const handleDownloadArtifact = () => {
    if (!artifact?.content || !downloadSpec || artifact.status === 'open') {
      return;
    }
    downloadBlobAsFile(
      new Blob([artifact.content], { type: downloadSpec.mimeType }),
      downloadSpec.filename,
    );
  };

  return (
    <>
      {/* Dimmed backdrop doubles as the click-to-close affordance. */}
      <button
        type="button"
        aria-label={t('ai.artifacts.closePanel')}
        onClick={open ? onClose : undefined}
        disabled={!open}
        className={`fixed inset-0 z-40 appearance-none border-0 bg-black/10 p-0 transition-opacity ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <dialog
        open={open}
        aria-label={artifact?.title ?? t('ai.artifacts.panel')}
        aria-hidden={!open}
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        className={`m-0 max-h-none max-w-none fixed right-0 top-0 z-50 flex h-full w-[min(1200px,96vw)] flex-col border-l border-app-border bg-app-surface p-0 shadow-xl transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {artifact ? (
          <>
            <header className="flex items-start justify-between gap-3 border-b border-app-border px-5 py-4">
              <div className="min-w-0 space-y-0.5">
                <div className="app-text-caption text-app-ink/55">
                  {artifact.type}
                  {artifact.language ? ` · ${artifact.language}` : ''}
                </div>
                <h2 className="app-text-title-md truncate text-app-ink">
                  {artifact.title?.trim() || t('ai.artifacts.untitledDocument')}
                </h2>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <ArtifactActionButton
                  label={
                    copied
                      ? t('ai.artifacts.copied')
                      : t('ai.artifacts.copyContent')
                  }
                  disabled={!artifact.content.trim()}
                  onClick={() => void handleCopyArtifact()}
                  icon={copied ? Check : Copy}
                />
                <ArtifactActionButton
                  label={artifactDownloadLabel(artifact.type, t)}
                  disabled={
                    !artifact.content.trim() || artifact.status === 'open'
                  }
                  onClick={handleDownloadArtifact}
                  icon={Download}
                />
                <ArtifactActionButton
                  label={t('ai.artifacts.closePanel')}
                  onClick={onClose}
                  icon={X}
                />
              </div>
            </header>
            <div className="custom-scrollbar flex-1 overflow-y-auto px-5 py-4">
              {artifact.content.trim() || hasCustomRenderer ? (
                <ArtifactBody
                  artifact={artifact}
                  artifacts={artifacts}
                  renderers={renderers}
                  svgAriaLabel={t('ai.artifacts.svgAriaLabel')}
                />
              ) : (
                <div className="app-text-body-sm text-app-ink/55">
                  {t('ai.artifacts.empty')}
                </div>
              )}
            </div>
          </>
        ) : null}
      </dialog>
    </>
  );
}

function ArtifactActionButton({
  disabled = false,
  icon: Icon,
  label,
  onClick,
}: {
  disabled?: boolean;
  icon: typeof Copy;
  label: string;
  onClick: () => void;
}) {
  return (
    <Tooltip content={label}>
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        className="flex size-8 items-center justify-center rounded-md text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-app-ink/55"
      >
        <Icon size={16} />
      </button>
    </Tooltip>
  );
}

function artifactDownloadLabel(
  type: string,
  t: (key: string) => string,
): string {
  switch (type) {
    case 'html':
      return t('ai.artifacts.downloadHtml');
    case 'code':
      return t('ai.artifacts.downloadCode');
    case 'svg':
      return t('ai.artifacts.downloadSvg');
    case 'document':
      return t('ai.artifacts.downloadMarkdown');
    default:
      return t('ai.artifacts.downloadContent');
  }
}

function ArtifactBody({
  artifact,
  artifacts,
  renderers,
  svgAriaLabel,
}: {
  artifact: ArtifactBuffer;
  artifacts: readonly ArtifactBuffer[];
  renderers: readonly ChatbotArtifactRenderer[];
  svgAriaLabel: string;
}) {
  const customRenderer = renderers.find(
    (renderer) => renderer.type === artifact.type,
  );
  if (customRenderer) {
    return customRenderer.render(artifact, {
      relatedArtifacts: resolveRelatedArtifacts(artifact, artifacts),
    });
  }

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
      return (
        <SvgArtifact content={artifact.content} ariaLabel={svgAriaLabel} />
      );
    case 'document':
    default:
      // Unknown/future types fall back to the document renderer —
      // markdown tolerates arbitrary content gracefully, and that keeps
      // the client forward-compatible with server-side type expansions
      // (mermaid, react, etc.) without a hard crash in the meantime.
      return <DocumentArtifact content={artifact.content} />;
  }
}

function resolveRelatedArtifacts(
  artifact: ArtifactBuffer,
  artifacts: readonly ArtifactBuffer[],
): ArtifactBuffer[] {
  if (artifact.graphRunId || artifact.conversationTurnId) {
    return artifacts.filter(
      (candidate) =>
        (Boolean(artifact.graphRunId) &&
          candidate.graphRunId === artifact.graphRunId) ||
        (Boolean(artifact.conversationTurnId) &&
          candidate.conversationTurnId === artifact.conversationTurnId),
    );
  }
  return [...artifacts];
}
