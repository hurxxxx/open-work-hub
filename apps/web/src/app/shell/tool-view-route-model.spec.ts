import { describe, expect, it } from 'vitest';

import {
  resolveToolRedirectAppRootPath,
  resolveToolViewRouteDecision,
  type ToolViewRouteItem,
} from './tool-view-route-model';

const betaItem: ToolViewRouteItem = { appId: 'chatbot' };
const docsItem: ToolViewRouteItem = { appId: 'docs' };
const homeItem: ToolViewRouteItem = { appId: 'home' };
const docsRoute = {
  appId: 'docs',
  id: 'docs.main',
  type: 'element',
} as const;
const pmsRoute = {
  appId: 'pms',
  id: 'pms.main',
  type: 'element',
} as const;
const ragSearchRoute = {
  appId: 'ai',
  gates: [{ type: 'workspace_search' }],
  id: 'ai.workspace-search',
  type: 'element',
} as const;
const imageWizardRoute = {
  appId: 'chatbot',
  gates: [
    {
      deniedReason: 'image_wizard_disabled',
      navItemId: 'image-wizard',
      type: 'bootstrap_nav_item',
    },
  ],
  id: 'chatbot.image-wizard',
  type: 'element',
} as const;
const genericBootstrapGatedRoute = {
  appId: 'chatbot',
  gates: [
    {
      deniedReason: 'workspace_search_disabled',
      navItemId: 'generic-feature',
      type: 'bootstrap_nav_item',
    },
  ],
  id: 'chatbot.generic-feature',
  type: 'element',
} as const;
const customUngatedRoute = {
  appId: 'chatbot',
  id: 'chatbot.custom-tool',
  type: 'element',
} as const;

const enabledApps = [
  { app_id: 'chatbot', enabled: true },
  { app_id: 'docs', enabled: true },
  { app_id: 'pms', enabled: true },
  { app_id: 'whiteboard', enabled: true },
];

function decision(
  overrides: Partial<Parameters<typeof resolveToolViewRouteDecision>[0]> = {},
) {
  return resolveToolViewRouteDecision({
    enabledBootstrapApps: enabledApps,
    enabledBootstrapNav: [{ id: 'image-wizard' }],
    hasAnyWorkspaceMembership: true,
    hasRequestedWorkspaceMembership: true,
    hasToolWorkspaceMembership: true,
    item: docsItem,
    matchedToolRoute: docsRoute,
    requestedToolWorkspaceSlug: null,
    toolId: 'docs-all',
    workspaceBootstrapError: null,
    workspaceBootstrapLoading: false,
    ...overrides,
  });
}

describe('tool view route model', () => {
  it('routes matched PMS nav tools through the PMS element', () => {
    expect(
      decision({
        item: { appId: 'pms' },
        matchedToolRoute: pmsRoute,
        toolId: 'pms-inbox',
      }),
    ).toEqual({
      routeId: 'pms.main',
      type: 'tool_element',
    });
    expect(
      decision({
        hasAnyWorkspaceMembership: false,
        item: { appId: 'pms' },
        matchedToolRoute: pmsRoute,
        toolId: 'pms-inbox',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'tool_workspace_denied',
    });
  });

  it('redirects app roots into the validated tool workspace when present', () => {
    const user = {
      default_workspace_id: 'default-workspace-id',
      workspaces: [
        { id: 'default-workspace-id', name: 'Default', slug: 'default' },
        { id: 'requested-workspace-id', name: 'HQ', slug: 'hq' },
      ],
    };

    expect(
      resolveToolRedirectAppRootPath({
        appId: 'pms',
        toolWorkspaceSlug: 'hq',
        user,
      }),
    ).toBe('/w/hq/pms');
    expect(
      resolveToolRedirectAppRootPath({
        appId: 'pms',
        toolWorkspaceSlug: null,
        user,
      }),
    ).toBe('/w/default/pms');
  });

  it('rejects missing or unauthorized workspace routing contexts', () => {
    expect(
      decision({ item: null, matchedToolRoute: null, toolId: 'missing' }),
    ).toEqual({
      type: 'not_found',
    });
    expect(
      decision({
        hasAnyWorkspaceMembership: false,
        item: docsItem,
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'tool_workspace_denied',
    });
    expect(
      decision({
        hasRequestedWorkspaceMembership: false,
        requestedToolWorkspaceSlug: 'other-workspace',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'tool_workspace_denied',
    });
    expect(
      decision({
        hasAnyWorkspaceMembership: false,
        item: homeItem,
        matchedToolRoute: null,
        requestedToolWorkspaceSlug: null,
        toolId: 'home',
      }),
    ).toEqual({ type: 'tool_view' });
  });

  it('gates Chatbot tools on workspace bootstrap state', () => {
    expect(
      decision({
        item: betaItem,
        hasToolWorkspaceMembership: false,
        matchedToolRoute: null,
        toolId: 'chatbot',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'tool_workspace_denied',
    });
    expect(
      decision({
        enabledBootstrapApps: null,
        item: betaItem,
        matchedToolRoute: null,
        toolId: 'chatbot',
        workspaceBootstrapLoading: true,
      }),
    ).toEqual({ type: 'loading' });
    expect(
      decision({
        item: betaItem,
        matchedToolRoute: null,
        toolId: 'chatbot',
        workspaceBootstrapError: 'Bootstrap failed',
      }),
    ).toEqual({ type: 'access_denied_message', message: 'Bootstrap failed' });
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'docs', enabled: true }],
        item: betaItem,
        matchedToolRoute: null,
        toolId: 'chatbot',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'app_disabled',
    });
  });

  it('selects dedicated tool elements and feature gates', () => {
    expect(
      decision({
        item: { appId: 'pms' },
        matchedToolRoute: pmsRoute,
        toolId: 'pms-tasks',
      }),
    ).toEqual({
      routeId: 'pms.main',
      type: 'tool_element',
    });
    expect(decision({ item: docsItem, toolId: 'docs-all' })).toEqual({
      routeId: 'docs.main',
      type: 'tool_element',
    });
    expect(
      decision({
        item: { appId: 'whiteboard' },
        matchedToolRoute: {
          appId: 'whiteboard',
          id: 'whiteboard.main',
          type: 'element',
        },
        toolId: 'whiteboard-all',
      }),
    ).toEqual({
      routeId: 'whiteboard.main',
      type: 'tool_element',
    });
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'docs', enabled: true }],
        item: betaItem,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceKeywordSearchEntityTypes: [{ value: 'doc' }],
      }),
    ).toEqual({
      routeId: 'ai.workspace-search',
      type: 'tool_element',
    });
    expect(
      decision({
        enabledBootstrapApps: [
          { app_id: 'chatbot', enabled: false },
          { app_id: 'docs', enabled: true },
        ],
        item: betaItem,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceKeywordSearchEntityTypes: [{ value: 'doc' }],
      }),
    ).toEqual({
      routeId: 'ai.workspace-search',
      type: 'tool_element',
    });
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'chatbot', enabled: true }],
        item: betaItem,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceKeywordSearchEntityTypes: [],
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'workspace_search_disabled',
    });
    expect(
      decision({
        enabledBootstrapApps: [
          { app_id: 'chatbot', enabled: true },
          { app_id: 'mail', enabled: true },
        ],
        item: betaItem,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceKeywordSearchEntityTypes: [],
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'workspace_search_disabled',
    });
    expect(
      decision({
        item: betaItem,
        matchedToolRoute: imageWizardRoute,
        toolId: 'image-wizard',
      }),
    ).toEqual({
      routeId: 'chatbot.image-wizard',
      type: 'tool_element',
    });
    expect(
      decision({
        enabledBootstrapNav: [],
        item: betaItem,
        matchedToolRoute: imageWizardRoute,
        toolId: 'image-wizard',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'image_wizard_disabled',
    });
    expect(
      decision({
        enabledBootstrapNav: [],
        item: betaItem,
        matchedToolRoute: genericBootstrapGatedRoute,
        toolId: 'generic-feature',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'workspace_search_disabled',
    });
    expect(
      decision({
        item: betaItem,
        matchedToolRoute: customUngatedRoute,
        toolId: 'custom-tool',
      }),
    ).toEqual({
      routeId: 'chatbot.custom-tool',
      type: 'tool_element',
    });
  });

  it('keeps workspace context checks on the source-gated search route', () => {
    expect(
      decision({
        hasToolWorkspaceMembership: false,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceKeywordSearchEntityTypes: [{ value: 'doc' }],
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'tool_workspace_denied',
    });
    expect(
      decision({
        enabledBootstrapApps: null,
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceBootstrapLoading: true,
        workspaceKeywordSearchEntityTypes: [{ value: 'doc' }],
      }),
    ).toEqual({ type: 'loading' });
    expect(
      decision({
        matchedToolRoute: ragSearchRoute,
        toolId: 'search',
        workspaceBootstrapError: 'Bootstrap failed',
        workspaceKeywordSearchEntityTypes: [{ value: 'doc' }],
      }),
    ).toEqual({
      type: 'access_denied_message',
      message: 'Bootstrap failed',
    });
  });

  it('gates non-Chatbot dedicated tool elements on workspace app enablement', () => {
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'chatbot', enabled: true }],
        item: docsItem,
        matchedToolRoute: docsRoute,
        toolId: 'docs-all',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'app_disabled',
    });
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'chatbot', enabled: true }],
        item: { appId: 'pms' },
        matchedToolRoute: pmsRoute,
        toolId: 'pms-inbox',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'app_disabled',
    });
    expect(
      decision({
        item: betaItem,
        matchedToolRoute: customUngatedRoute,
        toolId: 'custom-tool',
      }),
    ).toEqual({
      routeId: 'chatbot.custom-tool',
      type: 'tool_element',
    });
  });

  it('gates an aggregate shell tool route with its leaf bootstrap app ID', () => {
    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'docs', enabled: true }],
        item: { appId: 'collaboration', linkAppId: 'docs' },
        matchedToolRoute: {
          appId: 'collaboration',
          bootstrapAppId: 'docs',
          id: 'collaboration.docs',
          type: 'element',
        },
        toolId: 'docs-all',
      }),
    ).toEqual({
      routeId: 'collaboration.docs',
      type: 'tool_element',
    });

    expect(
      decision({
        enabledBootstrapApps: [{ app_id: 'collaboration', enabled: true }],
        item: { appId: 'collaboration', linkAppId: 'docs' },
        matchedToolRoute: {
          appId: 'collaboration',
          bootstrapAppId: 'docs',
          id: 'collaboration.docs',
          type: 'element',
        },
        toolId: 'docs-all',
      }),
    ).toEqual({
      type: 'access_denied',
      reason: 'app_disabled',
    });
  });

  it('falls back to coming soon and generic tool views', () => {
    expect(
      decision({
        item: { appId: 'chatbot', comingSoon: true },
        matchedToolRoute: null,
        toolId: 'future-tool',
      }),
    ).toEqual({ type: 'coming_soon' });
    expect(
      decision({
        item: { appId: 'chatbot' },
        matchedToolRoute: null,
        toolId: 'generic-tool',
      }),
    ).toEqual({ type: 'tool_view' });
  });
});
