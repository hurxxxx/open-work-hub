import { MessageSquare } from 'lucide-react';
import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const chatbotManifest: AppModuleManifest = {
  appBarItem: { id: 'chatbot', title: 'chatbot', icon: MessageSquare },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'ai',
    workspaceApiPrefixes: ['/api/v1/chatbot'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/chatbot/api/workspace-chatbot-api-path.spec.ts',
      'apps/web/src/app-modules/chatbot/api/sse-parser.spec.ts',
      'apps/web/src/app-modules/chatbot/api/chat-stream-state.spec.ts',
      'apps/web/src/app-modules/chatbot/api/useChatStream.spec.tsx',
      'apps/api/tests/test_ai.py',
    ],
  },
  defaultActiveNavItemId: '',
  navItems: [],
  workspaceRoutePaths: [getAppRoutePattern('chatbot.root')],
};
