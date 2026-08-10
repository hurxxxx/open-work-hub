import { Cog, Fan, Thermometer, UserCog, Zap } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { resources } from '@/src/platform/i18n/resources';
import {
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
  LEGACY_ISSUE_VIEWS,
} from './core/public-api';
import { legacyIssuesManifest } from './manifest';

describe('legacyIssuesManifest compressor activation', () => {
  it('registers the heat exchanger module navigation contract', () => {
    const heatExchangerItem = legacyIssuesManifest.navItems.find(
      (item) => item.id === LEGACY_ISSUE_VIEWS['heat-exchanger'].navItemId,
    );
    const coolingModuleItem = legacyIssuesManifest.navItems.find(
      (item) => item.id === LEGACY_ISSUE_VIEWS['cooling-module'].navItemId,
    );

    expect(heatExchangerItem).toMatchObject({
      category: 'legacy-issues',
      icon: Thermometer,
      pathSuffix: '/heat-exchanger',
    });
    expect(coolingModuleItem).toMatchObject({
      icon: Fan,
    });
    expect(heatExchangerItem?.icon).not.toBe(coolingModuleItem?.icon);
    expect(resources['ko-KR'].shell.nav).toHaveProperty(
      'legacy-issues-heat-exchanger',
      '열교환기',
    );
    expect(resources['en-US'].shell.nav).toHaveProperty(
      'legacy-issues-heat-exchanger',
      'Heat Exchanger',
    );
    expect(resources['ko-KR'].shell.navDescriptions).toHaveProperty(
      'legacy-issues-heat-exchanger',
    );
    expect(resources['en-US'].shell.navDescriptions).toHaveProperty(
      'legacy-issues-heat-exchanger',
    );
  });

  it('registers both compressor navigation items with their group and icons', () => {
    expect(
      legacyIssuesManifest.navItems.find(
        (item) =>
          item.id === LEGACY_ISSUE_VIEWS['compressor-mechanical'].navItemId,
      ),
    ).toMatchObject({
      category: 'legacy-issues-compressor',
      icon: Cog,
      pathSuffix: '/compressor/mechanical',
    });
    expect(
      legacyIssuesManifest.navItems.find(
        (item) =>
          item.id === LEGACY_ISSUE_VIEWS['compressor-electric'].navItemId,
      ),
    ).toMatchObject({
      category: 'legacy-issues-compressor',
      icon: Zap,
      pathSuffix: '/compressor/electric',
    });
  });

  it('provides Korean and English labels, descriptions, and category copy', () => {
    expect(resources['ko-KR'].shell.nav).toMatchObject({
      'legacy-issues-compressor-mechanical': '기계',
      'legacy-issues-compressor-electric': '전동',
    });
    expect(resources['en-US'].shell.nav).toMatchObject({
      'legacy-issues-compressor-mechanical': 'Mechanical',
      'legacy-issues-compressor-electric': 'Electric',
    });
    expect(resources['ko-KR'].shell.navDescriptions).toHaveProperty(
      'legacy-issues-compressor-mechanical',
    );
    expect(resources['en-US'].shell.navDescriptions).toHaveProperty(
      'legacy-issues-compressor-electric',
    );
    expect(resources['ko-KR'].shell.categories).toHaveProperty(
      'legacy-issues-compressor',
      '컴프레서',
    );
    expect(resources['en-US'].shell.categories).toHaveProperty(
      'legacy-issues-compressor',
      'Compressor',
    );
  });

  it('registers the direct edit permission settings contract', () => {
    expect(
      legacyIssuesManifest.navItems.find(
        (item) => item.id === LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
      ),
    ).toMatchObject({
      category: 'legacy-issues',
      icon: UserCog,
      pathSuffix: '/settings/direct-edit-permissions',
    });
    expect(legacyIssuesManifest.contract.writeAuditActions).toEqual(
      expect.arrayContaining([
        'legacy_issues.module_direct_editor.grant',
        'legacy_issues.module_direct_editor.revoke',
      ]),
    );
    expect(resources['ko-KR'].shell.nav).toHaveProperty(
      LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
      '모듈별 직접 수정 권한',
    );
    expect(resources['en-US'].shell.navDescriptions).toHaveProperty(
      LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
    );
    expect(legacyIssuesManifest.workspaceRoutePaths).toContain(
      LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH,
    );
  });

  it('registers report sharing audit actions', () => {
    expect(legacyIssuesManifest.contract.writeAuditActions).toEqual(
      expect.arrayContaining([
        'legacy_issues.report.share',
        'legacy_issues.report.unshare',
      ]),
    );
  });
});
