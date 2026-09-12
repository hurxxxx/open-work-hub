import { describe, expect, it } from 'vitest';

import type { HrGroupItem } from './admin-api';
import { buildHrGroupRows } from './admin-group-hierarchy';

function unit(
  id: string,
  name: string,
  parentId: string | null = null,
): HrGroupItem {
  return {
    id,
    name,
    slug: name.toLowerCase().replaceAll(' ', '-'),
    unit_type: 'department',
    parent_id: parentId,
    active: true,
    created_at: '2026-08-26T00:00:00Z',
    updated_at: '2026-08-26T00:00:00Z',
  };
}

describe('buildHrGroupRows', () => {
  it('sorts sibling names and preserves hierarchy depth', () => {
    const rows = buildHrGroupRows([
      unit('child-b', 'Beta', 'root'),
      unit('root', 'Platform'),
      unit('child-a', 'Alpha', 'root'),
      unit('other', 'Business'),
    ]);

    expect(rows.map(({ depth, item }) => [item.id, depth])).toEqual([
      ['other', 0],
      ['root', 0],
      ['child-a', 1],
      ['child-b', 1],
    ]);
  });

  it('keeps orphaned or cyclic legacy rows visible once', () => {
    const rows = buildHrGroupRows([
      unit('orphan', 'Orphan', 'missing'),
      unit('cycle-a', 'Cycle A', 'cycle-b'),
      unit('cycle-b', 'Cycle B', 'cycle-a'),
    ]);

    expect(rows.map(({ item }) => item.id).sort()).toEqual([
      'cycle-a',
      'cycle-b',
      'orphan',
    ]);
    expect(new Set(rows.map(({ item }) => item.id)).size).toBe(3);
  });
});
