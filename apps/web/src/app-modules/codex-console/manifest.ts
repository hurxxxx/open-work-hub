import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { CodeXml } from 'lucide-react';
import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const codexConsoleManifest: AppModuleManifest = {
  appBarItem: { id: 'codex-console', title: 'codex-console', icon: CodeXml },
  contract: {
    owner: 'platform-operations',
    permissions: ['admin.access'],
    apiDomain: null,
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_codex_console_launch.py',
      'apps/web/src/app/shell/app-launch-destination.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'codex-console',
  navItems: [],
  appRoutePaths: [],
  globalRoutePaths: [getAppRoutePattern('codex-console.root')],
};
