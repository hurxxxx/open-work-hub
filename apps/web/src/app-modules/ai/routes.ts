import { createElement, lazy, type ReactNode } from 'react';

import { chatbotWorkspaceRoutes } from '@/src/app-modules/chatbot';
import {
  qaAssistantGlobalRoutes,
  qaAssistantToolViewRoutes,
} from '@/src/app-modules/qa-assistant';
import {
  researchTrendsWorkspaceRoutes,
  standardsMonitorWorkspaceRoutes,
  webSearchWorkspaceRoutes,
} from '@/src/app-modules/web-search';
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
const SpecCompareView = lazy(() =>
  import('./views/SpecCompareView').then((module) => ({
    default: module.SpecCompareView,
  })),
);
const DocumentTranslateView = lazy(() =>
  import('./views/DocumentTranslateView').then((module) => ({
    default: module.DocumentTranslateView,
  })),
);
const FmeaCompareView = lazy(() =>
  import('./views/FmeaCompareView').then((module) => ({
    default: module.FmeaCompareView,
  })),
);
const ImdsMineralsView = lazy(() =>
  import('./views/ImdsMineralsView').then((module) => ({
    default: module.ImdsMineralsView,
  })),
);
const DraftingView = lazy(() =>
  import('./views/DraftingView').then((module) => ({
    default: module.DraftingView,
  })),
);
const EmailAssistantView = lazy(() =>
  import('./views/EmailAssistantView').then((module) => ({
    default: module.EmailAssistantView,
  })),
);
const PatentComposeView = lazy(() =>
  import('./views/PatentComposeView').then((module) => ({
    default: module.PatentComposeView,
  })),
);
const PatentAnalysisView = lazy(() =>
  import('./views/PatentAnalysisView').then((module) => ({
    default: module.PatentAnalysisView,
  })),
);
const LawSearchView = lazy(() =>
  import('./views/lawsearch/LawSearchView').then((module) => ({
    default: module.LawSearchView,
  })),
);

export const ragSearchToolElement = lazyRoute(createElement(RagSearchView));
export const imageWizardToolElement = lazyRoute(
  createElement(ImageWizardToolView),
);
export const specCompareToolElement = lazyRoute(createElement(SpecCompareView));
export const documentTranslateToolElement = lazyRoute(
  createElement(DocumentTranslateView),
);
export const fmeaCompareToolElement = lazyRoute(createElement(FmeaCompareView));
export const imdsMineralsToolElement = lazyRoute(
  createElement(ImdsMineralsView),
);
export const draftingToolElement = lazyRoute(createElement(DraftingView));
export const emailAssistantToolElement = lazyRoute(
  createElement(EmailAssistantView),
);
export const patentComposeToolElement = lazyRoute(
  createElement(PatentComposeView),
);
export const patentAnalysisToolElement = lazyRoute(
  createElement(PatentAnalysisView),
);
export const lawSearchToolElement = lazyRoute(createElement(LawSearchView));

function rewriteAiToolRoute(
  route: ToolViewRouteDefinition,
): ToolViewRouteDefinition {
  return {
    ...route,
    appId: 'ai',
    bootstrapAppId: route.bootstrapAppId ?? route.appId,
    gates: [
      ...(route.type === 'element' ? (route.gates ?? []) : []),
      {
        deniedReason: 'app_disabled',
        navItemId: 'qa-assistant',
        type: 'bootstrap_nav_item',
      },
    ],
  } as ToolViewRouteDefinition;
}

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
  ...qaAssistantToolViewRoutes.map(rewriteAiToolRoute),
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

function rewriteResearchTrendsWorkspaceRoute(
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  return rewriteAiFeatureWorkspaceRoute(route, 'research-trends');
}

function rewriteStandardsMonitorWorkspaceRoute(
  route: WorkspaceRouteDefinition,
): WorkspaceRouteDefinition {
  return rewriteAiFeatureWorkspaceRoute(route, 'standards-monitor');
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

export const aiGlobalRoutes: StaticRouteDefinition[] = [
  ...qaAssistantGlobalRoutes,
];

export const aiWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  ...chatbotWorkspaceRoutes.map(rewriteChatbotWorkspaceRoute),
  ...webSearchWorkspaceRoutes.map(rewriteWebSearchWorkspaceRoute),
  ...researchTrendsWorkspaceRoutes.map(rewriteResearchTrendsWorkspaceRoute),
  ...standardsMonitorWorkspaceRoutes.map(rewriteStandardsMonitorWorkspaceRoute),
];
