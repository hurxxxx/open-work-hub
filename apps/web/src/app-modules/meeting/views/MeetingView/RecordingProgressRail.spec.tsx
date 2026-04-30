import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  ACTIVE_RECORDING_STATUSES,
  type MeetingRecording,
  type MeetingRecordingStatus,
} from '../../api/meeting-api';

import { RecordingProgressRail } from './RecordingProgressRail';

function makeRecording(status: MeetingRecordingStatus, progress_pct = 50): MeetingRecording {
  return {
    id: 'rec-1',
    meeting_id: 'm-1',
    uploaded_by_id: 'u-1',
    storage_key: 'k',
    duration_sec: 120,
    source: 'manual_upload',
    transcription_status: status,
    progress_pct,
    file_size: 1024,
    mime_type: 'audio/webm',
    failure_reason: null,
    linked_doc_id: null,
    linked_task_id: null,
    transcribe_started_at: null,
    transcribe_completed_at: null,
    created_at: '2026-04-21T00:00:00',
  };
}

describe('RecordingProgressRail', () => {
  it('renders six pipeline markers after inserting extracting_insights', () => {
    const { container } = render(
      <RecordingProgressRail recording={makeRecording('pending', 10)} />,
    );
    // The rail renders one rounded-full marker per stage.
    const markers = container.querySelectorAll('div.rounded-full');
    expect(markers.length).toBe(6);
  });

  it('treats extracting_insights as an in-progress stage (Loader icon on current)', () => {
    const { container } = render(
      <RecordingProgressRail
        recording={makeRecording('extracting_insights', 90)}
      />,
    );
    // One spinner at the current stage marker.
    const spinners = container.querySelectorAll('svg.animate-spin');
    expect(spinners.length).toBe(1);
  });

  it('freezes failed state at the generating_doc index (stages preceding it marked done)', () => {
    const { container } = render(
      <RecordingProgressRail recording={makeRecording('failed', 80)} />,
    );
    // Expected stage order: pending, transcribing, summarizing,
    // extracting_insights, generating_doc, done. `failed` maps to
    // generating_doc's index (4), so markers 0..3 should render as
    // done — a stable invariant even when new stages are inserted.
    const doneMarkers = container.querySelectorAll('div.bg-app-accent');
    expect(doneMarkers.length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText(/회의록 생성에 실패했습니다/)).toBeTruthy();
  });
});

describe('ACTIVE_RECORDING_STATUSES', () => {
  it('includes extracting_insights so polling stays live during AI extraction', () => {
    expect(ACTIVE_RECORDING_STATUSES.has('extracting_insights')).toBe(true);
  });
});
