import { useEffect, useMemo, useState } from 'react';
import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';

import {
  listReleaseNotes,
  type ReleaseNoteItem,
} from '@/src/platform/release-notes/release-notes-api';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import type { SettingsTranslator } from './settings-page-model';

export function releaseNoteLines(body: string): string[] {
  return body
    .split('\n')
    .map((line) => line.trim().replace(/^[-•]\s*/, ''))
    .filter(Boolean);
}

export function formatReleaseNoteDate(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
  }).format(date);
}

export function ReleaseNoteBody({ body }: { body: string }) {
  const lines = useMemo(() => releaseNoteLines(body), [body]);
  if (lines.length === 0) {
    return null;
  }
  return (
    <ul className="mt-4 space-y-2">
      {lines.map((line, index) => (
        <li
          key={`${index}:${line}`}
          className="app-text-body flex gap-2 text-app-ink/80"
        >
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-app-accent" />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

export function ReleaseNoteCard({
  item,
  locale,
  t,
}: {
  item: ReleaseNoteItem;
  locale: string;
  t: SettingsTranslator;
}) {
  return (
    <article className="border-b border-app-border py-5 last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="app-text-title-sm text-app-ink">{item.title}</h3>
          <p className="app-text-caption mt-1 text-app-ink/50">
            {formatReleaseNoteDate(item.published_at, locale)}
          </p>
        </div>
        {item.dismissed_at ? (
          <span className="app-text-caption rounded-full bg-app-surface-hover px-2.5 py-1 text-app-ink/50">
            {t('auth:settings.releaseNotesRead')}
          </span>
        ) : null}
      </div>
      {item.summary ? (
        <p className="app-text-body mt-3 text-app-ink/70">{item.summary}</p>
      ) : null}
      <ReleaseNoteBody body={item.body} />
    </article>
  );
}

export function ReleaseNotesSettingsSection({
  locale,
  t,
  token,
}: {
  locale: string;
  t: SettingsTranslator;
  token: string | null;
}) {
  const [items, setItems] = useState<ReleaseNoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setItems([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    listReleaseNotes(token)
      .then((response) => {
        if (!cancelled) {
          setItems(response.items);
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : t('auth:settings.releaseNotesLoadFailed'),
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t, token]);

  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.releaseNotes')}
        description={t('auth:settings.releaseNotesDescription')}
      />

      <div className="border-t border-app-border">
        {loading ? (
          <p className="app-text-body py-6 text-app-ink/50">
            {t('common:feedback.loading')}
          </p>
        ) : null}
        {error ? (
          <InlineNotice tone="danger" className="mt-4">
            {error}
          </InlineNotice>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <p className="app-text-body py-6 text-app-ink/50">
            {t('auth:settings.releaseNotesEmpty')}
          </p>
        ) : null}
        {!loading && !error
          ? items.map((item) => (
              <ReleaseNoteCard
                key={item.id}
                item={item}
                locale={locale}
                t={t}
              />
            ))
          : null}
      </div>
    </div>
  );
}
