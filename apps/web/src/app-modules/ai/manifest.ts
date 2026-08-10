import {
  BookOpen,
  Globe2,
  HelpCircle,
  MessageSquare,
  Scale,
  Sparkles,
} from 'lucide-react';

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
      id: 'qa-assistant',
      title: 'qa-assistant',
      icon: HelpCircle,
      category: 'AI 앱',
      appId: 'ai',
      absolutePath: '/qa-assistant',
    },
    {
      id: 'web-search',
      title: 'web-search',
      icon: Globe2,
      category: 'AI 앱',
      appId: 'ai',
      linkAppId: 'web-search',
    },
    {
      id: 'research-trends',
      title: 'research-trends',
      icon: BookOpen,
      category: 'AI 앱',
      appId: 'ai',
      linkAppId: 'research-trends',
    },
    {
      id: 'standards-monitor',
      title: 'standards-monitor',
      icon: Scale,
      category: 'AI 앱',
      appId: 'ai',
      linkAppId: 'standards-monitor',
    },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/chatbot',
    '/w/:workspaceSlug/web-search',
    '/w/:workspaceSlug/research-trends',
    '/w/:workspaceSlug/standards-monitor',
  ],
  globalRoutePaths: ['/qa-assistant'],
};
