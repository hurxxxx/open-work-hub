import { describe, expect, it } from 'vitest';

import {
  getInitialDocsSidebarExpandedSections,
  toggleDocsSidebarSection,
} from './docs-sidebar-model';

describe('docs sidebar model', () => {
  it('creates and toggles section expansion state', () => {
    const initial = getInitialDocsSidebarExpandedSections();

    expect(initial).toEqual(['favorites', 'recentPages']);
    expect(toggleDocsSidebarSection(initial, 'favorites')).toEqual([
      'recentPages',
    ]);
    expect(
      toggleDocsSidebarSection(['recentPages'], 'favorites'),
    ).toEqual(['recentPages', 'favorites']);
    expect(initial).toEqual(['favorites', 'recentPages']);
  });
});
