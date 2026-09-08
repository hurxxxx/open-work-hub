import { describe, expect, it } from 'vitest';

import {
  getInitials,
  resolveAppDisplayScope,
  resolveThemePreference,
} from './shell-ui-model';

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
    expect(resolveAppDisplayScope('docs')).toBe('personal');
    expect(resolveAppDisplayScope('mail')).toBe('personal');
    expect(resolveAppDisplayScope('community')).toBe('company');
  });
});
