import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';
import { LogOut } from 'lucide-react';

import { AppearanceSettingsSection } from './AppearanceSettingsSection';
import { NotificationsSettingsSection } from './NotificationsSettingsSection';
import { OpenWorkHubDesktopSettingsSection } from './OpenWorkHubDesktopSettingsSection';
import { ProfileSettingsSection } from './ProfileSettingsSection';
import { ReleaseNotesSettingsSection } from './ReleaseNotesSettingsSection';
import { SecuritySettingsSection } from './SecuritySettingsSection';
import { SettingsNavigation } from './SettingsNavigation';
import type { AuthUser } from './auth-api';
import type { AuthContextValue } from './auth-context';
import type { SettingsSection } from './settings-page-model';
import { useProfilePageController } from './useProfilePageController';

export function ProfilePageContent({
  auth,
  initialTab,
  user,
}: {
  auth: AuthContextValue;
  initialTab: SettingsSection;
  user: AuthUser;
}) {
  const {
    dispatch,
    handlePasswordSubmit,
    handleProfileSubmit,
    handleRevoke,
    handleSectionChange,
    i18nLanguage,
    saveDateFormatPreference,
    saveLocalePreference,
    saveThemePreference,
    saveTimeZonePreference,
    state,
    t,
  } = useProfilePageController({ auth, initialTab, user });

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="mx-auto max-w-5xl p-8">
        <div className="mb-8 flex items-center justify-between">
          <h1 className="app-text-title-lg text-app-ink">
            {t('auth:settings.mySettings')}
          </h1>
          <button
            className="app-text-control flex items-center gap-2 rounded-md px-3 py-1.5 text-app-danger-text transition-colors hover:bg-app-danger/10"
            onClick={() => {
              void auth.logout();
            }}
            type="button"
          >
            <LogOut size={15} />
            {t('common:actions.signOut')}
          </button>
        </div>

        {state.message ? (
          <div className="mb-4">
            <InlineNotice tone="success">{String(state.message)}</InlineNotice>
          </div>
        ) : null}
        {state.error ? (
          <div className="mb-4">
            <InlineNotice tone="danger">{String(state.error)}</InlineNotice>
          </div>
        ) : null}

        <div className="grid grid-cols-[200px_1fr] gap-10 max-[820px]:grid-cols-1 max-[820px]:gap-6">
          <SettingsNavigation
            activeSection={state.activeSection}
            onSectionChange={handleSectionChange}
            t={t}
          />
          <div className="min-w-0">
            {state.activeSection === 'profile' ? (
              <ProfileSettingsSection
                dispatch={dispatch}
                onSubmit={(event) => {
                  void handleProfileSubmit(event);
                }}
                state={state}
                t={t}
                user={user}
              />
            ) : null}
            {state.activeSection === 'appearance' ? (
              <AppearanceSettingsSection
                onDateFormatChange={(value) => {
                  void saveDateFormatPreference(value);
                }}
                onLocaleChange={(value) => {
                  void saveLocalePreference(value);
                }}
                onThemeChange={(value) => {
                  void saveThemePreference(value);
                }}
                onTimeZoneChange={(value) => {
                  void saveTimeZonePreference(value);
                }}
                state={state}
                t={t}
              />
            ) : null}
            {state.activeSection === 'security' ? (
              <SecuritySettingsSection
                dispatch={dispatch}
                i18nLanguage={i18nLanguage}
                onPasswordSubmit={(event) => {
                  void handlePasswordSubmit(event);
                }}
                onRevoke={handleRevoke}
                state={state}
                t={t}
                user={user}
              />
            ) : null}
            {state.activeSection === 'notifications' ? (
              <NotificationsSettingsSection t={t} />
            ) : null}
            {state.activeSection === 'releaseNotes' ? (
              <ReleaseNotesSettingsSection
                locale={i18nLanguage}
                t={t}
                token={auth.token}
              />
            ) : null}
            {state.activeSection === 'openWorkHubDesktop' ? (
              <OpenWorkHubDesktopSettingsSection t={t} />
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
