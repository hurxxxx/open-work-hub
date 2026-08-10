import { describe, expect, it } from 'vitest';

import {
  createAttendanceRequest,
  deleteAttendanceRequest,
  fetchAttendanceRequests,
} from './personal-attendance-api';

describe('personal attendance prototype requests', () => {
  it('creates a unique id and deletes only the newly created request', async () => {
    const seeded = await fetchAttendanceRequests(null);
    const approvedSeed = seeded.find((request) => request.id === 'ar-2004');

    expect(approvedSeed?.status).toBe('APPROVED');

    const created = await createAttendanceRequest(
      null,
      {
        code: 7,
        startDate: '2026-10-01',
        endDate: '2026-10-01',
        reason: 'prototype request',
        attachments: [],
      },
      1,
    );

    expect(seeded.some((request) => request.id === created.id)).toBe(false);

    await deleteAttendanceRequest(null, created.id);
    const remaining = await fetchAttendanceRequests(null);

    expect(remaining.some((request) => request.id === created.id)).toBe(false);
    expect(remaining.find((request) => request.id === 'ar-2004')).toEqual(
      approvedSeed,
    );
  });
});
