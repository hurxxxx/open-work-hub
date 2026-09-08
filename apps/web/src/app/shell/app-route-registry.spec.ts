import { describe, expect, it } from 'vitest';

import { AppRouteElements } from './app-route-registry';

describe('app route registry', () => {
  it('exposes only the leaf app route owner contract', () => {
    expect(AppRouteElements).toBeTypeOf('function');
  });
});
