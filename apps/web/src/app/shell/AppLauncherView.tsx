import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { appIconForKey } from '@/src/platform/apps/app-icons';
import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import {
  resolveAppLaunchDestination,
  translateAppLaunchContext,
  translateAppLaunchLabel,
} from './app-launch-destination';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from './navigation-types';

const LAUNCHER_SECTIONS = [
  { id: 'company', titleKey: 'launcher.companyApp' },
  { id: 'personal', titleKey: 'launcher.personalApp' },
] as const;

export function AppLauncherView({
  data,
  error,
  loading,
}: {
  data: AppsBootstrapResponse | null;
  error: string | null;
  loading: boolean;
}) {
  const { t } = useTranslation('shell');
  const hasNoApps = Boolean(data && !data.apps.some((app) => app.enabled));
  const sections = LAUNCHER_SECTIONS.map((section) => ({
    ...section,
    apps: (data?.apps ?? []).filter((app) => {
      if (!app.enabled) return false;
      return section.id === 'personal'
        ? app.execution_context_kind === 'personal'
        : app.execution_context_kind === 'company';
    }),
  })).filter((section) => section.apps.length > 0);
  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8">
      <p className="app-text-overline text-app-accent">
        {t('launcher.eyebrow')}
      </p>
      <h1 className="app-text-title-xl mt-2 text-app-ink">
        {t('launcher.title')}
      </h1>
      <p className="app-text-body mt-2 max-w-2xl text-app-ink/60">
        {t('launcher.description')}
      </p>

      {loading && !data ? (
        <div
          role="status"
          aria-label={t('common:feedback.loading')}
          className="mt-8 h-40 animate-pulse rounded-2xl bg-app-surface"
        />
      ) : null}
      {error ? (
        <p className="app-text-body mt-8 rounded-xl border border-app-danger/25 bg-app-danger/10 p-4 text-app-danger">
          {error}
        </p>
      ) : null}
      {hasNoApps && !error ? (
        <section className="mt-8 rounded-2xl border border-app-border bg-app-surface p-6 text-center">
          <h2 className="app-text-title-md text-app-ink">
            {t('launcher.noAppsTitle')}
          </h2>
          <p className="app-text-body mt-2 text-app-ink/60">
            {t('launcher.noAppsDescription')}
          </p>
        </section>
      ) : null}
      {sections.map((section) => (
        <section
          aria-labelledby={`launcher-section-${section.id}`}
          className="mt-8"
          key={section.id}
        >
          <h2
            className="app-text-title-md text-app-ink"
            id={`launcher-section-${section.id}`}
          >
            {t(section.titleKey)}
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {section.apps.map((app) => {
              const Icon = appIconForKey(app.icon_key);
              const title = t(`apps.${app.app_id}`, {
                defaultValue: app.title,
              });
              const destination = resolveAppLaunchDestination({
                app,
                appId: app.app_id,
                launcherGlobalPaths: EMPTY_LAUNCHER_GLOBAL_PATHS,
              });
              return (
                <Link
                  aria-label={translateAppLaunchLabel(title, destination, t)}
                  className="group rounded-2xl border border-app-border bg-app-surface p-4 transition hover:-translate-y-0.5 hover:border-app-accent/40 hover:shadow-lg"
                  key={app.app_id}
                  to={destination.href}
                >
                  <span className="flex size-11 items-center justify-center rounded-xl bg-app-accent/12 text-app-accent">
                    <Icon aria-hidden size={21} />
                  </span>
                  <h3 className="app-text-title-sm mt-4 text-app-ink">
                    {title}
                  </h3>
                  <p className="app-text-caption mt-1 text-app-ink/55">
                    {translateAppLaunchContext(destination, t)}
                  </p>
                </Link>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
