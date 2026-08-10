import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@open-alm/ui';

export const HEALTH_CHECKUP_PAGE_SIZES = [25, 50, 100] as const;
export type HealthCheckupPageSize = (typeof HEALTH_CHECKUP_PAGE_SIZES)[number];

export interface HealthCheckupPaginationProps {
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: HealthCheckupPageSize) => void;
  page: number;
  pageSize: HealthCheckupPageSize;
  total: number;
}

export function HealthCheckupPagination({
  onPageChange,
  onPageSizeChange,
  page,
  pageSize,
  total,
}: HealthCheckupPaginationProps) {
  const { t } = useTranslation(['apps', 'common']);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(page, 1), pageCount);
  const start = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const end = Math.min(safePage * pageSize, total);

  return (
    <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-app-border pt-3">
      <label className="flex items-center gap-2 text-[length:var(--ui-text-caption)] text-app-text-muted">
        <span>{t('apps:healthCheckup.pagination.pageSize')}</span>
        <select
          className="h-[var(--ui-density-dense)] rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface px-2 text-app-text outline-none focus:ring-2 focus:ring-app-accent/30"
          onChange={(event) =>
            onPageSizeChange(
              Number(event.target.value) as HealthCheckupPageSize,
            )
          }
          value={pageSize}
        >
          {HEALTH_CHECKUP_PAGE_SIZES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <span
        aria-live="polite"
        className="text-[length:var(--ui-text-caption)] text-app-text-muted tabular-nums"
      >
        {t('apps:healthCheckup.pagination.summary', {
          start,
          end,
          total,
          page: safePage,
          pageCount,
        })}
      </span>

      <div className="flex items-center gap-1">
        <Button
          aria-label={t('apps:healthCheckup.pagination.previous')}
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
          variant="ghost"
        >
          <ChevronLeft aria-hidden="true" size={16} />
          {t('apps:healthCheckup.pagination.previous')}
        </Button>
        <Button
          aria-label={t('apps:healthCheckup.pagination.next')}
          disabled={safePage >= pageCount}
          onClick={() => onPageChange(safePage + 1)}
          variant="ghost"
        >
          {t('apps:healthCheckup.pagination.next')}
          <ChevronRight aria-hidden="true" size={16} />
        </Button>
      </div>
    </footer>
  );
}
