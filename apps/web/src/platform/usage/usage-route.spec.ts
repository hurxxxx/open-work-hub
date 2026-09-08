import { describe, expect, it } from 'vitest';

import { normalizeUsageRoutePath, resolveUsageEventAppId } from './usage-route';

describe('normalizeUsageRoutePath', () => {
  it('groups app routes without preserving resource IDs', () => {
    expect(
      normalizeUsageRoutePath(
        '/apps/docs/documents/items/550e8400-e29b-41d4-a716-446655440000',
      ),
    ).toBe('/apps/docs/documents/items/:id');
  });

  it('keeps stable admin routes readable', () => {
    expect(normalizeUsageRoutePath('/admin/general/usage')).toBe(
      '/admin/general/usage',
    );
  });
});

describe('resolveUsageEventAppId', () => {
  it('uses the leaf bootstrap app id for usage events', () => {
    expect(
      resolveUsageEventAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'docs-my',
        navItems: [{ app_id: 'docs', id: 'docs-my' }],
      }),
    ).toBe('docs');
  });

  it('falls back to the active app when the nav item has no app id', () => {
    expect(
      resolveUsageEventAppId({
        activeAppId: 'collaboration',
        activeNavItemId: 'collaboration-home',
        navItems: [{ id: 'collaboration-home' }],
      }),
    ).toBe('collaboration');
  });
});
