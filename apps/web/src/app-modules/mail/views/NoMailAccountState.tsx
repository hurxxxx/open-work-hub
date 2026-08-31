import { Settings } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';

import { actionButtonClassName } from './mail-view-model';

export function NoMailAccountState() {
  const { t } = useTranslation('apps');
  return (
    <main className="flex flex-1 items-start justify-center overflow-auto p-6">
      <div className="w-full max-w-xl rounded-md border border-app-border bg-app-surface p-5">
        <Settings className="mb-3 size-7 text-app-ink/45" />
        <h2 className="app-text-title-md">{t('mail.account.emptyTitle')}</h2>
        <p className="app-text-body mt-1 text-app-ink/60">
          {t('mail.account.emptyDescription')}
        </p>
        <Link
          className={`${actionButtonClassName} mt-4`}
          to={buildAppHref({
            routeId: 'mail.root',
            queryParams: { view: 'settings' },
          })}
        >
          <Settings size={16} />
          <span>{t('mail.account.openSettings')}</span>
        </Link>
      </div>
    </main>
  );
}
