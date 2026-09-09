import { NOTIFICATION_REALTIME_EVENT_TYPE_VALUES } from '@open-work-hub/contracts/notifications';
import { FeedbackProvider } from '@open-work-hub/ui';
import { lazy, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { BrowserRouter as Router } from 'react-router-dom';

import { pmsManifest } from '../app-modules/pms';
import { resolveShellState } from '../app-shell';
import { NotificationPanel } from '../components/layout/NotificationPanel';
import { getUnreadNotificationCount } from '../platform/notifications/notifications-api';
import {
  RealtimeProvider,
  useRealtime,
} from '../platform/realtime/realtime-provider';
import {
  AI_TOOL_APP_IDS,
  APP_BACKGROUND_WORK_SOURCES,
  APP_BAR_FIXED_APP_IDS,
  APP_BAR_ITEMS,
  APP_BAR_PINNED_BY_DEFAULT_APP_IDS,
  APP_FEATURE_GUIDE_TOOL_IDS,
  APP_GLOBAL_ROUTES,
  APP_LAUNCHER_GLOBAL_PATHS,
  APP_ROUTES,
  APP_SHELL_PROVIDERS,
  getAppModuleManifest,
  getAppModuleSidebarConfig,
  NAV_ITEMS,
} from './shell/app-registry';
import {
  staticAdminLandingRoute,
  staticAdminRedirectRoutes,
  staticAdminSectionRoutes,
} from './shell/app-route-definitions';
import { AppContent } from './shell/AppContent';
import { ShellRealtimeProvider } from './shell/shell-realtime-context';

type RegisteredAppId = Parameters<typeof getAppModuleManifest>[0];

const DefaultShellPersonalWidgetHost = lazy(() =>
  import('./shell/personal-widget-registry').then((module) => ({
    default: module.ShellPersonalWidgetHost,
  })),
);

const getDefaultAppModuleManifest = (appId: string) =>
  getAppModuleManifest(appId as RegisteredAppId);

const NOTIFICATION_REALTIME_EVENT_TYPE_SET = new Set<string>(
  NOTIFICATION_REALTIME_EVENT_TYPE_VALUES,
);

function ShellRealtimeBridge({ children }: { children: ReactNode }) {
  const realtime = useRealtime();
  return (
    <ShellRealtimeProvider value={realtime}>{children}</ShellRealtimeProvider>
  );
}

function DefaultShellRealtimeProvider({
  children,
  token,
}: {
  children: ReactNode;
  token: string | null;
}) {
  return (
    <RealtimeProvider token={token}>
      <ShellRealtimeBridge>{children}</ShellRealtimeBridge>
    </RealtimeProvider>
  );
}

export default function AppRoot() {
  const { t } = useTranslation('common');

  return (
    <FeedbackProvider
      labels={{
        close: t('actions.close'),
        item: t('feedback.itemLabel'),
        region: t('feedback.regionLabel'),
      }}
    >
      <Router>
        <AppContent
          adminLandingRoute={staticAdminLandingRoute}
          adminRedirectRoutes={staticAdminRedirectRoutes}
          adminSectionRoutes={staticAdminSectionRoutes}
          appBarItems={APP_BAR_ITEMS}
          appBarFixedAppIds={APP_BAR_FIXED_APP_IDS}
          appBarPinnedByDefaultAppIds={APP_BAR_PINNED_BY_DEFAULT_APP_IDS}
          appGlobalRoutes={APP_GLOBAL_ROUTES}
          backgroundWorkSources={APP_BACKGROUND_WORK_SOURCES}
          featureGuideToolIds={APP_FEATURE_GUIDE_TOOL_IDS}
          getAppModuleManifest={getDefaultAppModuleManifest}
          getAppSidebarConfig={getAppModuleSidebarConfig}
          launcherGlobalPaths={APP_LAUNCHER_GLOBAL_PATHS}
          navItems={NAV_ITEMS}
          notificationIssueAppId={pmsManifest.appBarItem.id}
          notificationPanel={NotificationPanel}
          notificationRealtimeEventTypes={NOTIFICATION_REALTIME_EVENT_TYPE_SET}
          notificationUnreadCountLoader={getUnreadNotificationCount}
          personalWidgetHost={DefaultShellPersonalWidgetHost}
          realtimeProvider={DefaultShellRealtimeProvider}
          resolveShellStateForPath={resolveShellState}
          shellProviders={APP_SHELL_PROVIDERS}
          appRoutes={APP_ROUTES}
          aiToolAppIds={AI_TOOL_APP_IDS}
        />
      </Router>
    </FeedbackProvider>
  );
}
