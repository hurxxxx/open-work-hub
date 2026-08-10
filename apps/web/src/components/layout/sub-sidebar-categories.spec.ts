import { describe, expect, it } from 'vitest';

import {
  buildSidebarCategories,
  normalizeSubSidebarCategoryExpansionState,
  subSidebarCategoryExpansionKey,
  toggleSubSidebarCategoryExpansion,
} from './sub-sidebar-categories';

describe('buildSidebarCategories', () => {
  it('deduplicates category entries while preserving first-seen order', () => {
    expect(
      buildSidebarCategories(['Spaces', 'Personal', 'Personal', 'Spaces']),
    ).toEqual(['Spaces', 'Personal']);
  });
});

describe('sub-sidebar category expansion state', () => {
  it('normalizes category expansion state when the category set changes', () => {
    const categories = ['Core', 'Tools'];
    const normalized = normalizeSubSidebarCategoryExpansionState(
      {
        key: 'old',
        expandedCategories: ['Old'],
      },
      categories,
    );

    expect(normalized).toEqual({
      key: subSidebarCategoryExpansionKey(categories),
      expandedCategories: categories,
    });
    expect(
      normalizeSubSidebarCategoryExpansionState(normalized, categories),
    ).toBe(normalized);
  });

  it('toggles category expansion from current or stale state', () => {
    const categories = ['Core', 'Tools'];
    const initial = normalizeSubSidebarCategoryExpansionState(
      {
        key: '',
        expandedCategories: [],
      },
      categories,
    );

    expect(
      toggleSubSidebarCategoryExpansion(initial, categories, 'Tools')
        .expandedCategories,
    ).toEqual(['Core']);
    expect(
      toggleSubSidebarCategoryExpansion(initial, categories, 'Admin')
        .expandedCategories,
    ).toEqual(['Core', 'Tools', 'Admin']);
    expect(
      toggleSubSidebarCategoryExpansion(
        {
          key: 'old',
          expandedCategories: ['Old'],
        },
        categories,
        'Tools',
      ).expandedCategories,
    ).toEqual(['Core']);
  });
});
