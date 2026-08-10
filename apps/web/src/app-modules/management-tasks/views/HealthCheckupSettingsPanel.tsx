import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Panel } from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import type {
  AgeCalcMethod,
  HealthCheckupSettings,
  HealthCheckupSettingsUpdate,
  SettingsHistoryItem,
} from '../api/health-checkup-api';

interface SettingsDraft {
  ageCalcMethod: AgeCalcMethod;
  seniorAge: string;
  adultAge: string;
  serviceYearsThreshold: string;
}

function settingsDraft(settings: HealthCheckupSettings): SettingsDraft {
  return {
    ageCalcMethod: settings.age_calc_method,
    seniorAge: String(settings.senior_age),
    adultAge: String(settings.adult_age),
    serviceYearsThreshold: String(settings.service_years_threshold),
  };
}

function parseInteger(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

function buildPayload(
  draft: SettingsDraft,
): HealthCheckupSettingsUpdate | null {
  const seniorAge = parseInteger(draft.seniorAge);
  const adultAge = parseInteger(draft.adultAge);
  const serviceYearsThreshold = parseInteger(draft.serviceYearsThreshold);
  if (
    seniorAge === null ||
    adultAge === null ||
    serviceYearsThreshold === null
  ) {
    return null;
  }
  return {
    age_calc_method: draft.ageCalcMethod,
    senior_age: seniorAge,
    adult_age: adultAge,
    service_years_threshold: serviceYearsThreshold,
  };
}

function historyValue(
  item: SettingsHistoryItem,
  value: string | null,
  t: (key: string) => string,
): string {
  if (value === null) return t('common:empty.none');
  if (item.field_key === 'age_calc_method') {
    if (value === 'korean') return t('apps:healthCheckup.settings.korean');
    if (value === 'international') {
      return t('apps:healthCheckup.settings.international');
    }
  }
  return value;
}

export interface HealthCheckupSettingsPanelProps {
  history: SettingsHistoryItem[];
  onSave: (payload: HealthCheckupSettingsUpdate) => void;
  saving: boolean;
  settings: HealthCheckupSettings | null;
}

export function HealthCheckupSettingsPanel({
  history,
  onSave,
  saving,
  settings,
}: HealthCheckupSettingsPanelProps) {
  const { t } = useTranslation(['apps', 'common']);
  const [draft, setDraft] = useState<SettingsDraft | null>(
    settings ? settingsDraft(settings) : null,
  );

  useEffect(() => {
    setDraft(settings ? settingsDraft(settings) : null);
  }, [settings]);

  const payload = useMemo(
    () => (settings && draft ? buildPayload(draft) : null),
    [draft, settings],
  );
  const dirty = Boolean(
    settings &&
      payload &&
      (payload.age_calc_method !== settings.age_calc_method ||
        payload.senior_age !== settings.senior_age ||
        payload.adult_age !== settings.adult_age ||
        payload.service_years_threshold !== settings.service_years_threshold),
  );

  if (!draft || !settings) return null;

  const numberField = (
    key: 'seniorAge' | 'adultAge' | 'serviceYearsThreshold',
    label: string,
  ) => (
    <label className="grid gap-1 text-[length:var(--ui-text-body-sm)]">
      <span className="text-app-text">{label}</span>
      <Input
        inputMode="numeric"
        min={0}
        onChange={(event) =>
          setDraft((current) =>
            current ? { ...current, [key]: event.target.value } : current,
          )
        }
        step={1}
        type="number"
        value={draft[key]}
      />
    </label>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel>
        <div className="grid gap-3 p-4">
          <h2 className="m-0 text-app-text text-[length:var(--ui-text-h3)] font-semibold">
            {t('apps:healthCheckup.settings.title')}
          </h2>
          <label className="grid gap-1 text-[length:var(--ui-text-body-sm)]">
            <span className="text-app-text">
              {t('apps:healthCheckup.settings.ageCalcMethod')}
            </span>
            <select
              className="h-[var(--ui-density-dense)] rounded-[var(--ui-radius-sm)] border border-app-border bg-app-surface px-2 text-app-text outline-none focus:ring-2 focus:ring-app-accent/30"
              onChange={(event) =>
                setDraft((current) =>
                  current
                    ? {
                        ...current,
                        ageCalcMethod: event.target.value as AgeCalcMethod,
                      }
                    : current,
                )
              }
              value={draft.ageCalcMethod}
            >
              <option value="korean">
                {t('apps:healthCheckup.settings.korean')}
              </option>
              <option value="international">
                {t('apps:healthCheckup.settings.international')}
              </option>
            </select>
          </label>
          {numberField('seniorAge', t('apps:healthCheckup.settings.seniorAge'))}
          {numberField('adultAge', t('apps:healthCheckup.settings.adultAge'))}
          {numberField(
            'serviceYearsThreshold',
            t('apps:healthCheckup.settings.serviceYearsThreshold'),
          )}
          {!payload ? (
            <p className="m-0 text-[length:var(--ui-text-caption)] text-app-danger-text">
              {t('apps:healthCheckup.settings.invalidNumber')}
            </p>
          ) : null}
          <div>
            <Button
              disabled={!payload || !dirty || saving}
              onClick={() => payload && onSave(payload)}
            >
              {saving
                ? t('apps:healthCheckup.actions.savingSettings')
                : t('apps:healthCheckup.actions.saveSettings')}
            </Button>
          </div>
        </div>
      </Panel>

      <Panel>
        <div className="grid gap-2 p-4">
          <h2 className="m-0 text-app-text text-[length:var(--ui-text-h3)] font-semibold">
            {t('apps:healthCheckup.settings.historyTitle')}
          </h2>
          {history.length === 0 ? (
            <p className="m-0 text-app-text-muted text-[length:var(--ui-text-body-sm)]">
              {t('apps:healthCheckup.settings.noHistory')}
            </p>
          ) : (
            <ul className="m-0 grid list-none gap-2 p-0">
              {history.map((item) => (
                <li
                  className="grid gap-0.5 border-b border-app-border pb-2 text-[length:var(--ui-text-body-sm)]"
                  key={item.id}
                >
                  <span className="text-app-text">
                    {t(`apps:healthCheckup.settings.fields.${item.field_key}`, {
                      defaultValue: t(
                        'apps:healthCheckup.settings.fields.unknown',
                      ),
                    })}
                    {': '}
                    {t('apps:healthCheckup.settings.historyChange', {
                      oldValue: historyValue(item, item.old_value, t),
                      newValue: historyValue(item, item.new_value, t),
                    })}
                  </span>
                  <span className="text-app-text-muted text-[length:var(--ui-text-caption)]">
                    {item.changed_by_name ?? t('common:feedback.unknown')}{' '}
                    <UserDateTime value={item.created_at} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>
    </div>
  );
}
