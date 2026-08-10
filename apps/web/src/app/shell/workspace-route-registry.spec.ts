import { describe, expect, it } from 'vitest';

import { resolveWorkspaceRouteBootstrapAppId } from './workspace-route-registry';

describe('workspace route registry', () => {
  it('gates aggregate shell routes with their leaf bootstrap app ID', () => {
    expect(
      resolveWorkspaceRouteBootstrapAppId({
        appId: 'collaboration',
        bootstrapAppId: 'docs',
      }),
    ).toBe('docs');
    expect(resolveWorkspaceRouteBootstrapAppId({ appId: 'docs' })).toBe('docs');
  });
});
