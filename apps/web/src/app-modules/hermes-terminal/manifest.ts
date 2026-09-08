import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { SquareTerminal } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const hermesTerminalManifest: AppModuleManifest = {
  appBarItem: {
    id: 'hermes-terminal',
    title: 'hermes-terminal',
    icon: SquareTerminal,
  },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'hermes_terminal',
    aiCapabilities: [],
    writeAuditActions: [
      'hermes_terminal.session.start',
      'hermes_terminal.session.finish',
      'hermes_terminal.session.archive_failed',
      'hermes_terminal.session.runtime_missing',
      'hermes_terminal.approval.approve',
      'hermes_terminal.approval.deny',
    ],
    appLocalTests: [
      'apps/api/tests/test_hermes_terminal.py',
      'apps/web/src/app-modules/hermes-terminal/api/hermes-terminal-api.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'hermes-terminal',
  navItems: [],
  appRoutePaths: [getAppRoutePattern('hermes-terminal.root')],
};
