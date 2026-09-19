import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { useTranslation } from 'react-i18next';
import { useAppBootstrapContext } from '@/src/platform/apps/app-bootstrap-context';
import { codexConsoleManifest } from './manifest';

function CodexConsoleEntry() {
  const { t } = useTranslation('shell');
  const { data } = useAppBootstrapContext();
  const app = data?.apps.find(
    (item) => item.app_id === 'codex-console' && item.enabled,
  );
  return (
    <section className="p-8">
      <h1 className="app-text-title-lg">{t('apps.codex-console')}</h1>
      <p className="app-text-body my-4">{t('launcher.consoleSignIn')}</p>
      {app?.launch_url ? (
        <a
          className="text-app-accent underline"
          href={app.launch_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('launcher.openAppInNewTab', { app: t('apps.codex-console') })}
        </a>
      ) : (
        <p>{t('launcher.appUnavailable')}</p>
      )}
    </section>
  );
}

export const codexConsoleModule = {
  manifest: codexConsoleManifest,
  globalRoutes: [
    {
      path: getAppRoutePattern('codex-console.root'),
      chrome: 'containedSurface' as const,
      element: <CodexConsoleEntry />,
    },
  ],
};
