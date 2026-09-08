import { DesktopInstallerPanel } from './desktop-installer-panel';
import type { SettingsTranslator } from './settings-page-model';
import { SettingsSectionHeader } from './SettingsSectionHeader';

export function OpenWorkHubDesktopSettingsSection({
  t,
}: {
  t: SettingsTranslator;
}) {
  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.openWorkHubDesktop')}
        description={t('auth:settings.openWorkHubDesktopSettingsDescription')}
      />

      <div className="border-t border-app-border">
        <DesktopInstallerPanel />
      </div>
    </div>
  );
}
