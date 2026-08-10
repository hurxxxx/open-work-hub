import { Monitor, Moon, Sun } from 'lucide-react';

import {
  DATE_FORMAT_OPTIONS,
  TIME_ZONE_OPTIONS,
} from '@/src/platform/time/time-utils';
import { LOCALE_OPTIONS } from '@/src/platform/i18n';
import { cn } from '@/src/lib/utils';
import { SettingsFieldRow } from './SettingsFieldRow';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import {
  type ProfilePageState,
  type SettingsTranslator,
} from './settings-page-model';
import type { AuthUser, ThemePreference } from './auth-api';

const themeOptions: {
  value: ThemePreference;
  labelKey: string;
  icon: typeof Sun;
}[] = [
  { value: 'system', labelKey: 'theme.system', icon: Monitor },
  { value: 'light', labelKey: 'theme.light', icon: Sun },
  { value: 'dark', labelKey: 'theme.dark', icon: Moon },
];

export function AppearanceSettingsSection({
  onDateFormatChange,
  onDefaultWorkspaceChange,
  onLocaleChange,
  onThemeChange,
  onTimeZoneChange,
  state,
  t,
  user,
}: {
  onDateFormatChange: (value: string) => void;
  onDefaultWorkspaceChange: (value: string) => void;
  onLocaleChange: (value: string) => void;
  onThemeChange: (value: ThemePreference) => void;
  onTimeZoneChange: (value: string) => void;
  state: ProfilePageState;
  t: SettingsTranslator;
  user: AuthUser;
}) {
  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.appearance')}
        description={t('auth:settings.customizeAppearance')}
      />

      <div className="border-t border-app-border">
        <SettingsFieldRow
          label={t('auth:settings.theme')}
          description={t('auth:settings.themeDescription')}
        >
          <div className="flex gap-2">
            {themeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onThemeChange(option.value)}
                className={cn(
                  'app-text-control flex items-center gap-2 rounded-md border px-4 py-2.5 transition-colors',
                  state.themePreference === option.value
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border bg-app-bg text-app-ink hover:border-app-ink/30',
                )}
              >
                <option.icon size={15} />
                {t(`auth:${option.labelKey}`)}
              </button>
            ))}
          </div>
        </SettingsFieldRow>
        <SettingsFieldRow
          label={t('auth:settings.language')}
          description={t('auth:settings.languageDescription')}
        >
          <select
            aria-label={t('auth:settings.language')}
            className="app-field-input"
            onChange={(event) => onLocaleChange(event.target.value)}
            value={state.locale}
          >
            {LOCALE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </SettingsFieldRow>
        <SettingsFieldRow
          label={t('auth:settings.timeZone')}
          description={t('auth:settings.timeZoneDescription')}
        >
          <select
            aria-label={t('auth:settings.timeZone')}
            className="app-field-input"
            onChange={(event) => onTimeZoneChange(event.target.value)}
            value={state.timeZone}
          >
            {TIME_ZONE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </SettingsFieldRow>
        <SettingsFieldRow
          label={t('auth:settings.dateFormat')}
          description={t('auth:settings.dateFormatDescription')}
        >
          <select
            aria-label={t('auth:settings.dateFormat')}
            className="app-field-input"
            onChange={(event) => onDateFormatChange(event.target.value)}
            value={state.dateFormat}
          >
            {DATE_FORMAT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(option.labelKey)}
              </option>
            ))}
          </select>
        </SettingsFieldRow>
        <SettingsFieldRow
          label={t('auth:settings.defaultWorkspace')}
          description={t('auth:settings.defaultWorkspaceDescription')}
        >
          <select
            aria-label={t('auth:settings.defaultWorkspace')}
            className="app-field-input"
            disabled={user.workspaces.length === 0}
            onChange={(event) => onDefaultWorkspaceChange(event.target.value)}
            value={state.defaultWorkspaceId}
          >
            <option value="">{t('auth:settings.defaultWorkspaceNone')}</option>
            {user.workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </SettingsFieldRow>
      </div>
    </div>
  );
}
