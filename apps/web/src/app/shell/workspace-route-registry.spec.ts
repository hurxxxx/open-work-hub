import { describe, expect, it } from 'vitest';

import { WorkspaceRouteElements } from './workspace-route-registry';

describe('workspace route registry', () => {
  it('exposes only the leaf app route owner contract', () => {
    expect(WorkspaceRouteElements).toBeTypeOf('function');
  });
});
