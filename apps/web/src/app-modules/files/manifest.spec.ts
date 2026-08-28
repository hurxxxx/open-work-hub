import { describe, expect, it } from 'vitest';

import { filesManifest } from './manifest';

describe('Files manifest', () => {
  it('registers Files search and document chat navigation with its AI workloads', () => {
    expect(filesManifest.navItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          appId: 'files',
          id: 'files-search',
          pathSuffix: '?view=search',
          title: 'files-search',
        }),
        expect.objectContaining({
          appId: 'files',
          id: 'files-chat',
          pathSuffix: '/chat',
          title: 'files-chat',
        }),
      ]),
    );
    expect(filesManifest.workspaceRoutePaths).toContain(
      '/apps/files/workspaces/:workspaceSlug/chat',
    );
    expect(filesManifest.contract.aiCapabilities).toEqual([
      'files.grounded_chat',
      'files.rag_query_rewrite',
    ]);
  });
});
