import { createElement, type ReactNode } from 'react';

import {
  dataVizToolViewRoutes,
  dataVizWorkspaceRoutes,
} from '@/src/app-modules/data-viz';
import { learningWorkspaceRoutes } from '@/src/app-modules/learning';
import { legacyIssuesWorkspaceRoutes } from '@/src/app-modules/legacy-issues';
import { mealInvoiceOcrWorkspaceRoutes } from '@/src/app-modules/meal-invoice-ocr';
import { patentAutomationWorkspaceRoutes } from '@/src/app-modules/patent-automation';
import { plmWorkspaceRoutes } from '@/src/app-modules/plm';
import type { CompiledFeatureShellRegistration } from '@/src/app/shell/feature-module-registry';
import { WorkspaceFeatureAppGate } from '@/src/app/shell/gates';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';
import { businessFeatureShellRegistrations } from './feature-modules';

const BUSINESS_APP_ID = 'business' as const;

function withFeatureAppGate(
  featureAppId: string,
  element: ReactNode,
): ReactNode {
  return createElement(WorkspaceFeatureAppGate, {
    appId: featureAppId,
    children: element,
  });
}

function rewriteWorkspaceRoute(
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  const featureAppId = route.bootstrapAppId ?? route.appId;
  return {
    ...route,
    appId: BUSINESS_APP_ID,
    bootstrapAppId: featureAppId,
    path: route.path,
    element: withFeatureAppGate(featureAppId, route.element),
  };
}

function rewriteFeatureShellToolRoute(
  registration: CompiledFeatureShellRegistration,
): WorkspaceRouteDefinition & ToolViewRouteDefinition {
  const { appId, navItem, toolRoute } = registration;
  const gatedElement = withFeatureAppGate(appId, toolRoute.element);
  return {
    appId: BUSINESS_APP_ID,
    bootstrapAppId: appId,
    element: gatedElement,
    gates: [
      {
        deniedReason: 'app_disabled',
        navItemId: navItem.id,
        type: 'bootstrap_nav_item',
      },
    ],
    id: toolRoute.id,
    match: ({ toolId }) => toolRoute.toolIds.includes(toolId),
    path: toolRoute.path,
    subSidebar: toolRoute.subSidebar,
    toolIds: toolRoute.toolIds,
    type: 'element',
  } as WorkspaceRouteDefinition & ToolViewRouteDefinition;
}

function rewriteFeatureShellWorkspaceRoute(
  registration: CompiledFeatureShellRegistration,
  route: CompiledFeatureShellRegistration['workspaceRoutes'][number],
): WorkspaceRouteDefinition {
  return {
    appId: BUSINESS_APP_ID,
    bootstrapAppId: registration.appId,
    element: withFeatureAppGate(registration.appId, route.element),
    path: route.path,
    subSidebar: route.subSidebar,
  };
}

function rewriteBusinessToolRoute(
  route: ToolViewRouteDefinition,
): ToolViewRouteDefinition {
  const navItemId = route.toolIds?.[0];
  return {
    ...route,
    appId: BUSINESS_APP_ID,
    bootstrapAppId: route.bootstrapAppId ?? route.appId,
    gates: [
      ...(route.type === 'element' ? (route.gates ?? []) : []),
      ...(navItemId
        ? [
            {
              deniedReason: 'app_disabled' as const,
              navItemId,
              type: 'bootstrap_nav_item' as const,
            },
          ]
        : []),
    ],
  } as ToolViewRouteDefinition;
}

const businessToolRoutes = businessFeatureShellRegistrations.map(
  rewriteFeatureShellToolRoute,
);

const businessFeatureWorkspaceRoutes =
  businessFeatureShellRegistrations.flatMap((registration) =>
    registration.workspaceRoutes.map((route) =>
      rewriteFeatureShellWorkspaceRoute(registration, route),
    ),
  );

export const businessWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  ...plmWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...learningWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...dataVizWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...patentAutomationWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...legacyIssuesWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...mealInvoiceOcrWorkspaceRoutes.map(rewriteWorkspaceRoute),
  ...businessToolRoutes,
  ...businessFeatureWorkspaceRoutes,
];

export const businessToolViewRoutes: ToolViewRouteDefinition[] = [
  ...businessToolRoutes,
  ...dataVizToolViewRoutes.map(rewriteBusinessToolRoute),
];
