import { createElement, lazy, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  LEGACY_ISSUE_ASSISTANT_HISTORY_ROUTE_PATH,
  LEGACY_ISSUE_ASSISTANT_ROUTE_PATH,
  LEGACY_ISSUE_COMMON_CODE_ROUTE_PATH,
  LEGACY_ISSUE_DEFAULT_VIEW_KEY,
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
  LEGACY_ISSUE_FIELD_SETTINGS_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_CHECKLISTS_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_CHECKLIST_DETAIL_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_MANAGEMENT_ROUTE_PATH,
  LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH,
  LEGACY_ISSUE_REPORTS_PATH_SUFFIX,
  LEGACY_ISSUE_REPORTS_ROUTE_PATH,
  LEGACY_ISSUE_VIEWS,
  LEGACY_ISSUE_VIEW_KEYS,
  type LegacyIssueViewKey,
} from './core/public-api';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

const LegacyIssueDatasetView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueDatasetView,
  })),
);
const LegacyIssueAssistantView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueAssistantView,
  })),
);
const LegacyIssueReportManagementView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueReportManagementView,
  })),
);
const LegacyIssueReportDetailView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueReportDetailView,
  })),
);
const LegacyIssueFieldSettingsView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueFieldSettingsView,
  })),
);
const LegacyIssueCommonCodeView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueCommonCodeView,
  })),
);
const LegacyIssueDirectEditPermissionsView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueDirectEditPermissionsView,
  })),
);
const LegacyIssueVehicleChecklistView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueVehicleChecklistView,
  })),
);
const LegacyIssueVehicleModuleChecklistView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueVehicleModuleChecklistView,
  })),
);
const LegacyIssueVehicleManagementView = lazy(() =>
  import('./core/public-api').then((module) => ({
    default: module.CoreBusinessLegacyIssueVehicleManagementView,
  })),
);

const legacyIssueAssistantElement = lazyRoute(
  createElement(LegacyIssueAssistantView),
);
const legacyIssueReportManagementElement = lazyRoute(
  createElement(LegacyIssueReportManagementView),
);
const legacyIssueReportDetailElement = lazyRoute(
  createElement(LegacyIssueReportDetailView),
);
const legacyIssueFieldSettingsElement = lazyRoute(
  createElement(LegacyIssueFieldSettingsView),
);
const legacyIssueCommonCodeElement = lazyRoute(
  createElement(LegacyIssueCommonCodeView),
);
const legacyIssueDirectEditPermissionsElement = lazyRoute(
  createElement(
    LegacyIssuePlatformAdminRoute,
    null,
    createElement(LegacyIssueDirectEditPermissionsView),
  ),
);
const legacyIssueVehicleChecklistElement = lazyRoute(
  createElement(LegacyIssueVehicleChecklistView),
);
const legacyIssueVehicleModuleChecklistElement = lazyRoute(
  createElement(LegacyIssueVehicleModuleChecklistView),
);
const legacyIssueVehicleManagementElement = lazyRoute(
  createElement(LegacyIssueVehicleManagementView),
);

const COMPRESSOR_VIEW_KEYS = new Set<LegacyIssueViewKey>([
  'compressor-mechanical',
  'compressor-electric',
]);

export function isLegacyIssueViewAvailable(
  viewKey: LegacyIssueViewKey,
  navItems: readonly { id: string }[] | null | undefined,
): boolean {
  if (!COMPRESSOR_VIEW_KEYS.has(viewKey)) {
    return true;
  }
  return (navItems ?? []).some(
    (item) => item.id === LEGACY_ISSUE_VIEWS[viewKey].navItemId,
  );
}

function LegacyIssueDatasetRoute({
  children,
  viewKey,
}: {
  children?: ReactNode;
  viewKey: LegacyIssueViewKey;
}) {
  const { t } = useTranslation('shell');
  const workspaceBootstrap = useWorkspaceBootstrapContext();

  if (!COMPRESSOR_VIEW_KEYS.has(viewKey)) {
    return children;
  }
  if (workspaceBootstrap.loading) {
    return createElement(
      'div',
      { className: 'p-8 text-app-ink/55' },
      t('gates.workspaceLoading'),
    );
  }
  if (workspaceBootstrap.error) {
    return createElement(AccessDeniedView, {
      description: workspaceBootstrap.error,
    });
  }
  if (!isLegacyIssueViewAvailable(viewKey, workspaceBootstrap.data?.nav)) {
    return createElement(AccessDeniedView, {
      description: t('gates.appDisabled'),
    });
  }
  return children;
}

function LegacyIssuePlatformAdminRoute({ children }: { children?: ReactNode }) {
  const { status, user } = useAuth();
  const { t } = useTranslation('shell');

  if (status === 'bootstrapping') {
    return createElement(
      'div',
      { className: 'p-8 text-app-ink/55' },
      t('gates.workspaceLoading'),
    );
  }
  if (!hasAdminConsoleAccess(user)) {
    return createElement(AccessDeniedView, {
      description: t('gates.adminSectionDenied'),
    });
  }
  return children;
}

function legacyIssueDatasetElement(viewKey: LegacyIssueViewKey) {
  const view = LEGACY_ISSUE_VIEWS[viewKey];
  return lazyRoute(
    createElement(
      LegacyIssueDatasetRoute,
      {
        key: viewKey,
        viewKey,
      },
      createElement(LegacyIssueDatasetView, {
        datasetKey: view.datasetKey,
        viewKey,
      }),
    ),
  );
}

function LegacyIssuesRootRedirect() {
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  return createElement(Navigate, {
    replace: true,
    to: workspaceSlug
      ? buildWorkspaceAppPath(
          workspaceSlug,
          'legacy-issues',
          LEGACY_ISSUE_VIEWS[LEGACY_ISSUE_DEFAULT_VIEW_KEY].pathSuffix,
        )
      : '/',
  });
}

function LegacyIssueAssistantHistoryRedirect() {
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  return createElement(Navigate, {
    replace: true,
    to: workspaceSlug
      ? buildWorkspaceAppPath(
          workspaceSlug,
          'legacy-issues',
          LEGACY_ISSUE_REPORTS_PATH_SUFFIX,
        )
      : '/',
  });
}

export const legacyIssuesWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'legacy-issues',
    path: '/w/:workspaceSlug/legacy-issues',
    element: createElement(LegacyIssuesRootRedirect),
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_ASSISTANT_ROUTE_PATH,
    element: legacyIssueAssistantElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_ASSISTANT_HISTORY_ROUTE_PATH,
    element: createElement(LegacyIssueAssistantHistoryRedirect),
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_REPORTS_ROUTE_PATH,
    element: legacyIssueReportManagementElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH,
    element: legacyIssueReportDetailElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_FIELD_SETTINGS_ROUTE_PATH,
    element: legacyIssueFieldSettingsElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_COMMON_CODE_ROUTE_PATH,
    element: legacyIssueCommonCodeElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
    element: legacyIssueDirectEditPermissionsElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_VEHICLE_CHECKLISTS_ROUTE_PATH,
    element: legacyIssueVehicleChecklistElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_VEHICLE_CHECKLIST_DETAIL_ROUTE_PATH,
    element: legacyIssueVehicleChecklistElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH,
    element: legacyIssueVehicleModuleChecklistElement,
  },
  {
    appId: 'legacy-issues',
    path: LEGACY_ISSUE_VEHICLE_MANAGEMENT_ROUTE_PATH,
    element: legacyIssueVehicleManagementElement,
  },
  ...LEGACY_ISSUE_VIEW_KEYS.map((viewKey) => ({
    appId: 'legacy-issues' as const,
    path: LEGACY_ISSUE_VIEWS[viewKey].routePath,
    element: legacyIssueDatasetElement(viewKey),
  })),
];
