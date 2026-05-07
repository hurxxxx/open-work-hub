import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import { listDocsHub, type DocsHubItem } from '@/src/app-modules/docs/public-api';

interface DocPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (doc: DocsHubItem) => Promise<void> | void;
  excludeDocIds?: string[];
  workspaceSlug: string;
}

export function DocPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeDocIds = [],
  workspaceSlug,
}: DocPickerModalProps) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();
  const canAccessDocs = hasWorkspaceMembership(user, workspaceSlug);
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<DocsHubItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token || !canAccessDocs) return;
    setQuery('');
    setError(null);
    setSubmittingId(null);
    let cancelled = false;
    setLoading(true);
    listDocsHub(
      token,
      { sort_by: 'updated_at', sort_dir: 'desc', page_size: 50 },
      workspaceSlug,
    )
      .then((response) => {
        if (cancelled) return;
        setItems(response.items.filter((item) => item.source_type === 'native_doc'));
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? t('meeting.docPicker.loadFailed'));
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, canAccessDocs, workspaceSlug]);

  const excludeSet = useMemo(() => new Set(excludeDocIds), [excludeDocIds]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((item) => !excludeSet.has(item.source_id))
      .filter((item) => (q ? item.title.toLowerCase().includes(q) : true))
      .slice(0, 50);
  }, [items, query, excludeSet]);

  async function handlePick(doc: DocsHubItem) {
    setSubmittingId(doc.source_id);
    setError(null);
    try {
      await onPick(doc);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('meeting.docPicker.attachFailed'));
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t('meeting.docPicker.title')}
      description={t('meeting.docPicker.description')}
      maxWidth="max-w-xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {!canAccessDocs ? (
          <NoAccessNotice
            workspaceLabel={t('meeting.docPicker.docsWorkspace')}
            action={t('meeting.docPicker.attachAction')}
          />
        ) : null}

        {canAccessDocs && error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        {canAccessDocs ? (
          <>
            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">{t('common:actions.search')}</label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('meeting.docPicker.searchPlaceholder')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>

            <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
              {loading ? (
                <div className="flex h-24 items-center justify-center text-app-ink/40">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="px-4 py-6 text-center app-text-caption text-app-ink/50">
                  {t('meeting.docPicker.empty')}
                </div>
              ) : (
                <ul className="divide-y divide-app-border">
                  {filteredItems.map((item) => (
                    <li key={item.source_id}>
                      <button
                        type="button"
                        onClick={() => handlePick(item)}
                        disabled={submittingId !== null}
                        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                      >
                        <div className="min-w-0">
                          <p className="app-text-body line-clamp-1 text-app-ink">
                            {item.title}
                          </p>
                          <p className="app-text-caption text-app-ink/40">
                            {item.created_by_name} · {formatDateTime(item.updated_at, {
                              day: 'numeric',
                              locale: i18n.language,
                              month: 'short',
                              timeZone,
                            })}
                          </p>
                        </div>
                        {submittingId === item.source_id ? (
                          <Loader2 size={14} className="animate-spin text-app-ink/40" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
