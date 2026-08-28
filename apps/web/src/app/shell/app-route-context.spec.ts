import { describe, expect, it } from 'vitest';

import { resolveAppRouteContext } from './app-route-context';

describe('resolveAppRouteContext', () => {
  it('keeps the launcher neutral', () => {
    expect(resolveAppRouteContext('/')).toEqual({
      kind: 'launcher',
      appId: null,
      workspaceSlug: null,
    });
  });

  it('recognizes unresolved workspace app entry routes', () => {
    expect(resolveAppRouteContext('/apps/docs')).toMatchObject({
      kind: 'entry',
      appId: 'docs',
    });
  });

  it('extracts canonical workspace context', () => {
    expect(
      resolveAppRouteContext('/apps/docs/workspaces/hq/documents/doc-1'),
    ).toMatchObject({ kind: 'workspace', appId: 'docs', workspaceSlug: 'hq' });
  });

  it('never assigns workspace context to platform and shared routes', () => {
    expect(resolveAppRouteContext('/apps/mail')).toMatchObject({
      kind: 'global',
      workspaceSlug: null,
    });
    expect(resolveAppRouteContext('/apps/docs/shared/token')).toMatchObject({
      kind: 'global',
      workspaceSlug: null,
    });
  });
});
