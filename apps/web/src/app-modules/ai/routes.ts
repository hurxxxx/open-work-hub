import { createElement, lazy, type ReactNode } from 'react';

import { chatbotWorkspaceRoutes } from '@/src/app-modules/chatbot';
import { webSearchWorkspaceRoutes } from '@/src/app-modules/web-search';
import { WorkspaceFeatureAppGate } from '@/src/app/shell/gates';
import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const RagSearchView = lazy(() =>
  import('./views/RagSearchView').then((module) => ({
    default: module.RagSearchView,
  })),
);
const ImageWizardToolView = lazy(() =>
  import('./views/ImageWizard/ImageWizardToolView').then((module) => ({
    default: module.ImageWizardToolView,
  })),
);
const EmailAssistantView = lazy(() =>
  import('./views/EmailAssistantView').then((module) => ({
    default: module.EmailAssistantView,
  })),
);

export const ragSearchToolElement = lazyRoute(createElement(RagSearchView));
export const imageWizardToolElement = lazyRoute(
  createElement(ImageWizardToolView),
);
export const emailAssistantToolElement = lazyRoute(
  createElement(EmailAssistantView),
);
export const aiToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'ai',
    element: ragSearchToolElement,
    gates: [{ type: 'workspace_search' }],
    id: 'ai.workspace-search',
    match: ({ toolId }) => toolId === 'search',
    toolIds: ['search'],
    type: 'element',
  },
];

function withFeatureAppGate(
  featureAppId: string,
  element: ReactNode,
): ReactNode {
  return createElement(WorkspaceFeatureAppGate, {
    appId: featureAppId,
    children: element,
  });
}

function rewriteChatbotWorkspaceRoute(
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  return {
    ...route,
    appId: 'ai',
    bootstrapAppId: 'chatbot',
    element: withFeatureAppGate('chatbot', route.element),
    path: route.path,
  };
}

function rewriteWebSearchWorkspaceRoute(
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  return rewriteAiFeatureWorkspaceRoute(route, 'web-search');
}

function rewriteAiFeatureWorkspaceRoute(
  route: WorkspaceRouteDefinition,
  featureAppId: WorkspaceRouteDefinition['appId'],
): WorkspaceRouteDefinition {
  return {
    ...route,
    appId: 'ai',
    bootstrapAppId: featureAppId,
    element: withFeatureAppGate(featureAppId, route.element),
    path: route.path,
  };
}

export const aiGlobalRoutes: StaticRouteDefinition[] = [];

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  ...chatbotWorkspaceRoutes.map(rewriteChatbotWorkspaceRoute),
  ...webSearchWorkspaceRoutes.map(rewriteWebSearchWorkspaceRoute),
];
