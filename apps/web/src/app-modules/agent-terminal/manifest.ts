import { SquareTerminal } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const agentTerminalManifest: AppModuleManifest = {
  appBarItem: {
    id: 'agent-terminal',
    title: 'agent-terminal',
    icon: SquareTerminal,
  },
  surfaces: { launcher: { globalPath: '/agent-terminal' } },
  contract: {
    owner: 'platform-operations',
    permissions: ['admin.access'],
    apiDomain: 'agent_terminal',
    resourceScope: 'personal',
    aiCapabilities: [],
    writeAuditActions: [
      'agent_terminal.session.start',
      'agent_terminal.session.recover',
      'agent_terminal.session.stop',
      'agent_terminal.session.finish',
      'agent_terminal.session.delete',
    ],
    appLocalTests: [
      'apps/web/src/app-modules/agent-terminal/api/agent-terminal-api.spec.ts',
      'apps/api/tests/test_agent_terminal.py',
    ],
  },
  defaultActiveNavItemId: 'agent-terminal',
  navItems: [],
  workspaceRoutePaths: [],
  globalRoutePaths: ['/agent-terminal'],
};
