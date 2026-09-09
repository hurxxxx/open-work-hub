import { createPmsStatus } from '../../../../tests/fixtures/pms';
import { beforeEach, describe, expect, it } from 'vitest';

import { DATE_FORMAT_STORAGE_KEY } from '@/src/platform/time/time-utils';

import {
  formatDate,
  getDefaultTaskStatus,
  getStatusLabel,
  getStatusSlugs,
  getStatusTone,
} from './pms-constants';

describe('pms-constants', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DATE_FORMAT_STORAGE_KEY);
  });

  it('formats task dates with the stored date preference', () => {
    window.localStorage.setItem(DATE_FORMAT_STORAGE_KEY, 'iso');

    expect(formatDate('2026-05-02')).toBe('2026-05-02');
    expect(formatDate('2026-05-02T03:00:00Z')).toBe('2026-05-02');
  });

  it('keeps the Korean default task date format', () => {
    expect(formatDate('2026-05-02')).toBe('2026. 5. 2.');
  });

  it('resolves custom status labels, tones, and default status from task-list statuses', () => {
    const statuses = [
      createPmsStatus({
        slug: 'backlog',
        name: 'Backlog',
        category: 'not_started',
        sort_order: 0,
      }),
      createPmsStatus({
        slug: 'doing',
        name: 'Doing',
        category: 'active',
        sort_order: 1,
      }),
      createPmsStatus({
        slug: 'closed_custom',
        name: 'Closed',
        category: 'closed',
        sort_order: 2,
      }),
    ];

    expect(getStatusSlugs(statuses)).toEqual([
      'backlog',
      'doing',
      'closed_custom',
    ]);
    expect(getStatusLabel('doing', statuses)).toBe('Doing');
    expect(getStatusTone('doing', statuses)).toBe('accent');
    expect(getStatusTone('closed_custom', statuses)).toBe('success');
    expect(getDefaultTaskStatus(statuses)).toBe('doing');
  });

  it('falls back for unknown status labels and default slugs', () => {
    expect(getStatusLabel('needs_review')).toBe('Needs Review');
    expect(getStatusTone('unknown')).toBe('neutral');
    expect(getDefaultTaskStatus([])).toBe('todo');
  });
});
