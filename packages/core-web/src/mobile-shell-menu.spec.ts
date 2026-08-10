import { describe, expect, it } from 'vitest';

import {
  applyCoreMobileAppMenuOpenChange,
  applyCoreMobileNavOpenChange,
  createClosedCoreMobileShellMenuState,
  createCoreMobileShellRouteKey,
  resolveActiveCoreMobileShellMenuState,
} from './mobile-shell-menu';

describe('core mobile shell menu model', () => {
  it('builds stable route keys from path and search', () => {
    expect(createCoreMobileShellRouteKey('/w/hq/docs', '?view=mine')).toBe(
      '/w/hq/docs\u0000?view=mine',
    );
  });

  it('resolves stale route state to closed drawers', () => {
    const active = { routeKey: 'old', navOpen: true, appMenuOpen: true };

    expect(resolveActiveCoreMobileShellMenuState(active, 'next')).toEqual(
      createClosedCoreMobileShellMenuState('next'),
    );
  });

  it('applies drawer state changes against the active route state', () => {
    expect(
      applyCoreMobileNavOpenChange(
        { routeKey: 'route', navOpen: false, appMenuOpen: true },
        'route',
        (open) => !open,
      ),
    ).toEqual({ routeKey: 'route', navOpen: true, appMenuOpen: true });

    expect(
      applyCoreMobileAppMenuOpenChange(
        { routeKey: 'old', navOpen: true, appMenuOpen: true },
        'next',
        true,
      ),
    ).toEqual({ routeKey: 'next', navOpen: false, appMenuOpen: true });
  });
});
