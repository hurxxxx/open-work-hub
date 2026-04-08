import { describe, expect, it, vi, afterEach } from 'vitest';

import { listProjectIssues } from './pms-api';
import {
  createDefaultIssueFilterParams,
  reconcileSelectedIssueIds,
  toLocalDateInputValue,
} from './pms-filters';

describe('pms filter helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults issue filters to active issues', () => {
    expect(createDefaultIssueFilterParams()).toEqual({ archived_state: 'active' });
    expect(createDefaultIssueFilterParams({ q: 'compressor' })).toEqual({
      archived_state: 'active',
      q: 'compressor',
    });
  });

  it('reconciles selected ids against the visible issue list', () => {
    const nextSelection = reconcileSelectedIssueIds(
      new Set(['issue-1', 'issue-2', 'issue-3']),
      [{ id: 'issue-2' }, { id: 'issue-4' }] as Array<{ id: string }>,
    );

    expect(Array.from(nextSelection)).toEqual(['issue-2']);
  });

  it('formats local dates without UTC conversion', () => {
    expect(toLocalDateInputValue(new Date(2026, 3, 8, 0, 30))).toBe('2026-04-08');
  });
});

describe('listProjectIssues', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps archived filter states to API query params', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    );

    await listProjectIssues('token', 'project-1', createDefaultIssueFilterParams());
    expect(String(fetchSpy.mock.calls[0][0])).toContain('archived=false');

    await listProjectIssues('token', 'project-1', { archived_state: 'archived' });
    expect(String(fetchSpy.mock.calls[1][0])).toContain('archived=true');

    await listProjectIssues('token', 'project-1', { archived_state: 'all' });
    expect(String(fetchSpy.mock.calls[2][0])).not.toContain('archived=');
  });
});
