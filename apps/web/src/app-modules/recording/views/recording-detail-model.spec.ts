import { describe, expect, it } from 'vitest';

import type { Recording, RecordingTarget } from '../api/recording-api';
import {
  deriveRecordingStages,
  groupRecordingTargets,
  isRecordingRetryable,
  recordingTargetHref,
  recordingPipelineState,
  summarizeRecordingStages,
} from './recording-detail-model';

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
    workspace_id: 'workspace-1',
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

describe('recording detail model', () => {
  it('maps backend pipeline statuses into rail states', () => {
    expect(recordingPipelineState('done')).toBe('done');
    expect(recordingPipelineState('saved')).toBe('done');
    expect(recordingPipelineState('failed')).toBe('failed');
    expect(recordingPipelineState('creating')).toBe('inProgress');
    expect(recordingPipelineState('transcribing')).toBe('inProgress');
    expect(recordingPipelineState('verifying')).toBe('inProgress');
    expect(recordingPipelineState('pending')).toBe('pending');
  });

  it('summarizes the visible recording pipeline stages', () => {
    const summary = summarizeRecordingStages(
      recording({
        transcript_status: 'done',
        summary_status: 'analyzing',
      }),
    );

    expect(summary.stages).toEqual([
      { key: 'audio', state: 'done' },
      { key: 'transcript', state: 'done' },
      { key: 'summary', state: 'inProgress' },
    ]);
    expect(summary.failedStage).toBeNull();
    expect(summary.activeStage).toEqual({
      key: 'summary',
      state: 'inProgress',
    });
    expect(summary.allDone).toBe(false);
  });

  it('prioritizes failed stages over active stages', () => {
    const summary = summarizeRecordingStages(
      recording({
        transcript_status: 'failed',
        summary_status: 'analyzing',
      }),
    );

    expect(summary.failedStage).toEqual({ key: 'transcript', state: 'failed' });
    expect(summary.activeStage).toBeNull();
    expect(
      isRecordingRetryable(recording({ transcript_status: 'failed' })),
    ).toBe(true);
    expect(
      isRecordingRetryable(recording({ meeting_insight_status: 'failed' })),
    ).toBe(false);
  });

  it('derives completed stages when the recording-owned result is done', () => {
    expect(deriveRecordingStages(recording())).toEqual([
      { key: 'audio', state: 'done' },
      { key: 'transcript', state: 'done' },
      { key: 'summary', state: 'done' },
    ]);
    expect(summarizeRecordingStages(recording()).allDone).toBe(true);
  });

  it('groups linked targets by recording detail sections', () => {
    const meeting = target({ id: 'meeting-target' });
    const task = target({
      id: 'task-target',
      target_app: 'pms',
      target_type: 'task',
      target_id: 'task 42',
    });
    const docs = target({
      id: 'docs-target',
      target_app: 'docs',
      target_type: 'document',
      target_id: 'doc-1',
    });

    expect(groupRecordingTargets([meeting, task, docs])).toEqual({
      meetingTargets: [meeting],
      taskTargets: [task],
      otherTargets: [docs],
    });
    expect(groupRecordingTargets(null)).toEqual({
      meetingTargets: [],
      taskTargets: [],
      otherTargets: [],
    });
  });

  it('builds hrefs for known target apps', () => {
    expect(recordingTargetHref('team space', target())).toBe(
      '/apps/meeting/workspaces/team%20space/meetings/meeting-1',
    );
    expect(
      recordingTargetHref(
        'hq',
        target({
          target_app: 'pms',
          target_type: 'task',
          target_id: 'task 42',
        }),
      ),
    ).toBe('/apps/pms/workspaces/hq?task=task+42');
    expect(
      recordingTargetHref(
        'hq',
        target({
          target_app: 'docs',
          target_type: 'document',
          target_id: 'doc-1',
        }),
      ),
    ).toBe('/apps/docs/workspaces/hq/documents/doc-1');
    expect(
      recordingTargetHref('hq', target({ target_app: 'unknown-app' })),
    ).toBeNull();
  });
});
