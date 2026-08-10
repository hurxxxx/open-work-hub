import { describe, expect, it } from 'vitest';

import { collaborationGlobalRoutes } from '../../app-modules/collaboration';
import { pmsHelpGuideRegistration } from '../../app-modules/pms';
import {
  createDefaultHelpRoutes,
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

});
