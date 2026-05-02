import {
  AlertTriangle,
  BarChart3,
  Brain,
  FileBarChart,
  FilePlus,
  FileSearch,
  FileText,
  Gavel,
  HelpCircle,
  Languages,
  Mail,
  MessageSquare,
  Mic,
  Newspaper,
  Presentation,
  Search,
} from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const aiManifest: AppModuleManifest = {
  appBarItem: { id: 'ai', title: 'AI', icon: Brain },
  defaultActiveNavItemId: 'chatbot',
  navItems: [
    { id: 'chatbot', title: 'chatbot', icon: MessageSquare, category: 'Core Tools', appId: 'ai', description: 'chatbot' },
    { id: 'search', title: 'search', icon: Search, category: 'Core Tools', appId: 'ai', description: 'search' },
    { id: 'drafting', title: 'drafting', icon: FileText, category: 'Core Tools', appId: 'ai', description: 'drafting', comingSoon: true },
    { id: 'translate', title: 'translate', icon: Languages, category: 'Core Tools', appId: 'ai', description: 'translate', comingSoon: true },
    { id: 'spec-compare', title: 'spec-compare', icon: FileSearch, category: 'Core Tools', appId: 'ai', description: 'spec-compare', comingSoon: true },
    { id: 'fmea-compare', title: 'fmea-compare', icon: AlertTriangle, category: 'Core Tools', appId: 'ai', description: 'fmea-compare', comingSoon: true },
    { id: 'meeting-minutes', title: 'meeting-minutes', icon: Mic, category: 'Assistants', appId: 'ai', linkAppId: 'meeting', pathSuffix: '?tab=recordings', description: 'meeting-minutes' },
    { id: 'email-assistant', title: 'email-assistant', icon: Mail, category: 'Assistants', appId: 'ai', description: 'email-assistant', comingSoon: true },
    { id: 'ppt-assistant', title: 'ppt-assistant', icon: Presentation, category: 'Assistants', appId: 'ai', description: 'ppt-assistant', comingSoon: true },
    { id: 'qa-assistant', title: 'qa-assistant', icon: HelpCircle, category: 'Assistants', appId: 'ai', description: 'qa-assistant', comingSoon: true },
    { id: 'news', title: 'news', icon: Newspaper, category: 'Assistants', appId: 'ai', description: 'news', comingSoon: true },
    { id: 'industry-report', title: 'industry-report', icon: BarChart3, category: 'Assistants', appId: 'ai', description: 'industry-report', comingSoon: true },
    { id: 'patent-interpret', title: 'patent-interpret', icon: Gavel, category: 'Patent', appId: 'ai', description: 'patent-interpret', comingSoon: true },
    { id: 'patent-apply', title: 'patent-apply', icon: FilePlus, category: 'Patent', appId: 'ai', description: 'patent-apply', comingSoon: true },
    { id: 'patent-report', title: 'patent-report', icon: FileBarChart, category: 'Patent', appId: 'ai', description: 'patent-report', comingSoon: true },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/ai'],
};
