import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { UserDateTime } from '@/src/components/date/UserDateTime';

export type LegacyIssueHistoryEntry = {
  action: string;
  actor_email: string | null;
  actor_name: string | null;
  created_at: string;
  field_label: string | null;
  id: string;
  new_value: string | null;
  old_value: string | null;
  revision_id: string | null;
  revision_no: number | null;
  revision_status: string | null;
};

export function LegacyIssueHistoryList({
  items,
  loading,
}: {
  items: LegacyIssueHistoryEntry[];
  loading: boolean;
}) {
  const { t } = useTranslation(['apps']);
  if (loading) {
    return (
      <div className="flex min-h-32 items-center justify-center gap-2 app-text-caption text-app-ink/50">
        <Loader2 size={14} className="animate-spin" />
        <span>{t('coreBusiness.history.loading')}</span>
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-app-border px-3 py-5 text-center app-text-caption text-app-ink/50">
        {t('coreBusiness.history.empty')}
      </div>
    );
  }
  return (
    <div className="max-h-full overflow-auto rounded-md border border-app-border">
      <table className="min-w-[54rem] w-full border-collapse app-text-micro">
        <thead className="sticky top-0 bg-app-surface-sidebar text-app-ink/60">
          <tr>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.field')}
            </th>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.revision')}
            </th>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.before')}
            </th>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.after')}
            </th>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.actor')}
            </th>
            <th className="border-b border-app-border px-2 py-1.5 text-left font-semibold">
              {t('coreBusiness.history.changedAt')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="odd:bg-app-surface-sidebar/50">
              <td className="border-b border-app-border px-2 py-1.5 align-top">
                <div className="font-medium text-app-ink/80">
                  {item.field_label || t('coreBusiness.history.record')}
                </div>
                <div className="text-app-ink/45">
                  {t(`coreBusiness.history.actions.${item.action}`, {
                    defaultValue: item.action,
                  })}
                </div>
              </td>
              <td className="whitespace-nowrap border-b border-app-border px-2 py-1.5 align-top text-app-ink/70">
                {historyRevisionLabel(item, t)}
              </td>
              <HistoryValue value={item.old_value} />
              <HistoryValue value={item.new_value} />
              <td className="border-b border-app-border px-2 py-1.5 align-top text-app-ink/70">
                {item.actor_name ||
                  item.actor_email ||
                  t('coreBusiness.history.unknownActor')}
              </td>
              <td className="whitespace-nowrap border-b border-app-border px-2 py-1.5 align-top text-app-ink/55">
                <UserDateTime
                  value={item.created_at}
                  options={{ hourCycle: 'h23' }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryValue({ value }: { value: string | null }) {
  const { t } = useTranslation(['apps']);
  return (
    <td className="max-w-64 border-b border-app-border px-2 py-1.5 align-top">
      <div className="max-h-16 overflow-y-auto whitespace-pre-wrap break-words text-app-ink/75">
        {value || t('coreBusiness.history.emptyValue')}
      </div>
    </td>
  );
}

function historyRevisionLabel(
  item: LegacyIssueHistoryEntry,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (item.revision_no) {
    return t('coreBusiness.history.revisionNo', { revision: item.revision_no });
  }
  if (item.revision_status === 'draft') {
    return t('coreBusiness.history.draftRevision');
  }
  if (!item.revision_id) {
    return '';
  }
  return t('coreBusiness.history.unknownRevision');
}
