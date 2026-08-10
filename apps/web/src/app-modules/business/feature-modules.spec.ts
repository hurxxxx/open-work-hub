import { describe, expect, it } from 'vitest';

import { businessManifest } from './manifest';
import {
  businessFeatureModules,
  businessFeatureShellRegistrations,
} from './feature-modules';
import { businessToolViewRoutes, businessWorkspaceRoutes } from './routes';

describe('business feature module composition', () => {
  it('projects every app-local shell registration into the business manifest', () => {
    expect(businessFeatureShellRegistrations).toHaveLength(
      businessFeatureModules.length,
    );

    for (const registration of businessFeatureShellRegistrations) {
      expect(registration.toolRoute.id).toBe(`${registration.appId}.main`);
      expect(registration.toolRoute.path).toBe(
        `/w/:workspaceSlug/${registration.appId}`,
      );
      expect(businessManifest.navItems).toContainEqual(
        expect.objectContaining({
          id: registration.navItem.id,
          appId: 'business',
          linkAppId: registration.appId,
        }),
      );
      expect(businessManifest.workspaceRoutePaths).toContain(
        registration.toolRoute.path,
      );
    }
  });

  it('only adapts app-local route identities with business ownership and gates', () => {
    for (const registration of businessFeatureShellRegistrations) {
      const workspaceRoute = businessWorkspaceRoutes.find(
        (route) => route.path === registration.toolRoute.path,
      );
      const toolRoute = businessToolViewRoutes.find(
        (route) => route.id === registration.toolRoute.id,
      );

      expect(workspaceRoute).toMatchObject({
        appId: 'business',
        bootstrapAppId: registration.appId,
        subSidebar: registration.toolRoute.subSidebar,
      });
      expect(toolRoute).toMatchObject({
        appId: 'business',
        bootstrapAppId: registration.appId,
        id: registration.toolRoute.id,
        toolIds: registration.toolRoute.toolIds,
        gates: [
          {
            deniedReason: 'app_disabled',
            navItemId: registration.navItem.id,
            type: 'bootstrap_nav_item',
          },
        ],
      });
    }
  });
});
