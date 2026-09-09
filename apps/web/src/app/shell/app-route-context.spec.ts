import { describe, expect, it } from 'vitest';

import { resolveAppRouteContext } from './app-route-context';

describe('resolveAppRouteContext', () => {
  it('keeps the launcher neutral', () => {
    expect(resolveAppRouteContext('/')).toEqual({
      kind: 'launcher',
      appId: null,
    });
  });

  it('recognizes declared app entry routes', () => {
    expect(resolveAppRouteContext('/apps/docs')).toMatchObject({
      kind: 'app',
      appId: 'docs',
    });
  });

  it('identifies app resource routes', () => {
    expect(resolveAppRouteContext('/apps/docs/documents/doc-1')).toMatchObject({
      kind: 'app',
      appId: 'docs',
    });
  });

  it('identifies personal and shared app routes', () => {
    expect(resolveAppRouteContext('/apps/mail')).toMatchObject({
      kind: 'app',
    });
    expect(resolveAppRouteContext('/apps/docs/shared/token')).toMatchObject({
      kind: 'app',
    });
  });
});
