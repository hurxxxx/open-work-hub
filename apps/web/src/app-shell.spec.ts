import { createAuthUser } from '../tests/fixtures/company';
import { describe, expect, it } from 'vitest';
import { resolveShellState } from './app-shell';
const user = createAuthUser({
  id: 'member',
  system_roles: [],
  group_ids: [],
  managed_organization_unit_ids: [],
});
const enabled = [
  'home',
  'pms',
  'docs',
  'meeting',
  'community',
  'retrieval-search',
  'whiteboard',
  'recording',
];
describe('company shell admission and navigation', () => {
  it('keeps the launcher neutral', () =>
    expect(resolveShellState('/', user, enabled)).toEqual({
      activeAppId: 'launcher',
      activeNavItemId: '',
    }));
  it.each([
    ['/apps/docs', 'docs', 'docs-all'],
    ['/apps/docs?view=mine', 'docs', 'docs-my'],
    ['/apps/pms', 'pms', 'pms-inbox'],
    ['/apps/pms/assigned', 'pms', 'pms-tasks-assigned'],
    ['/apps/pms/lists/demo', 'pms', 'pms-list-demo'],
    [
      '/apps/pms/spaces/space-1/docs/doc-1',
      'pms',
      'pms-space-space-1-docs-doc-1',
    ],
    ['/apps/retrieval-search', 'retrieval-search', 'retrieval-search'],
    ['/apps/meeting', 'meeting', 'meeting-upcoming'],
    ['/apps/meeting?scope=mine', 'meeting', 'meeting-mine'],
    ['/apps/whiteboard?view=mine', 'whiteboard', 'whiteboard-my'],
  ])('selects the declared route %s', (path, app, nav) => {
    expect(resolveShellState(path, user, enabled)).toEqual({
      activeAppId: app,
      activeNavItemId: nav,
    });
  });
  it.each(['/apps/docs', '/apps/docs/shared/token', '/apps/pms/lists/demo'])(
    'denies %s without current admission',
    (path) => {
      expect(resolveShellState(path, user)).toEqual({
        activeAppId: 'launcher',
        activeNavItemId: '',
      });
      expect(resolveShellState(path, user, [])).toEqual({
        activeAppId: 'launcher',
        activeNavItemId: '',
      });
      expect(resolveShellState(path, null, enabled)).toEqual({
        activeAppId: 'launcher',
        activeNavItemId: '',
      });
    },
  );
  it('does not infer authority from display category ids', () =>
    expect(resolveShellState('/apps/docs', user, ['collaboration'])).toEqual({
      activeAppId: 'launcher',
      activeNavItemId: '',
    }));
  it('requires a platform role for administration', () => {
    expect(resolveShellState('/admin/people', user, enabled)).toEqual({
      activeAppId: 'launcher',
      activeNavItemId: '',
    });
    expect(
      resolveShellState(
        '/admin/people',
        { ...user, system_roles: ['platform_admin'] },
        enabled,
      ),
    ).toEqual({ activeAppId: 'settings', activeNavItemId: 'settings-people' });
  });
  it('does not recognize removed outer container routes', () =>
    expect(
      resolveShellState('/apps/docs/workspaces/hq', user, enabled),
    ).toEqual({ activeAppId: 'home', activeNavItemId: '' }));
});
