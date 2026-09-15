import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CodeArtifact } from './CodeArtifact';
import { htmlPreviewDocument } from './html-preview-document';

type Tab = 'preview' | 'source';

export interface HtmlArtifactProps {
  content: string;
  title?: string | null;
  previewContent?: string | null;
  previewError?: boolean;
}

// HTML artifact renderer with Preview ↔ Source tabs, matching the pattern
// set by Claude Artifacts / ChatGPT Canvas. The preview runs in a sandboxed
// iframe so the page's scripts execute (needed for any interactive demo)
// without `allow-same-origin` — that combination prevents the guest from
// reading the parent's cookies, localStorage, or DOM even if it tries.
export function HtmlArtifact({
  content,
  title,
  previewContent,
  previewError,
}: HtmlArtifactProps) {
  const { t } = useTranslation('apps');
  const [tab, setTab] = useState<Tab>('preview');
  const [runtimeError, setRuntimeError] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const html = previewContent === undefined ? content : previewContent;
  // Remote HTTP development origins lack randomUUID, but getRandomValues
  // remains available. Keep a fresh unpredictable channel per preview version.
  const channel = useMemo(
    () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join(''),
    [html],
  );
  useEffect(() => {
    setRuntimeError(false);
    const onMessage = (event: MessageEvent) => {
      if (
        event.source === frame.current?.contentWindow &&
        event.data?.channel === channel &&
        event.data?.type === 'preview-error'
      )
        setRuntimeError(true);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [channel]);
  const previewTitle = title ?? t('ai.htmlArtifact.title');
  const document = useMemo(
    () =>
      html === null
        ? undefined
        : htmlPreviewDocument(html, channel, previewTitle),
    [html, channel, previewTitle],
  );

  return (
    <div className="flex h-full flex-col">
      <div
        role="tablist"
        aria-label={t('ai.htmlArtifact.tabList')}
        className="mb-3 inline-flex shrink-0 self-start rounded-md border border-app-border bg-app-surface p-0.5"
      >
        <TabButton
          label={t('ai.htmlArtifact.preview')}
          active={tab === 'preview'}
          onClick={() => setTab('preview')}
        />
        <TabButton
          label={t('ai.htmlArtifact.source')}
          active={tab === 'source'}
          onClick={() => setTab('source')}
        />
      </div>
      <div className="min-h-0 flex-1">
        {tab === 'preview' ? (
          <div className="flex h-full flex-col">
            {previewError || runtimeError ? (
              <p
                role="status"
                className="mb-2 app-text-body-sm text-app-ink-muted"
              >
                {t('ai.htmlArtifact.previewFailed')}
              </p>
            ) : null}
            {html === null && !previewError ? (
              <p role="status">{t('hermesWorkspace.loading')}</p>
            ) : null}
            {html !== null ? (
              <iframe
                ref={frame}
                title={previewTitle}
                srcDoc={document}
                referrerPolicy="no-referrer"
                // `allow-scripts` lets the guest page run its own JS (needed
                // for any interactive HTML). We intentionally do NOT include
                // `allow-same-origin` — without it the iframe runs in a
                // unique null origin with no access to parent cookies /
                // localStorage / DOM, so even a hostile `<script>` inside
                // the artifact can't escalate to the authenticated session.
                sandbox="allow-scripts"
                className="h-full w-full rounded-md border border-app-border bg-white"
              />
            ) : null}
          </div>
        ) : (
          <CodeArtifact content={content} language="html" />
        )}
      </div>
    </div>
  );
}

interface TabButtonProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

function TabButton({ label, active, onClick }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={
        active
          ? 'rounded px-3 py-1 text-sm font-medium bg-app-accent text-app-accent-fg'
          : 'rounded px-3 py-1 text-sm font-medium text-app-ink-muted hover:text-app-ink'
      }
    >
      {label}
    </button>
  );
}
