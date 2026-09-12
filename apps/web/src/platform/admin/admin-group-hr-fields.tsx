import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@open-work-hub/ui';
import { DirectoryPicker } from '@/src/platform/directory/DirectoryPicker';
import { listHrGroups, type HrGroupItem } from './admin-api';
import { buildHrGroupRows, descendantIds } from './admin-group-hierarchy';
import { FORM_FIELD_CLASS } from './admin-shared';

export interface HrFields {
  slug: string;
  source_reference: string;
  unit_type: string;
  parent_id: string | null;
  head_user_id: string | null;
}
export const emptyHrFields: HrFields = {
  slug: '',
  source_reference: '',
  unit_type: 'department',
  parent_id: null,
  head_user_id: null,
};

export function GroupHrFields({
  token,
  groupId,
  value,
  onChange,
  disabled = false,
}: {
  token: string;
  groupId?: string;
  value: HrFields;
  onChange: (value: HrFields) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation('shell');
  const [groups, setGroups] = useState<HrGroupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFailed(false);
    listHrGroups(token, {
      includeInactive: true,
      signal: controller.signal,
    })
      .then((items) => {
        if (!controller.signal.aborted) setGroups(items);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, retry]);
  const excluded = groupId ? descendantIds(groups, groupId) : new Set<string>();
  const parents = buildHrGroupRows(groups).filter(
    ({ item }) =>
      !excluded.has(item.id) && (item.active || item.id === value.parent_id),
  );
  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend>{t('companyGroups.hrInformation')}</legend>
      <p className="app-text-caption text-app-ink/60">
        {t('companyGroups.hrInformationHint')}
      </p>
      <label className="block">
        <span>{t('companyGroups.sourceReference')}</span>
        <input
          className={FORM_FIELD_CLASS}
          value={value.source_reference}
          maxLength={120}
          onChange={(event) =>
            onChange({ ...value, source_reference: event.target.value })
          }
        />
      </label>
      <label className="block">
        <span>{t('companyGroups.slug')}</span>
        <input
          className={FORM_FIELD_CLASS}
          value={value.slug}
          maxLength={80}
          placeholder={t('companyGroups.slugPlaceholder')}
          onChange={(event) => onChange({ ...value, slug: event.target.value })}
        />
      </label>
      <label className="block">
        <span>{t('companyGroups.unitType')}</span>
        <input
          className={FORM_FIELD_CLASS}
          value={value.unit_type}
          maxLength={40}
          onChange={(event) =>
            onChange({ ...value, unit_type: event.target.value })
          }
        />
      </label>
      <label className="block">
        <span>{t('companyGroups.parent')}</span>
        <select
          className={FORM_FIELD_CLASS}
          value={value.parent_id ?? ''}
          disabled={loading || failed || disabled}
          onChange={(event) =>
            onChange({ ...value, parent_id: event.target.value || null })
          }
        >
          <option value="">{t('companyGroups.noParent')}</option>
          {value.parent_id &&
          !parents.some(({ item }) => item.id === value.parent_id) ? (
            <option value={value.parent_id}>{t('directory.loading')}</option>
          ) : null}
          {parents.map(({ item, depth }) => (
            <option key={item.id} value={item.id}>
              {'　'.repeat(depth)}
              {item.name}
            </option>
          ))}
        </select>
      </label>
      {failed ? (
        <div role="alert">
          {t('companyGroups.loadFailed')}
          <Button onClick={() => setRetry((current) => current + 1)}>
            {t('directory.retry')}
          </Button>
        </div>
      ) : loading ? (
        <p role="status">{t('directory.loading')}</p>
      ) : null}
      <div>
        <p>{t('companyGroups.head')}</p>
        <DirectoryPicker
          token={token}
          kind="people"
          single
          disabled={disabled}
          selectedIds={value.head_user_id ? [value.head_user_id] : []}
          onChange={(ids) =>
            onChange({ ...value, head_user_id: ids[0] ?? null })
          }
        />
        <p className="app-text-caption text-app-ink/60">
          {t('companyGroups.headRule')}
        </p>
      </div>
    </fieldset>
  );
}
