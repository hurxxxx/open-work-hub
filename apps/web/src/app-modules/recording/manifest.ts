import { ListMusic, Mic } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const recordingManifest: AppModuleManifest = {
  appBarItem: { id: 'recording', title: 'recording', icon: Mic },
  defaultActiveNavItemId: 'recording-quick',
  navItems: [
    {
      id: 'recording-quick',
      title: 'recording-quick',
      icon: Mic,
      category: 'Recordings',
      appId: 'recording',
    },
    {
      id: 'recording-mine',
      title: 'recording-mine',
      icon: ListMusic,
      category: 'Recordings',
      appId: 'recording',
      pathSuffix: '?view=mine',
    },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/recording'],
};
