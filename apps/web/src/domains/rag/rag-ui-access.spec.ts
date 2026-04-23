import { describe, expect, it } from 'vitest';

import { canUseWorkspaceSearchTool, isWorkspaceAppEnabled } from './rag-ui-access';

describe('rag-ui-access', () => {
  it('requires the ai app and at least one searchable workspace app', () => {
    expect(canUseWorkspaceSearchTool([
      { app_id: 'ai', enabled: true },
      { app_id: 'docs', enabled: true },
    ])).toBe(true);

    expect(canUseWorkspaceSearchTool([
      { app_id: 'ai', enabled: true },
      { app_id: 'docs', enabled: false },
    ])).toBe(false);

    expect(canUseWorkspaceSearchTool([
      { app_id: 'docs', enabled: true },
    ])).toBe(false);
  });

  it('checks a single workspace app toggle', () => {
    expect(isWorkspaceAppEnabled([
      { app_id: 'ai', enabled: true },
      { app_id: 'meeting', enabled: false },
    ], 'ai')).toBe(true);
    expect(isWorkspaceAppEnabled([
      { app_id: 'ai', enabled: true },
      { app_id: 'meeting', enabled: false },
    ], 'meeting')).toBe(false);
  });
});
