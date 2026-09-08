import { DropdownMenu, type DropdownItem } from '@open-work-hub/ui';
import {
  Loader2,
  Lock,
  MapPin,
  MoreHorizontal,
  PencilRuler,
  Star,
  Users,
} from 'lucide-react';
import { useEffect, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import {
  formatRelativeTime,
  formatDateTime as formatZonedDateTime,
} from '@/src/platform/time/time-utils';
import type {
  WhiteboardHubItem,
  WhiteboardVisibility,
} from '../api/whiteboard-api';
import {
  createWhiteboardPreviewState,
  getWhiteboardPreviewSourceKey,
  whiteboardPreviewLoader,
  whiteboardPreviewReducer,
} from './whiteboard-preview-loader';

function ownerInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? '').join('') || '?';
}

function formatRelativeDate(
  value: string | null | undefined,
  timeZone: string,
  locale: string,
): string {
  return formatRelativeTime(value, { fallback: '-', locale, timeZone });
}

function formatDateTime(
  value: string | null | undefined,
  timeZone: string,
  locale: string,
): string {
  return formatZonedDateTime(value, {
    fallback: '-',
    locale,
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  });
}

export function buildWhiteboardVisibilityMenuItems({
  canManage,
  currentVisibility,
  onChange,
  t,
}: {
  canManage: boolean;
  currentVisibility: WhiteboardVisibility;
  onChange: (visibility: WhiteboardVisibility) => void;
  t: (key: string, options?: Record<string, unknown>) => string;
}): DropdownItem[] {
  return [
    {
      id: 'current',
      disabled: true,
      label: t('whiteboard.visibilityCurrent', {
        visibility: t(
          currentVisibility === 'company'
            ? 'whiteboard.visibilityCompany'
            : 'whiteboard.visibilityPersonal',
        ),
      }),
    },
    {
      id: 'personal',
      separatorBefore: true,
      disabled: !canManage || currentVisibility === 'personal',
      label: (
        <span className="inline-flex items-center gap-2">
          <Lock size={14} />
          {t('whiteboard.changeToPersonal')}
        </span>
      ),
      onSelect: () => onChange('personal'),
    },
    {
      id: 'company',
      disabled: !canManage || currentVisibility === 'company',
      label: (
        <span className="inline-flex items-center gap-2">
          <Users size={14} />
          {t('whiteboard.changeToCompany')}
        </span>
      ),
      onSelect: () => onChange('company'),
    },
    {
      id: 'scope-notice',
      separatorBefore: true,
      disabled: true,
      label: t('whiteboard.visibilityScopeNotice'),
    },
    {
      id: 'manage-required',
      separatorBefore: true,
      disabled: true,
      label: t('whiteboard.visibilityManageRequired'),
    },
  ].filter((item) => item.id !== 'manage-required' || !canManage);
}

function WhiteboardPreview({
  item,
  token,
}: {
  item: WhiteboardHubItem;
  token: string | null;
}) {
  const { t } = useTranslation('apps');
  const targetRef = useRef<HTMLDivElement | null>(null);
  const sourceKey = getWhiteboardPreviewSourceKey(item);
  const [previewState, dispatchPreview] = useReducer(
    whiteboardPreviewReducer,
    sourceKey,
    createWhiteboardPreviewState,
  );
  const effectivePreviewState =
    previewState.sourceKey === sourceKey
      ? previewState
      : createWhiteboardPreviewState(sourceKey);
  const { status, previewUrl } = effectivePreviewState;

  useEffect(() => {
    if (status !== 'idle') return undefined;
    const node = targetRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      dispatchPreview({ type: 'previewVisible', sourceKey });
      return undefined;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          dispatchPreview({ type: 'previewVisible', sourceKey });
          observer.disconnect();
        }
      },
      { rootMargin: '240px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [sourceKey, status]);

  useEffect(() => {
    if (status !== 'loading' || !token) return undefined;
    let cancelled = false;
    whiteboardPreviewLoader
      .load(token, item)
      .then((url) => {
        if (cancelled) return;
        dispatchPreview({ type: 'previewLoaded', previewUrl: url, sourceKey });
      })
      .catch(() => {
        if (cancelled) return;
        dispatchPreview({ type: 'previewFailed', sourceKey });
      });
    return () => {
      cancelled = true;
    };
  }, [item, sourceKey, status, token]);

  return (
    <div
      ref={targetRef}
      className="flex aspect-[16/10] w-full items-center justify-center overflow-hidden bg-white"
    >
      {status === 'ready' && previewUrl ? (
        <img
          src={previewUrl}
          alt=""
          className="h-full w-full object-contain"
          draggable={false}
        />
      ) : status === 'loading' ? (
        <Loader2 size={18} className="animate-spin text-app-ink/35" />
      ) : (
        <div className="flex flex-col items-center gap-2 text-app-ink/40">
          <PencilRuler size={22} className="text-app-warning" />
          <span className="app-text-body-sm">
            {status === 'error'
              ? t('whiteboard.previewUnavailable')
              : t('whiteboard.emptyBoard')}
          </span>
        </div>
      )}
    </div>
  );
}

export function WhiteboardCard({
  item,
  token,
  timeZone,
  onOpen,
  onVisibilityChange,
}: {
  item: WhiteboardHubItem;
  token: string | null;

  timeZone: string;
  onOpen: (item: WhiteboardHubItem) => void;
  onVisibilityChange: (
    item: WhiteboardHubItem,
    visibility: WhiteboardVisibility,
  ) => void;
}) {
  const { t, i18n } = useTranslation('apps');
  const visibility: WhiteboardVisibility = item.company_visible
    ? 'company'
    : 'personal';
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(item);
        }
      }}
      className="group flex min-h-[300px] flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-app-accent/45 hover:shadow-md"
    >
      <div className="relative">
        <WhiteboardPreview item={item} token={token} />
        <div
          className="absolute right-2 top-2"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <DropdownMenu
            align="end"
            side="bottom"
            trigger={
              <button
                type="button"
                aria-label={t('whiteboard.actionsMenu')}
                className="inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-bg/95 text-app-ink/65 shadow-sm backdrop-blur transition hover:text-app-ink"
              >
                <MoreHorizontal size={16} />
              </button>
            }
            items={buildWhiteboardVisibilityMenuItems({
              canManage: item.can_manage,
              currentVisibility: visibility,
              onChange: (nextVisibility) =>
                onVisibilityChange(item, nextVisibility),
              t,
            })}
          />
        </div>
      </div>
      <div className="flex min-h-[112px] items-start gap-3 border-t border-app-border p-4">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-app-ink text-xs font-semibold text-app-bg">
          {ownerInitials(item.created_by_name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <PencilRuler size={15} className="shrink-0 text-app-warning" />
            <p className="app-text-title-sm min-w-0 flex-1 truncate text-app-ink">
              {item.title}
            </p>
            {item.is_favorite ? (
              <Star
                size={14}
                fill="currentColor"
                className="shrink-0 text-app-warning"
              />
            ) : null}
          </div>
          <p className="app-text-body-sm mt-2 truncate text-app-ink/55">
            {t('whiteboard.edited', {
              date: formatRelativeDate(
                item.updated_at,
                timeZone,
                i18n.language,
              ),
            })}
          </p>
          <p className="app-text-body-sm mt-1 truncate text-app-ink/45">
            {item.location_label || t('whiteboard.fallbackCompany')}
          </p>
          <p className="app-text-body-sm mt-1 truncate text-app-ink/45">
            {item.created_by_name || t('whiteboard.unknown')}
          </p>
          <div className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-md border border-app-border px-2 py-1 text-xs text-app-ink/55">
            {visibility === 'company' ? (
              <Users size={13} className="shrink-0 text-app-warning" />
            ) : (
              <Lock size={13} className="shrink-0 text-app-ink/45" />
            )}
            <span className="truncate">
              {t(
                visibility === 'company'
                  ? 'whiteboard.visibilityCompany'
                  : 'whiteboard.visibilityPersonal',
              )}
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}

export function WhiteboardListTable({
  items,
  timeZone,
  onOpen,
  onVisibilityChange,
}: {
  items: WhiteboardHubItem[];
  timeZone: string;
  onOpen: (item: WhiteboardHubItem) => void;
  onVisibilityChange: (
    item: WhiteboardHubItem,
    visibility: WhiteboardVisibility,
  ) => void;
}) {
  const { t, i18n } = useTranslation('apps');
  return (
    <div className="overflow-hidden rounded-lg border border-app-border bg-app-surface">
      <div className="overflow-x-auto">
        <table className="min-w-[960px] w-full border-collapse">
          <thead className="bg-app-surface-hover text-left">
            <tr className="app-text-caption text-app-ink/55">
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableName')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableLocation')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableUpdated')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableCreated')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableViewed')}
              </th>
              <th className="px-5 py-3 font-medium">
                {t('whiteboard.tableCreator')}
              </th>
              <th className="w-12 px-4 py-3 font-medium">
                <span className="sr-only">{t('whiteboard.actionsMenu')}</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-app-border">
            {items.map((item) => {
              const visibility: WhiteboardVisibility = item.company_visible
                ? 'company'
                : 'personal';
              return (
                <tr
                  key={item.id}
                  onClick={() => onOpen(item)}
                  className="cursor-pointer transition-colors hover:bg-app-surface-hover"
                >
                  <td className="px-5 py-4">
                    <div className="flex min-w-0 items-center gap-2">
                      <PencilRuler
                        size={16}
                        className="shrink-0 text-app-warning"
                      />
                      <span className="app-text-title-sm min-w-0 truncate text-app-ink">
                        {item.title}
                      </span>
                      {item.is_favorite ? (
                        <Star
                          size={13}
                          fill="currentColor"
                          className="shrink-0 text-app-warning"
                        />
                      ) : null}
                    </div>
                  </td>
                  <td className="app-text-body-sm px-5 py-4 text-app-ink/65">
                    <span className="inline-flex max-w-[220px] items-center gap-2 truncate">
                      <MapPin size={14} className="shrink-0 text-app-ink/35" />
                      <span className="truncate">
                        {item.location_label || t('whiteboard.fallbackCompany')}
                      </span>
                    </span>
                  </td>
                  <td
                    className="app-text-body-sm px-5 py-4 text-app-ink/65"
                    title={formatDateTime(
                      item.updated_at,
                      timeZone,
                      i18n.language,
                    )}
                  >
                    {formatRelativeDate(
                      item.updated_at,
                      timeZone,
                      i18n.language,
                    )}
                  </td>
                  <td
                    className="app-text-body-sm px-5 py-4 text-app-ink/65"
                    title={formatDateTime(
                      item.created_at,
                      timeZone,
                      i18n.language,
                    )}
                  >
                    {formatRelativeDate(
                      item.created_at,
                      timeZone,
                      i18n.language,
                    )}
                  </td>
                  <td
                    className="app-text-body-sm px-5 py-4 text-app-ink/65"
                    title={formatDateTime(
                      item.last_viewed_at,
                      timeZone,
                      i18n.language,
                    )}
                  >
                    {formatRelativeDate(
                      item.last_viewed_at,
                      timeZone,
                      i18n.language,
                    )}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-app-ink text-[11px] font-semibold text-app-bg">
                        {ownerInitials(item.created_by_name)}
                      </div>
                      <span className="app-text-body-sm max-w-[180px] truncate text-app-ink/65">
                        {item.created_by_name || t('whiteboard.unknown')}
                      </span>
                    </div>
                  </td>
                  <td
                    className="px-4 py-4"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <DropdownMenu
                      align="end"
                      side="bottom"
                      trigger={
                        <button
                          type="button"
                          aria-label={t('whiteboard.actionsMenu')}
                          className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/60 transition hover:bg-app-surface-hover hover:text-app-ink"
                        >
                          <MoreHorizontal size={16} />
                        </button>
                      }
                      items={buildWhiteboardVisibilityMenuItems({
                        canManage: item.can_manage,
                        currentVisibility: visibility,
                        onChange: (nextVisibility) =>
                          onVisibilityChange(item, nextVisibility),
                        t,
                      })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function WhiteboardEditorFallback() {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-app-bg text-app-ink/45">
      <Loader2 size={24} className="animate-spin" />
    </div>
  );
}
