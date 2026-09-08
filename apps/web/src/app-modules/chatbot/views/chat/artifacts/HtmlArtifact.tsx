import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CodeArtifact } from './CodeArtifact';

type Tab = 'preview' | 'source';

export interface HtmlArtifactProps {
  content: string;
  title?: string | null;
}

// HTML artifact renderer with Preview ↔ Source tabs, matching the pattern
// set by Claude Artifacts / ChatGPT Canvas. The preview runs in a sandboxed
// iframe so the page's scripts execute (needed for any interactive demo)
// without `allow-same-origin` — that combination prevents the guest from
// reading the parent's cookies, localStorage, or DOM even if it tries.
export function HtmlArtifact({ content, title }: HtmlArtifactProps) {
  const { t } = useTranslation('apps');
  const [tab, setTab] = useState<Tab>('preview');

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
          <iframe
            title={title ?? t('ai.htmlArtifact.title')}
            srcDoc={content}
            // `allow-scripts` lets the guest page run its own JS (needed
            // for any interactive HTML). We intentionally do NOT include
            // `allow-same-origin` — without it the iframe runs in a
            // unique null origin with no access to parent cookies /
            // localStorage / DOM, so even a hostile `<script>` inside
            // the artifact can't escalate to the authenticated session.
            sandbox="allow-scripts"
            className="h-full w-full rounded-md border border-app-border bg-white"
          />
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
