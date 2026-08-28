import { describe, expect, it } from 'vitest';

import {
  EMPTY_LAUNCHER_GLOBAL_PATHS,
  type LauncherGlobalPaths,
} from './navigation-types';
import {
  getInitials,
  resolveAppDisplayScope,
  resolveMobileAppLink,
  resolveThemePreference,
} from './shell-ui-model';

const LAUNCHER_GLOBAL_PATHS: LauncherGlobalPaths = new Map([
  ['community', '/apps/community'],
  ['mail', '/apps/mail'],
]);

describe('shell ui model', () => {
  it('resolves system theme preference from media state', () => {
    expect(resolveThemePreference('system', true)).toBe('dark');
    expect(resolveThemePreference('system', false)).toBe('light');
    expect(resolveThemePreference('dark', false)).toBe('dark');
    expect(resolveThemePreference('light', true)).toBe('light');
  });

  it('builds compact initials with a fallback', () => {
    expect(getInitials('Open Work Hub HQ', 'WS')).toBe('OW');
    expect(getInitials('Delivery', 'WS')).toBe('D');
    expect(getInitials('   ', 'WS')).toBe('WS');
  });

  it('resolves user-facing app scopes from the executable app contract', () => {
    expect(resolveAppDisplayScope('docs')).toBe('workspace');
    expect(resolveAppDisplayScope('mail')).toBe('personal');
    expect(resolveAppDisplayScope('community')).toBe('company');
  });

  it('resolves mobile workspace apps through their own app entry route', () => {
    expect(resolveMobileAppLink('docs', EMPTY_LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/docs',
    );
  });

  it('uses the app entry route for workspace apps', () => {
    expect(resolveMobileAppLink('docs', EMPTY_LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/docs',
    );
  });

  it('uses manifest-projected global launcher paths', () => {
    expect(resolveMobileAppLink('mail', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/mail',
    );
    expect(resolveMobileAppLink('community', LAUNCHER_GLOBAL_PATHS)).toBe(
      '/apps/community',
    );
  });
});
