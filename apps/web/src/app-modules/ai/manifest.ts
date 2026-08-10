import { Globe2, MessageSquare, Sparkles } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const aiManifest: AppModuleManifest = {
  appBarItem: { id: 'ai', title: 'AI', icon: Sparkles },
  surfaces: { featureGuides: { toolIds: ['chatbot', 'search'] } },
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'ai',
    resourceScope: 'hybrid',
    workspaceApiPrefixes: ['/api/v1/chatbot'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_ai.py'],
  },
  defaultActiveNavItemId: '',
  navItems: [
    {
      id: 'chatbot',
      title: 'chatbot',
      icon: MessageSquare,
      category: 'AI 앱',
      appId: 'ai',
      linkAppId: 'chatbot',
    },
    {
      id: 'web-search',
      title: 'web-search',
      icon: Globe2,
      category: 'AI 앱',
      appId: 'ai',
      linkAppId: 'web-search',
    },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/chatbot',
    '/w/:workspaceSlug/web-search',
  ],
  globalRoutePaths: [],
};
