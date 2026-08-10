import { describe, expect, it } from 'vitest';

import { qaAssistantGlobalRoutes } from '../../app-modules/qa-assistant';
import { collaborationGlobalRoutes } from '../../app-modules/collaboration';
import { pmsHelpGuideRegistration } from '../../app-modules/pms';
import { newsGlobalRoutes } from '../../app-modules/news';
import { personalAttendanceGlobalRoutes } from '../../app-modules/personal-attendance';
import {
  createDefaultHelpRoutes,
  isGlobalAppGateVisible,
  resolveGlobalRouteBootstrapState,
  resolveGlobalRouteGateAppId,
} from './static-route-elements';

describe('static route app gates', () => {
  it('injects the registry-projected feature guides into the default help route', () => {
    const featureGuideToolIds = new Set(['drafting']);
    const guideRoute = createDefaultHelpRoutes(featureGuideToolIds).find(
      (route) => route.path === '/help/ai/:feature',
    );

    expect(guideRoute?.element).toMatchObject({
      props: { featureGuideToolIds },
    });
    expect(
      createDefaultHelpRoutes(featureGuideToolIds).some(
        (route) => route.path === pmsHelpGuideRegistration.routePath,
      ),
    ).toBe(true);
  });

  it('gates Q&A with its leaf entitlement instead of an enabled AI sibling', () => {
    const route = qaAssistantGlobalRoutes[0];
    const gateAppId = resolveGlobalRouteGateAppId(route);

    expect(gateAppId).toBe('qa-assistant');
    expect(isGlobalAppGateVisible(gateAppId, ['ai', 'web-search'])).toBe(false);
    expect(
      isGlobalAppGateVisible(gateAppId, ['ai', 'web-search', 'qa-assistant']),
    ).toBe(true);
  });

  it('gates personal attendance until the hidden platform app is enabled', () => {
    const route = personalAttendanceGlobalRoutes[0];
    const gateAppId = resolveGlobalRouteGateAppId(route);

    expect(gateAppId).toBe('personal-attendance');
    expect(isGlobalAppGateVisible(gateAppId, ['community', 'mail'])).toBe(false);
    expect(
      isGlobalAppGateVisible(gateAppId, [
        'community',
        'mail',
        'personal-attendance',
      ]),
    ).toBe(true);
  });

  it('gates aggregate collaboration routes with their leaf entitlements', () => {
    const docsRoute = collaborationGlobalRoutes.find((route) =>
      route.path.startsWith('/docs/shared/'),
    );
    const whiteboardRoute = collaborationGlobalRoutes.find((route) =>
      route.path.startsWith('/whiteboard/shared/'),
    );

    expect(resolveGlobalRouteGateAppId(docsRoute ?? {})).toBe('docs');
    expect(resolveGlobalRouteGateAppId(whiteboardRoute ?? {})).toBe(
      'whiteboard',
    );
  });

  it('gates workspace-less News routes only with the global bootstrap', () => {
    const newsRoute = newsGlobalRoutes.find((route) => route.path === '/news');
    const state = resolveGlobalRouteBootstrapState({
      appId: newsRoute?.appId ?? 'news',
      defaultState: {
        bootstrapError: 'Workspace bootstrap failed',
        bootstrapLoading: true,
        visibleAppIds: null,
      },
      launcherGlobalAppIds: ['news'],
      launcherGlobalState: {
        bootstrapError: null,
        bootstrapLoading: false,
        visibleAppIds: ['news'],
      },
    });

    expect(state).toEqual({
      bootstrapError: null,
      bootstrapLoading: false,
      visibleAppIds: ['news'],
    });
    expect(isGlobalAppGateVisible('news', state.visibleAppIds ?? [])).toBe(
      true,
    );
  });
});
