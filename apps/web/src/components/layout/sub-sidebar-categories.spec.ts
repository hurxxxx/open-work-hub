import { describe, expect, it } from 'vitest';

import { buildSidebarCategories } from './sub-sidebar-categories';

describe('buildSidebarCategories', () => {
  it('does not duplicate existing category entries', () => {
    expect(buildSidebarCategories(['Spaces', 'Personal', 'Personal'])).toEqual(['Spaces', 'Personal']);
  });
});
