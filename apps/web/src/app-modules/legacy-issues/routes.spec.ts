import { isValidElement } from 'react';
import { describe, expect, it } from 'vitest';

import {
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
  LEGACY_ISSUE_ASSISTANT_HISTORY_ROUTE_PATH,
  LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH,
  LEGACY_ISSUE_REPORTS_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_CHECKLIST_DETAIL_ROUTE_PATH,
  LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH,
  LEGACY_ISSUE_VIEW_KEYS,
  LEGACY_ISSUE_VIEWS,
} from './core/public-api';
import {
  isLegacyIssueViewAvailable,
  legacyIssuesWorkspaceRoutes,
} from './routes';

describe('legacy issue dataset routes', () => {
  it('keys every module screen so revision state cannot leak across modules', () => {
    for (const viewKey of LEGACY_ISSUE_VIEW_KEYS) {
      const route = legacyIssuesWorkspaceRoutes.find(
        (candidate) => candidate.path === LEGACY_ISSUE_VIEWS[viewKey].routePath,
      );

      expect(route).toBeDefined();
      expect(isValidElement(route?.element)).toBe(true);

      expect(route?.element?.key).toBe(viewKey);
    }
  });

  it('registers the compressor routes with isolated view state', () => {
    for (const viewKey of [
      'compressor-mechanical',
      'compressor-electric',
    ] as const) {
      const route = legacyIssuesWorkspaceRoutes.find(
        (candidate) => candidate.path === LEGACY_ISSUE_VIEWS[viewKey].routePath,
      );
      expect(route?.path).toBe(
        `/w/:workspaceSlug/legacy-issues/compressor/${
          viewKey === 'compressor-mechanical' ? 'mechanical' : 'electric'
        }`,
      );
      expect(route?.element?.key).toBe(viewKey);
    }
  });

  it('registers the heat exchanger route with isolated view state', () => {
    const route = legacyIssuesWorkspaceRoutes.find(
      (candidate) =>
        candidate.path === LEGACY_ISSUE_VIEWS['heat-exchanger'].routePath,
    );

    expect(route?.path).toBe('/w/:workspaceSlug/legacy-issues/heat-exchanger');
    expect(route?.element?.key).toBe('heat-exchanger');
  });

  it('requires each compressor nav item in workspace bootstrap', () => {
    expect(
      isLegacyIssueViewAvailable('compressor-mechanical', [
        { id: LEGACY_ISSUE_VIEWS['compressor-mechanical'].navItemId },
      ]),
    ).toBe(true);
    expect(
      isLegacyIssueViewAvailable('compressor-electric', [
        { id: LEGACY_ISSUE_VIEWS['compressor-mechanical'].navItemId },
      ]),
    ).toBe(false);
    expect(isLegacyIssueViewAvailable('aircon', [])).toBe(true);
  });

  it('registers separate vehicle-module list and module checklist detail routes', () => {
    expect(LEGACY_ISSUE_VEHICLE_CHECKLIST_DETAIL_ROUTE_PATH).toBe(
      '/w/:workspaceSlug/legacy-issues/vehicle-checklists/:vehicleModelId',
    );
    expect(LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH).toBe(
      '/w/:workspaceSlug/legacy-issues/vehicle-checklists/:vehicleModelId/:moduleKey',
    );
    expect(
      legacyIssuesWorkspaceRoutes.find(
        (route) =>
          route.path === LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH,
      )?.element,
    ).toBeDefined();
  });

  it('registers the platform-admin direct edit permission settings route', () => {
    expect(LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH).toBe(
      '/w/:workspaceSlug/legacy-issues/settings/direct-edit-permissions',
    );
    expect(
      legacyIssuesWorkspaceRoutes.find(
        (route) =>
          route.path === LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
      )?.element,
    ).toBeDefined();
  });

  it('registers canonical report management routes and keeps the old history route', () => {
    expect(LEGACY_ISSUE_REPORTS_ROUTE_PATH).toBe(
      '/w/:workspaceSlug/legacy-issues/reports',
    );
    expect(LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH).toBe(
      '/w/:workspaceSlug/legacy-issues/reports/:reportNumber',
    );
    for (const path of [
      LEGACY_ISSUE_REPORTS_ROUTE_PATH,
      LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH,
      LEGACY_ISSUE_ASSISTANT_HISTORY_ROUTE_PATH,
    ]) {
      expect(
        legacyIssuesWorkspaceRoutes.find((route) => route.path === path)
          ?.element,
      ).toBeDefined();
    }
  });
});
