import { describe, expect, it } from 'vitest';

import {
  applyMobileAppMenuOpenChange,
  applyMobileNavOpenChange,
  createClosedMobileShellMenuState,
  createMobileShellRouteKey,
  resolveActiveMobileShellMenuState,
} from './mobile-shell-menu-model';

describe('mobile shell menu model', () => {
  it('builds stable route keys from path and search', () => {
    expect(createMobileShellRouteKey('/apps/docs', '?view=mine')).toBe(
      '/apps/docs\u0000?view=mine',
    );
  });

  it('resolves stale route state to closed drawers', () => {
    const active = { routeKey: 'old', navOpen: true, appMenuOpen: true };

    expect(resolveActiveMobileShellMenuState(active, 'next')).toEqual(
      createClosedMobileShellMenuState('next'),
    );
  });

  it('applies nav open changes against the active route state', () => {
    expect(
      applyMobileNavOpenChange(
        { routeKey: 'route', navOpen: false, appMenuOpen: true },
        'route',
        (open) => !open,
      ),
    ).toEqual({ routeKey: 'route', navOpen: true, appMenuOpen: true });
  });

  it('resets stale route state before applying app menu changes', () => {
    expect(
      applyMobileAppMenuOpenChange(
        { routeKey: 'old', navOpen: true, appMenuOpen: true },
        'next',
        true,
      ),
    ).toEqual({ routeKey: 'next', navOpen: false, appMenuOpen: true });
  });
});
