import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';

import { SettingsSectionHeader } from './SettingsSectionHeader';
import type { SettingsTranslator } from './settings-page-model';

export function NotificationsSettingsSection({ t }: { t: SettingsTranslator }) {
  const items = [
    {
      title: t('auth:settings.notificationsCompanyTitle'),
      desc: t('auth:settings.notificationsCompanyDescription'),
      email: true,
      push: true,
    },
    {
      title: t('auth:settings.notificationsSecurityTitle'),
      desc: t('auth:settings.notificationsSecurityDescription'),
      email: true,
      push: true,
    },
    {
      title: t('auth:settings.notificationsWeeklyTitle'),
      desc: t('auth:settings.notificationsWeeklyDescription'),
      email: true,
      push: false,
    },
  ];

  return (
    <div>
      <SettingsSectionHeader
        title={t('auth:settings.notifications')}
        description={t('auth:settings.notificationsDescription')}
      />

      <div className="border-t border-app-border">
        <InlineNotice tone="warning" className="mt-4">
          {t('auth:settings.notificationsNotConnected')}
        </InlineNotice>

        {items.map((item) => (
          <div
            key={item.title}
            className="flex items-center justify-between border-b border-app-border py-4 last:border-b-0"
          >
            <div>
              <div className="app-text-body font-medium text-app-ink">
                {item.title}
              </div>
              <div className="app-text-caption mt-0.5 text-app-ink/55">
                {item.desc}
              </div>
            </div>
            <div className="flex items-center gap-5">
              <label className="flex cursor-pointer items-center gap-1.5">
                <input
                  className="size-3.5 rounded border-app-border bg-app-bg accent-app-accent"
                  aria-label={t('auth:settings.notificationsChannelEmail')}
                  defaultChecked={item.email}
                  type="checkbox"
                />
                <span className="app-text-caption text-app-ink/55">
                  {t('auth:settings.notificationsChannelEmail')}
                </span>
              </label>
              <label className="flex cursor-pointer items-center gap-1.5">
                <input
                  className="size-3.5 rounded border-app-border bg-app-bg accent-app-accent"
                  aria-label={t('auth:settings.notificationsChannelPush')}
                  defaultChecked={item.push}
                  type="checkbox"
                />
                <span className="app-text-caption text-app-ink/55">
                  {t('auth:settings.notificationsChannelPush')}
                </span>
              </label>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
