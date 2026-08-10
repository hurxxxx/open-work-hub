import { DesktopInstallerPanel } from './desktop-installer-panel';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import type { SettingsTranslator } from './settings-page-model';

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
