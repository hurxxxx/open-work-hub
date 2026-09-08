import { describe, expect, it } from 'vitest';

import {
  buildAppHref,
  getAppRouteChrome,
  getAppRoutePattern,
  matchAppRoute,
} from './app-routes';

describe('app route codec', () => {
  it('builds and matches an app resource route', () => {
    const href = buildAppHref({
      routeId: 'docs.document',
      pathParams: { docId: 'doc/1' },
      queryParams: { page: 'page 1' },
    });
    expect(href).toBe('/apps/docs/documents/doc%2F1?page=page+1');
    expect(matchAppRoute(href.split('?')[0])).toEqual({
      appId: 'docs',
      pathParams: { docId: 'doc/1' },
      routeId: 'docs.document',
    });
  });

  it('builds explicit shared resource routes', () => {
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

  it('builds roots directly and rejects missing or extra resource parameters', () => {
    expect(buildAppHref({ routeId: 'docs.root' })).toBe('/apps/docs');
    expect(buildAppHref({ routeId: 'mail.root' })).toBe('/apps/mail');
    expect(() => buildAppHref({ routeId: 'docs.document' })).toThrow(
      'Missing route parameter: docId',
    );
    expect(() =>
      buildAppHref({
        routeId: 'docs.document',
        pathParams: { docId: 'doc-1', unexpected: 'value' },
      }),
    ).toThrow('Unexpected route parameter: unexpected');
    expect(matchAppRoute('/apps/docs/workspaces/obsolete')).toBeNull();
  });
});
