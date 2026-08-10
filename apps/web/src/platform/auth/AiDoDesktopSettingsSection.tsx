import { DesktopInstallerPanel } from './desktop-installer-panel';
import { SettingsSectionHeader } from './SettingsSectionHeader';
import type { SettingsTranslator } from './settings-page-model';

export function AiDoDesktopSettingsSection({
  t,
}: {
  t: SettingsTranslator;
}) {
  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.aiDoDesktop')}
        description={t('auth:settings.aiDoDesktopSettingsDescription')}
      />

      <div className="border-t border-app-border">
        <DesktopInstallerPanel />
      </div>
    </div>
  );
}
