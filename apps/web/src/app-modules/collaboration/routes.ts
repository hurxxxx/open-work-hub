import { createElement, type ReactNode } from 'react';

import { bentoWorkspaceRoutes } from '@/src/app-modules/bento';

import {
  docsGlobalRoutes,
  docsToolViewRoutes,
  docsWorkspaceRoutes,
} from '@/src/app-modules/docs';
import {
  diagramsToolViewRoutes,
  diagramsWorkspaceRoutes,
} from '@/src/app-modules/diagrams';
import { filesWorkspaceRoutes } from '@/src/app-modules/files';
import { meetingWorkspaceRoutes } from '@/src/app-modules/meeting';
import { pmsToolViewRoutes, pmsWorkspaceRoutes } from '@/src/app-modules/pms';
import { recordingWorkspaceRoutes } from '@/src/app-modules/recording';
import { videoChatWorkspaceRoutes } from '@/src/app-modules/video-chat';
import {
  whiteboardGlobalRoutes,
  whiteboardToolViewRoutes,
  whiteboardWorkspaceRoutes,
} from '@/src/app-modules/whiteboard';
import { WorkspaceFeatureAppGate } from '@/src/app/shell/gates';
import type {
  AppModuleId,
  NavItem,
  StaticRouteDefinition,
} from '@/src/app/shell/navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';
import { collaborationNavItems } from './manifest';

const COLLABORATION_APP_ID = 'collaboration' as const;

const navFeatureAppIdById = new Map(
  collaborationNavItems.map((item) => {
    const featureAppId =
      item.linkAppId ??
      item.pathSuffix?.match(/^\/([^/?#]+)/)?.[1] ??
      COLLABORATION_APP_ID;
    return [item.id, featureAppId as AppModuleId];
  }),
);
const toolGateNavItemIdByFeatureAppId: Partial<Record<AppModuleId, string>> = {
  docs: 'docs-all',
  pms: 'pms-inbox',
  whiteboard: 'whiteboard-all',
  diagrams: 'diagrams-all',
};

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
  featureAppId: WorkspaceRouteDefinition['appId'],
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  return {
    ...route,
    appId: COLLABORATION_APP_ID,
    bootstrapAppId: featureAppId,
    element: withFeatureAppGate(featureAppId, route.element),
    path: route.path,
  };
}

function rewriteGlobalRoute(
  featureAppId: string,
  route: StaticRouteDefinition,
): StaticRouteDefinition {
  return {
    ...route,
    appId: COLLABORATION_APP_ID,
    bootstrapAppId: route.bootstrapAppId ?? featureAppId,
  };
}

function rewriteToolContextItem(item: NavItem | null): NavItem | null {
  if (!item) {
    return null;
  }
  const featureAppId = navFeatureAppIdById.get(item.id);
  return featureAppId ? { ...item, appId: featureAppId } : item;
}

function rewriteToolRoute(
  route: ToolViewRouteDefinition,
): ToolViewRouteDefinition {
  const match = route.match;
  const wrappedMatch: ToolViewRouteDefinition['match'] = (context) =>
    match({ ...context, item: rewriteToolContextItem(context.item) });
  const featureGateNavItemId =
    toolGateNavItemIdByFeatureAppId[route.appId as AppModuleId] ?? null;
  return {
    ...route,
    appId: COLLABORATION_APP_ID,
    bootstrapAppId: route.bootstrapAppId ?? route.appId,
    gates: [
      ...(route.type === 'element' ? (route.gates ?? []) : []),
      ...(featureGateNavItemId
        ? [
            {
              deniedReason: 'app_disabled' as const,
              navItemId: featureGateNavItemId,
              type: 'bootstrap_nav_item' as const,
            },
          ]
        : []),
    ],
    match: wrappedMatch,
  } as ToolViewRouteDefinition;
}

export const collaborationWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  ...pmsWorkspaceRoutes.map((route) => rewriteWorkspaceRoute('pms', route)),
  ...docsWorkspaceRoutes.map((route) => rewriteWorkspaceRoute('docs', route)),
  ...filesWorkspaceRoutes.map((route) => rewriteWorkspaceRoute('files', route)),
  ...meetingWorkspaceRoutes.map((route) =>
    rewriteWorkspaceRoute('meeting', route),
  ),
  ...whiteboardWorkspaceRoutes.map((route) =>
    rewriteWorkspaceRoute('whiteboard', route),
  ),
  ...diagramsWorkspaceRoutes.map((route) =>
    rewriteWorkspaceRoute('diagrams', route),
  ),
  ...bentoWorkspaceRoutes.map((route) => rewriteWorkspaceRoute('bento', route)),
  ...recordingWorkspaceRoutes.map((route) =>
    rewriteWorkspaceRoute('recording', route),
  ),
  ...videoChatWorkspaceRoutes.map((route) =>
    rewriteWorkspaceRoute('video-chat', route),
  ),
];

export const collaborationToolViewRoutes: ToolViewRouteDefinition[] = [
  ...pmsToolViewRoutes.map(rewriteToolRoute),
  ...docsToolViewRoutes.map(rewriteToolRoute),
  ...whiteboardToolViewRoutes.map(rewriteToolRoute),
  ...diagramsToolViewRoutes.map(rewriteToolRoute),
];

export const collaborationGlobalRoutes: StaticRouteDefinition[] = [
  ...docsGlobalRoutes.map((route) => rewriteGlobalRoute('docs', route)),
  ...whiteboardGlobalRoutes.map((route) =>
    rewriteGlobalRoute('whiteboard', route),
  ),
];
