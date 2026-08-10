import { type FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { Button, InlineNotice } from '@ai-do/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

import { listAuditLogs, type AuditLogItem } from './admin-api';
import { buildAuditLogDisplay } from './admin-audit-log-model';
import {
  Badge,
  EmptyPanel,
  FORM_FIELD_CLASS as fieldClassName,
  SurfaceCard,
  getErrorMessage,
} from './admin-shared';

export const AUDIT_LOG_PAGE_SIZE = 50;

const AUDIT_LOG_DEFAULT_DAYS = 7;
const AUDIT_LOG_PERIOD_OPTIONS = [1, 7, 30, 90, 365] as const;
const AI_SECURITY_AUDIT_SCOPE = 'ai-security';
const AI_SECURITY_BLOCKED_PARAM = 'blocked';

function formatAuditNumber(
  value: number | null | undefined,
  locale: string,
): string {
  return new Intl.NumberFormat(locale).format(value ?? 0);
}

function AuditLogRow({
  item,
  locale,
  timeZone,
}: {
  item: AuditLogItem;
  locale: string;
  timeZone: string;
}) {
  const { t } = useTranslation('apps');
  const display = buildAuditLogDisplay(item, (key, options) => t(key, options));
  const createdAt = formatDateTime(item.created_at, {
    dateStyle: 'medium',
    locale,
    timeStyle: 'short',
    timeZone,
  });
  const visibleDetails = display.detailItems.slice(0, 4);
  const detailSummary = visibleDetails
    .map((detail) => `${detail.label}: ${detail.value}`)
    .join(' / ');

  return (
    <li className="border-b border-app-border last:border-b-0">
      <div className="grid gap-2 px-3 py-2.5 lg:grid-cols-[150px_76px_minmax(0,1.4fr)_160px_minmax(160px,0.8fr)_minmax(120px,0.6fr)] lg:items-start">
        <time
          className="app-text-body-sm text-app-ink/70"
          dateTime={item.created_at}
        >
          {createdAt}
        </time>
        <div>
          <Badge tone="purple">{display.groupLabel}</Badge>
        </div>
        <div className="min-w-0">
          <div
            className="app-text-body-sm min-w-0 truncate"
            title={[display.actionLabel, display.summary, detailSummary]
              .filter(Boolean)
              .join(' / ')}
          >
            <span className="app-text-body-sm font-semibold text-app-ink">
              {display.actionLabel}
            </span>
            <span className="text-app-ink/50"> / </span>
            <span className="text-app-ink/80">{display.summary}</span>
            {detailSummary ? (
              <>
                <span className="text-app-ink/50"> / </span>
                <span className="text-app-ink/60">{detailSummary}</span>
              </>
            ) : null}
          </div>
        </div>
        <span
          className="app-text-body-sm truncate text-app-ink/70"
          title={display.actorLabel}
        >
          {display.actorLabel}
        </span>
        <span
          className="app-text-body-sm truncate text-app-ink/70"
          title={display.entityLabel}
        >
          {display.entityLabel}
        </span>
        <code className="truncate rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-[11px] text-app-ink/60">
          {display.actionCode}
        </code>
      </div>
    </li>
  );
}

export function AuditLogList({
  emptyDescription,
  emptyTitle,
  items,
  loading,
  loadingDescription,
  loadingTitle,
  locale,
  timeZone,
}: {
  emptyDescription: string;
  emptyTitle: string;
  items: AuditLogItem[];
  loading: boolean;
  loadingDescription: string;
  loadingTitle: string;
  locale: string;
  timeZone: string;
}) {
  if (loading && items.length === 0) {
    return <EmptyPanel description={loadingDescription} title={loadingTitle} />;
  }
  if (items.length === 0) {
    return <EmptyPanel description={emptyDescription} title={emptyTitle} />;
  }
  return (
    <ul className="overflow-hidden rounded-md border border-app-border bg-app-surface-sidebar">
      {items.map((item) => (
        <AuditLogRow
          item={item}
          key={item.id}
          locale={locale}
          timeZone={timeZone}
        />
      ))}
    </ul>
  );
}

export function AuditLogPager({
  limit,
  loading,
  locale,
  offset,
  onNext,
  onPrevious,
  total,
}: {
  limit: number;
  loading: boolean;
  locale: string;
  offset: number;
  onNext: () => void;
  onPrevious: () => void;
  total: number;
}) {
  const { t } = useTranslation('apps');
  const from = total === 0 ? 0 : Math.min(offset + 1, total);
  const to = Math.min(offset + limit, total);
  const nextDisabled = loading || offset + limit >= total;
  const previousDisabled = loading || offset <= 0;

  return (
    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="app-text-body-sm text-app-ink/70">
        {t('admin.console.audit.pageRange', {
          from: formatAuditNumber(from, locale),
          to: formatAuditNumber(to, locale),
          total: formatAuditNumber(total, locale),
        })}
      </div>
      <div className="flex items-center gap-2">
        <Button
          disabled={previousDisabled}
          onClick={onPrevious}
          type="button"
          variant="secondary"
        >
          {t('admin.console.audit.previousPage')}
        </Button>
        <Button
          disabled={nextDisabled}
          onClick={onNext}
          type="button"
          variant="secondary"
        >
          {t('admin.console.audit.nextPage')}
        </Button>
      </div>
    </div>
  );
}

export function AuditSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const [searchParams, setSearchParams] = useSearchParams();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const { user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const aiSecurityBlockedOnly =
    searchParams.get(AI_SECURITY_BLOCKED_PARAM) === 'true';
  const aiSecurityOnly =
    searchParams.get('scope') === AI_SECURITY_AUDIT_SCOPE ||
    aiSecurityBlockedOnly;
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [action, setAction] = useState('');
  const [days, setDays] = useState(String(AUDIT_LOG_DEFAULT_DAYS));
  const [appliedSearch, setAppliedSearch] = useState('');
  const [appliedAction, setAppliedAction] = useState('');
  const [appliedDays, setAppliedDays] = useState(
    String(AUDIT_LOG_DEFAULT_DAYS),
  );

  const loadItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listAuditLogs(token, {
        action: appliedAction.trim() || undefined,
        ai_security_blocked_only: aiSecurityBlockedOnly || undefined,
        ai_security_only: aiSecurityOnly || undefined,
        days: appliedDays ? Number(appliedDays) : undefined,
        limit: AUDIT_LOG_PAGE_SIZE,
        offset,
        q: appliedSearch.trim() || undefined,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.audit.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [
    aiSecurityBlockedOnly,
    aiSecurityOnly,
    appliedAction,
    appliedDays,
    appliedSearch,
    offset,
    t,
    token,
  ]);

  useEffect(() => {
    if (
      !aiSecurityBlockedOnly ||
      searchParams.get('scope') === AI_SECURITY_AUDIT_SCOPE
    ) {
      return;
    }
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('scope', AI_SECURITY_AUDIT_SCOPE);
    setSearchParams(nextParams, { replace: true });
  }, [aiSecurityBlockedOnly, searchParams, setSearchParams]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setOffset(0);
    setAppliedSearch(search);
    setAppliedAction(action);
    setAppliedDays(days);
  };

  const handleRefresh = () => {
    void loadItems();
  };

  const setAiSecurityFilters = (
    nextAiSecurityOnly: boolean,
    nextBlockedOnly: boolean,
  ) => {
    const nextParams = new URLSearchParams(searchParams);
    if (nextAiSecurityOnly || nextBlockedOnly) {
      nextParams.set('scope', AI_SECURITY_AUDIT_SCOPE);
    } else if (nextParams.get('scope') === AI_SECURITY_AUDIT_SCOPE) {
      nextParams.delete('scope');
    }
    if (nextBlockedOnly) {
      nextParams.set(AI_SECURITY_BLOCKED_PARAM, 'true');
    } else {
      nextParams.delete(AI_SECURITY_BLOCKED_PARAM);
    }
    setOffset(0);
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <div className="space-y-6">
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      <SurfaceCard
        description={t('admin.console.audit.description')}
        title={t('admin.console.audit.title')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              aria-pressed={aiSecurityOnly}
              disabled={loading}
              onClick={() => setAiSecurityFilters(!aiSecurityOnly, false)}
              type="button"
              variant={aiSecurityOnly ? 'primary' : 'secondary'}
            >
              {t('admin.console.audit.filters.aiSecurityOnly')}
            </Button>
            <Button
              aria-pressed={aiSecurityBlockedOnly}
              disabled={loading}
              onClick={() => setAiSecurityFilters(true, !aiSecurityBlockedOnly)}
              type="button"
              variant={aiSecurityBlockedOnly ? 'primary' : 'secondary'}
            >
              {t('admin.console.audit.filters.aiSecurityBlockedOnly')}
            </Button>
            <Button
              disabled={loading}
              onClick={handleRefresh}
              type="button"
              variant="secondary"
            >
              <RefreshCw size={16} />
              {t('admin.console.usage.refresh')}
            </Button>
          </div>
        }
      >
        <form
          className="mb-4 grid gap-2 lg:grid-cols-[minmax(0,1fr)_180px_160px_auto]"
          onSubmit={handleSubmit}
        >
          <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
            <Search size={14} className="shrink-0 text-app-ink/50" />
            <input
              aria-label={t('admin.console.audit.searchPlaceholder')}
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t('admin.console.audit.searchPlaceholder')}
              value={search}
            />
          </div>
          <input
            aria-label={t('admin.console.audit.actionPlaceholder')}
            className={fieldClassName}
            onChange={(event) => setAction(event.target.value)}
            placeholder={t('admin.console.audit.actionPlaceholder')}
            value={action}
          />
          <select
            aria-label={t('admin.console.audit.periodPlaceholder')}
            className="app-field-input-sm"
            onChange={(event) => setDays(event.target.value)}
            value={days}
          >
            <option value="">{t('admin.console.audit.periodAll')}</option>
            {AUDIT_LOG_PERIOD_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {t('admin.console.audit.periodDays', { count: option })}
              </option>
            ))}
          </select>
          <Button disabled={loading} type="submit" variant="secondary">
            {t('admin.console.usage.applyFilters')}
          </Button>
        </form>
        <AuditLogList
          emptyDescription={t(
            aiSecurityBlockedOnly
              ? 'admin.console.aiSecurity.audit.blockedEmptyDescription'
              : 'admin.console.audit.emptyDescription',
          )}
          emptyTitle={t(
            aiSecurityBlockedOnly
              ? 'admin.console.aiSecurity.audit.blockedEmptyTitle'
              : 'admin.console.audit.emptyTitle',
          )}
          items={items}
          loading={loading}
          loadingDescription={t('admin.console.audit.loadingDescription')}
          loadingTitle={t('admin.console.audit.loadingTitle')}
          locale={locale}
          timeZone={timeZone}
        />
        <AuditLogPager
          limit={AUDIT_LOG_PAGE_SIZE}
          loading={loading}
          locale={locale}
          offset={offset}
          onNext={() => setOffset((current) => current + AUDIT_LOG_PAGE_SIZE)}
          onPrevious={() =>
            setOffset((current) => Math.max(0, current - AUDIT_LOG_PAGE_SIZE))
          }
          total={total}
        />
      </SurfaceCard>
    </div>
  );
}
