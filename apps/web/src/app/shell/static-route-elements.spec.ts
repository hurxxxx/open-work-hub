import { describe, expect, it } from 'vitest';

import { pmsHelpGuideRegistration } from '../../app-modules/pms';
import { APP_GLOBAL_ROUTES } from './app-registry';
import {
  createDefaultHelpRoutes,
  resolveGlobalRouteGateAppId,
} from './static-route-elements';

describe('static route app gates', () => {
  it('injects the registry-projected feature guides into the default help route', () => {
    const featureGuideToolIds = new Set(['search']);
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

  it('gates shared routes with their leaf app controls', () => {
    const docsRoute = APP_GLOBAL_ROUTES.find((route) =>
      route.path.startsWith('/apps/docs/shared/'),
    );
    const whiteboardRoute = APP_GLOBAL_ROUTES.find((route) =>
      route.path.startsWith('/apps/whiteboard/shared/'),
    );

    expect(resolveGlobalRouteGateAppId(docsRoute ?? {})).toBe('docs');
    expect(resolveGlobalRouteGateAppId(whiteboardRoute ?? {})).toBe(
      'whiteboard',
    );
  });
});
