import { useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2, Square } from 'lucide-react';
import { useToast } from '@ai-do/ui/providers/toast-provider';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  addCancellingBackgroundWorkKey,
  backgroundWorkItemKey,
  buildBackgroundWorkSessionSnapshot,
  mergeBackgroundWorkSourceListResults,
  removeCancellingBackgroundWorkKey,
  resolveBackgroundWorkCadence,
  selectActiveBackgroundWorkItems,
} from './background-work-session';
import type {
  BackgroundWorkItem,
  BackgroundWorkSource,
  BackgroundWorkStatus,
  BackgroundWorkToastEvent,
} from './background-work-session';

export type { BackgroundWorkItem, BackgroundWorkSource, BackgroundWorkStatus };

function publishBackgroundWorkToast(
  event: BackgroundWorkToastEvent,
  {
    t,
    toast,
  }: {
    t: TFunction;
    toast: ReturnType<typeof useToast>;
  },
) {
  if (event.type === 'completed') {
    toast.success(
      t('shell:backgroundWork.completedTitle'),
      t('shell:backgroundWork.completedDescription', { title: event.item.title }),
    );
  } else if (event.type === 'failed') {
    toast.error(
      t('shell:backgroundWork.failedTitle'),
      event.item.description ||
        t('shell:backgroundWork.failedDescription', { title: event.item.title }),
    );
  } else {
    toast.info(
      t('shell:backgroundWork.cancelledTitle'),
      t('shell:backgroundWork.cancelledDescription', { title: event.item.title }),
    );
  }
}

export function BackgroundWorkProvider({
  sources,
  workspaceSlug,
}: {
  sources: readonly BackgroundWorkSource[];
  workspaceSlug: string | null;
}) {
  const { token } = useAuth();
  const { t } = useTranslation(['shell', 'apps']);
  const toast = useToast();
  const navigate = useNavigate();
  const [items, setItems] = useState<BackgroundWorkItem[]>([]);
  const [cancellingKeys, setCancellingKeys] = useState<Set<string>>(() => new Set());
  const previousStatuses =
    useRef<Map<string, BackgroundWorkStatus> | null>(null);
  const previousItemsBySource =
    useRef<Map<string, BackgroundWorkItem[]> | null>(null);
  if (previousStatuses.current === null) {
    previousStatuses.current = new Map();
  }
  if (previousItemsBySource.current === null) {
    previousItemsBySource.current = new Map();
  }
  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources],
  );
  const cadence = useMemo(() => resolveBackgroundWorkCadence(sources), [sources]);
  const canSync = Boolean(token && workspaceSlug && sources.length > 0);

  useEffect(() => {
    if (!token || !workspaceSlug || sources.length === 0) {
      previousStatuses.current?.clear();
      previousItemsBySource.current?.clear();
      setItems([]);
      return;
    }

    let active = true;
    let timeoutId: number | null = null;
    const activeToken = token;
    const activeWorkspaceSlug = workspaceSlug;

    function scheduleNext(delayMs: number) {
      if (!active) return;
      timeoutId = window.setTimeout(() => {
        void sync();
      }, delayMs);
    }

    async function sync() {
      const settled = await Promise.allSettled(
        sources.map((source) =>
          source.list({
            token: activeToken,
            workspaceSlug: activeWorkspaceSlug,
            t,
          }),
        ),
      );
      if (!active) return;
      const sourceItems = mergeBackgroundWorkSourceListResults({
        previousItemsBySource: previousItemsBySource.current ?? new Map(),
        settled,
        sources,
      });
      const snapshot = buildBackgroundWorkSessionSnapshot({
        items: sourceItems.items,
        previousStatuses: previousStatuses.current ?? new Map(),
        cadence,
      });
      for (const event of snapshot.toastEvents) {
        publishBackgroundWorkToast(event, { t, toast });
      }
      previousItemsBySource.current = sourceItems.itemsBySource;
      previousStatuses.current = snapshot.nextStatuses;
      setItems(snapshot.items);
      scheduleNext(snapshot.nextPollDelayMs);
    }

    void sync();

    return () => {
      active = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [cadence, sources, t, toast, token, workspaceSlug]);

  const activeItems = canSync ? selectActiveBackgroundWorkItems(items) : [];

  async function cancelItem(item: BackgroundWorkItem) {
    if (!token || !workspaceSlug) return;
    const source = sourceById.get(item.sourceId);
    if (!source?.cancel) return;
    setCancellingKeys((current) => addCancellingBackgroundWorkKey(current, item));
    try {
      await source.cancel({ token, workspaceSlug, item });
    } finally {
      setCancellingKeys((current) => removeCancellingBackgroundWorkKey(current, item));
    }
  }

  if (activeItems.length === 0) return null;

  return (
    <section
      aria-label={t('shell:backgroundWork.regionLabel')}
      className="fixed bottom-24 right-4 z-[70] w-[min(380px,calc(100vw-2rem))] rounded-lg border border-app-border bg-app-bg shadow-2xl"
    >
      <header className="flex items-center justify-between border-b border-app-border px-3 py-2">
        <h2 className="app-text-control-sm font-semibold text-app-ink">
          {t('shell:backgroundWork.title')}
        </h2>
        <span className="app-text-micro rounded-full bg-app-surface px-2 py-1 text-app-ink/55">
          {activeItems.length}
        </span>
      </header>
      <div className="max-h-72 overflow-y-auto">
        {activeItems.map((item) => {
          const key = backgroundWorkItemKey(item);
          const cancelling = cancellingKeys.has(key);
          return (
            <div key={key} className="flex items-start gap-2 border-b border-app-border p-3 last:border-b-0">
              <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin text-app-accent" />
              <button
                type="button"
                onClick={() => {
                  if (item.href) navigate(item.href);
                }}
                className="min-w-0 flex-1 text-left"
                disabled={!item.href}
              >
                <p className="app-text-body-sm truncate font-medium text-app-ink">
                  {item.title}
                </p>
                <p className="app-text-caption mt-0.5 truncate text-app-ink/55">
                  {item.description || t(`shell:backgroundWork.status.${item.status}`)}
                </p>
              </button>
              {item.href ? (
                <button
                  type="button"
                  onClick={() => navigate(item.href || '/')}
                  className="mt-0.5 rounded-md p-1.5 text-app-ink/45 hover:bg-app-surface-hover hover:text-app-ink"
                  aria-label={t('shell:backgroundWork.openAction')}
                >
                  <ExternalLink size={14} />
                </button>
              ) : null}
              {item.cancellable ? (
                <button
                  type="button"
                  onClick={() => void cancelItem(item)}
                  disabled={cancelling}
                  className="mt-0.5 rounded-md p-1.5 text-app-ink/45 hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-60"
                  aria-label={t('shell:backgroundWork.cancelAction')}
                >
                  {cancelling ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Square size={14} />
                  )}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
