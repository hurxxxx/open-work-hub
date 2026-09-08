import { describe, expect, it } from 'vitest';

import type { Recording, RecordingTarget } from '../api/recording-api';
import {
  compareRecordings,
  connectionChips,
  formatBytes,
  formatElapsed,
  hasFailedStage,
  listTitleKey,
  normalizeCategoryFilter,
  normalizeViewFilter,
  recordingMatchesCategory,
  searchableRecordingText,
  titleFor,
} from './recording-view-model';

function target(overrides: Partial<RecordingTarget> = {}): RecordingTarget {
  return {
    id: 'target-1',
    recording_id: 'recording-1',
    target_app: 'meeting',
    target_type: 'meeting',
    target_id: 'meeting-1',
    target_title: 'Planning sync',
    is_primary: true,
    sort_order: 0,
    added_by_id: 'user-1',
    created_at: '2026-05-30T00:00:00Z',
    ...overrides,
  };
}

function recording(overrides: Partial<Recording> = {}): Recording {
  return {
    id: 'recording-1',
    owner_id: 'user-1',
    title: 'Daily Standup',
    started_at: '2026-05-30T09:00:00Z',
    ended_at: null,
    duration_sec: 65,
    source: 'quick_record',
    storage_key: null,
    file_size: 1536,
    mime_type: 'audio/webm',
    audio_status: 'saved',
    transcript_status: 'done',
    summary_status: 'done',
    meeting_insight_status: 'done',
    progress_pct: 100,
    failure_reason: null,
    transcribe_started_at: null,
    transcribe_completed_at: null,
    created_at: '2026-05-30T09:00:00Z',
    updated_at: '2026-05-30T09:00:00Z',
    trashed_at: null,
    targets: [],
    ...overrides,
  } as Recording;
}

describe('recording view model', () => {
  it('normalizes invalid URL filters to the default view model state', () => {
    expect(normalizeViewFilter('processing')).toBe('processing');
    expect(normalizeViewFilter('unknown')).toBe('mine');
    expect(normalizeCategoryFilter('task')).toBe('task');
    expect(normalizeCategoryFilter('unknown')).toBe('all');
  });

  it('chooses list title keys with view filters taking precedence', () => {
    expect(listTitleKey('processing', 'meeting')).toBe(
      'apps:recording.views.processing',
    );
    expect(listTitleKey('mine', 'meeting')).toBe(
      'apps:recording.views.meeting',
    );
    expect(listTitleKey('mine', 'unlinked')).toBe(
      'apps:recording.views.unlinked',
    );
  });

  it('matches recordings by meeting, task, and unlinked categories', () => {
    const meeting = recording({ targets: [target()] });
    const task = recording({
      targets: [
        target({
          id: 'task-target',
          target_app: 'pms',
          target_type: 'task',
          target_title: 'ENG-42',
        }),
      ],
    });
    const unlinked = recording({ targets: [] });

    expect(recordingMatchesCategory(meeting, 'meeting')).toBe(true);
    expect(recordingMatchesCategory(meeting, 'task')).toBe(false);
    expect(recordingMatchesCategory(task, 'task')).toBe(true);
    expect(recordingMatchesCategory(unlinked, 'unlinked')).toBe(true);
    expect(recordingMatchesCategory(meeting, 'unlinked')).toBe(false);
  });

  it('sorts by title and start time', () => {
    const alpha = recording({
      id: 'alpha',
      title: 'Alpha',
      started_at: '2026-05-30T10:00:00Z',
    });
    const beta = recording({
      id: 'beta',
      title: 'Beta',
      started_at: '2026-05-30T08:00:00Z',
    });

    expect(compareRecordings(alpha, beta, 'title', 'en-US')).toBeLessThan(0);
    expect(compareRecordings(alpha, beta, 'latest', 'en-US')).toBeLessThan(0);
    expect(compareRecordings(alpha, beta, 'oldest', 'en-US')).toBeGreaterThan(
      0,
    );
  });

  it('builds searchable text and connection chips from targets', () => {
    const item = recording({
      title: 'Customer call',
      targets: [
        target({ id: 'meeting-target', target_title: 'Roadmap' }),
        target({
          id: 'task-target',
          target_app: 'pms',
          target_type: 'task',
          target_title: 'ENG-42',
        }),
      ],
    });

    expect(searchableRecordingText(item)).toContain('Customer call');
    expect(searchableRecordingText(item)).toContain('Roadmap');
    expect(searchableRecordingText(item)).toContain('ENG-42');
    expect(connectionChips(item)).toEqual([
      {
        id: 'meeting-target',
        labelKey: 'apps:recording.filters.categories.meeting',
        title: 'Roadmap',
      },
      {
        id: 'task-target',
        labelKey: 'apps:recording.filters.categories.task',
        title: 'ENG-42',
      },
    ]);
    expect(connectionChips(recording({ targets: [] }))).toEqual([
      {
        id: 'unlinked',
        labelKey: 'apps:recording.filters.categories.unlinked',
        title: null,
      },
    ]);
  });

  it('formats display values and detects failures', () => {
    expect(formatElapsed(3661)).toBe('01:01:01');
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(titleFor(recording({ title: '  ' }), 'Untitled')).toBe('Untitled');
    expect(hasFailedStage(recording({ transcript_status: 'failed' }))).toBe(
      true,
    );
    expect(hasFailedStage(recording({ audio_status: 'failed' }))).toBe(true);
    expect(
      hasFailedStage(recording({ meeting_insight_status: 'failed' })),
    ).toBe(true);
  });
});
