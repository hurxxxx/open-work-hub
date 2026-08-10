import { useTranslation } from 'react-i18next';
import {
  Apple,
  BadgeCheck,
  Download,
  Monitor,
  Terminal,
} from 'lucide-react';

import { Button } from '@ai-do/ui/primitives/button';

import {
  buildDesktopInstallerRows,
  downloadDesktopInstaller,
  type DesktopInstallerIcon,
} from './desktop-installer';

const desktopInstallerIcons: Record<DesktopInstallerIcon, typeof Monitor> = {
  monitor: Monitor,
  apple: Apple,
  terminal: Terminal,
};

const desktopInstallerIconFallbacks: Record<string, typeof Monitor> = {
  win: Monitor,
  mac: Apple,
  linux: Terminal,
};

function desktopInstallerIcon(
  icon: DesktopInstallerIcon,
  platform: string,
): typeof Monitor {
  if (icon in desktopInstallerIcons) return desktopInstallerIcons[icon];
  return desktopInstallerIconFallbacks[platform] ?? Monitor;
}

type DesktopInstallerCatalogRow = ReturnType<typeof buildDesktopInstallerRows>[number];

type DesktopInstallerPanelRow = Omit<DesktopInstallerCatalogRow, 'icon'> & {
  Icon: typeof Monitor;
};

export function DesktopInstallerPanel() {
  const { t } = useTranslation('auth');
  const rows: DesktopInstallerPanelRow[] = buildDesktopInstallerRows().map((row) => ({
    ...row,
    Icon: desktopInstallerIcon(row.icon, row.platform),
  }));

  return (
    <div className="mt-4 rounded-md border border-app-border bg-app-surface-subtle p-4">
      <div>
        <div className="app-text-body font-medium text-app-ink">
          {t('settings.aiDoDesktopTitle')}
        </div>
        <div className="app-text-caption mt-0.5 text-app-ink/55">
          {t('settings.aiDoDesktopDescription')}
        </div>
      </div>

      <div className="mt-4 divide-y divide-app-border">
        {rows.map((item) => {
          const platformName = t(item.titleKey);

          return (
            <div
              key={item.platform}
              className="flex flex-col gap-3 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="flex min-w-0 gap-3">
                <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink">
                  <item.Icon size={16} />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="app-text-body font-medium text-app-ink">{platformName}</span>
                    {item.isCurrent ? (
                      <span className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-accent/30 bg-app-accent/10 px-2 py-0.5 text-app-accent">
                        <BadgeCheck size={12} />
                        {t('settings.aiDoDesktopCurrentOs')}
                      </span>
                    ) : null}
                  </div>
                  <p className="app-text-caption mt-1 text-app-ink/55">
                    {t(item.descriptionKey)}
                  </p>
                  <p className="app-text-caption mt-1 text-app-ink/55">
                    {t(item.guideKey)}
                  </p>
                </div>
              </div>

              <Button
                className="shrink-0 sm:self-start"
                disabled={!item.installerUrl}
                onClick={() => {
                  if (!item.installerUrl) return;
                  downloadDesktopInstaller(item.installerUrl);
                }}
                variant={item.isCurrent ? 'primary' : 'secondary'}
              >
                <Download size={14} />
                {item.installerUrl
                  ? t('settings.aiDoDesktopDownload', {
                      platform: platformName,
                    })
                  : t('settings.aiDoDesktopUnavailable')}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
