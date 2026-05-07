import { useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ExternalLink, Loader2, Square } from 'lucide-react';
import { useToast } from '@ai-do/ui/providers/toast-provider';

import { useAuth } from '@/src/platform/auth/auth-provider';

export type BackgroundWorkStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface BackgroundWorkItem {
  id: string;
  sourceId: string;
  kind: string;
  title: string;
  description?: string;
  status: BackgroundWorkStatus;
  href?: string;
  cancellable?: boolean;
  updatedAt: string;
}

export interface BackgroundWorkSource {
  id: string;
  pollIntervalMs?: number;
  list: (context: {
    token: string;
    workspaceSlug: string;
    t: TFunction;
  }) => Promise<BackgroundWorkItem[]>;
  cancel?: (context: {
    token: string;
    workspaceSlug: string;
    item: BackgroundWorkItem;
  }) => Promise<void>;
}

function isActiveStatus(status: BackgroundWorkStatus): boolean {
  return status === 'queued' || status === 'running';
}

function itemKey(item: BackgroundWorkItem): string {
  return `${item.sourceId}:${item.id}`;
}

export function BackgroundWorkProvider({
  sources,
  workspaceSlug,
}: {
  sources: BackgroundWorkSource[];
  workspaceSlug: string | null;
}) {
  const { token } = useAuth();
  const { t } = useTranslation(['shell', 'apps']);
  const toast = useToast();
  const navigate = useNavigate();
  const [items, setItems] = useState<BackgroundWorkItem[]>([]);
  const [cancellingKeys, setCancellingKeys] = useState<Set<string>>(() => new Set());
  const previousStatuses = useRef<Map<string, BackgroundWorkStatus>>(new Map());
  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources],
  );
  const pollIntervalMs = useMemo(
    () => Math.min(...sources.map((source) => source.pollIntervalMs ?? 5000), 5000),
    [sources],
  );

  useEffect(() => {
    if (!token || !workspaceSlug || sources.length === 0) {
      setItems([]);
      previousStatuses.current.clear();
      return;
    }

    let active = true;
    const activeToken = token;
    const activeWorkspaceSlug = workspaceSlug;

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
      const nextItems = settled.flatMap((result) =>
        result.status === 'fulfilled' ? result.value : [],
      );
      const nextStatuses = new Map<string, BackgroundWorkStatus>();
      for (const item of nextItems) {
        const key = itemKey(item);
        const previous = previousStatuses.current.get(key);
        if (previous && isActiveStatus(previous) && !isActiveStatus(item.status)) {
          if (item.status === 'succeeded') {
            toast.success(
              t('shell:backgroundWork.completedTitle'),
              t('shell:backgroundWork.completedDescription', { title: item.title }),
            );
          } else if (item.status === 'failed') {
            toast.error(
              t('shell:backgroundWork.failedTitle'),
              item.description || t('shell:backgroundWork.failedDescription', { title: item.title }),
            );
          } else if (item.status === 'cancelled') {
            toast.info(
              t('shell:backgroundWork.cancelledTitle'),
              t('shell:backgroundWork.cancelledDescription', { title: item.title }),
            );
          }
        }
        nextStatuses.set(key, item.status);
      }
      previousStatuses.current = nextStatuses;
      setItems(nextItems);
    }

    void sync();
    const interval = window.setInterval(() => {
      void sync();
    }, pollIntervalMs);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [pollIntervalMs, sources, t, toast, token, workspaceSlug]);

  const activeItems = items
    .filter((item) => isActiveStatus(item.status))
    .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime());

  async function cancelItem(item: BackgroundWorkItem) {
    if (!token || !workspaceSlug) return;
    const source = sourceById.get(item.sourceId);
    if (!source?.cancel) return;
    const key = itemKey(item);
    setCancellingKeys((current) => new Set(current).add(key));
    try {
      await source.cancel({ token, workspaceSlug, item });
    } finally {
      setCancellingKeys((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
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
          const key = itemKey(item);
          const cancelling = cancellingKeys.has(key);
          return (
            <div key={key} className="flex items-start gap-2 border-b border-app-border px-3 py-3 last:border-b-0">
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
