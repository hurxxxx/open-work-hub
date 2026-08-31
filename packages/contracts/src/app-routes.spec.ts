import { describe, expect, it } from 'vitest';

import {
  buildAppHref,
  getAppRouteChrome,
  getAppRoutePattern,
  matchAppRoute,
} from './app-routes';

describe('app route codec', () => {
  it('builds and matches a workspace resource route', () => {
    const href = buildAppHref({
      routeId: 'docs.document',
      workspaceSlug: '제품 연구',
      pathParams: { docId: 'doc/1' },
      queryParams: { page: 'page 1' },
    });
    expect(href).toBe(
      '/apps/docs/workspaces/%EC%A0%9C%ED%92%88%20%EC%97%B0%EA%B5%AC/documents/doc%2F1?page=page+1',
    );
    expect(matchAppRoute(href.split('?')[0])).toEqual({
      appId: 'docs',
      contextScope: 'workspace',
      pathParams: { docId: 'doc/1' },
      routeId: 'docs.document',
      workspaceSlug: '제품 연구',
    });
  });

  it('keeps global shared routes outside workspace context', () => {
    expect(getAppRoutePattern('docs.shared')).toBe(
      '/apps/docs/shared/:shareToken',
    );
    expect(
      buildAppHref({
        routeId: 'docs.shared',
        pathParams: { shareToken: 'token' },
      }),
    ).toBe('/apps/docs/shared/token');
  });

  it('projects route chrome from the generated contract', () => {
    expect(getAppRouteChrome('chatbot.root')).toBe('containedSurface');
    expect(getAppRouteChrome('docs.shared')).toBe('shared');
  });

  it('rejects missing or extra workspace context', () => {
    expect(() => buildAppHref({ routeId: 'docs.root' })).toThrow(
      'Workspace route requires workspaceSlug',
    );
    expect(() =>
      buildAppHref({ routeId: 'mail.root', workspaceSlug: 'hq' }),
    ).toThrow('Global route cannot carry workspaceSlug');
    expect(() =>
      buildAppHref({
        routeId: 'docs.document',
        workspaceSlug: 'hq',
        pathParams: { docId: 'doc-1', unexpected: 'value' },
      }),
    ).toThrow('Unexpected route parameter: unexpected');
  });
});
