import { describe, expect, it } from 'vitest';

import {
  filterAvailableEntityTypes,
  toggleEntityTypeSelection,
} from './rag-search-view-model';

describe('rag search entity scope', () => {
  it('keeps only bootstrap-projected entity types and removes duplicates', () => {
    expect(
      filterAvailableEntityTypes(
        ['planner_event', 'doc', 'unknown', 'doc'],
        ['doc', 'pms_task'],
      ),
    ).toEqual(['doc']);
  });

  it('uses an empty selection to mean every bootstrap-allowed entity', () => {
    expect(toggleEntityTypeSelection(['doc'], null)).toEqual([]);
    expect(toggleEntityTypeSelection([], 'all')).toEqual(['all']);
  });
});
