import { describe, expect, it } from 'vitest';

import { buildSidebarCategories } from './sub-sidebar-categories';

describe('buildSidebarCategories', () => {
  it('prepends the PMS spaces section when PMS access exists', () => {
    expect(buildSidebarCategories(['Personal'], 'pms', true)).toEqual(['Spaces', 'Personal']);
  });

  it('does not inject the PMS spaces section without PMS access', () => {
    expect(buildSidebarCategories(['Personal'], 'pms', false)).toEqual(['Personal']);
  });

  it('does not duplicate existing category entries', () => {
    expect(buildSidebarCategories(['Spaces', 'Personal', 'Personal'], 'pms', true)).toEqual(['Spaces', 'Personal']);
  });
});
