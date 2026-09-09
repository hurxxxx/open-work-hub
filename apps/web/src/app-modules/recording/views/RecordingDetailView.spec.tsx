import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { RecordingDetail } from '../api/recording-api';
import { isRecordingRetryable } from './recording-detail-model';
import { RecordingDetailView } from './RecordingDetailView';

const state = vi.hoisted(() => ({ recording: null as RecordingDetail | null }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en-US' },
  }),
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token', user: { time_zone: 'UTC' } }),
}));
vi.mock('@/src/platform/apps/app-bootstrap-context', () => ({
  useAppBootstrapContext: () => ({ data: {} }),
  isBootstrapAppEnabled: () => true,
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({ confirm: vi.fn(), confirmDialog: null }),
}));
vi.mock('@/src/app-modules/docs/public-api', () => ({
  DocsViewerModal: () => null,
}));
vi.mock('./MeetingPickerModal', () => ({ MeetingPickerModal: () => null }));
vi.mock('./TaskPickerModal', () => ({ TaskPickerModal: () => null }));
vi.mock('./useRecordingDetailController', () => ({
  useRecordingDetailController: () => ({
    state: {
      recording: state.recording,
      titleDraft: state.recording?.title ?? '',
      playbackUrl: null,
      loading: false,
      busy: null,
      error: null,
      titleStatus: 'idle',
      meetingPickerOpen: false,
      taskPickerOpen: false,
      docPreview: null,
    },
    derived: {
      meetingTargets: [],
      taskTargets: [],
      otherTargets: [],
      retryable: state.recording
        ? isRecordingRetryable(state.recording)
        : false,
    },
    actions: {},
  }),
}));

function showRecording(overrides: Partial<RecordingDetail>) {
  state.recording = {
    id: 'recording-1',
    owner_id: 'user-1',
    ended_at: null,
    duration_sec: null,
    source: 'quick_record',
    storage_key: null,
    file_size: 0,
    mime_type: 'audio/webm',
    meeting_insight_status: 'pending',
    progress_pct: 0,
    transcribe_started_at: null,
    transcribe_completed_at: null,
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    trashed_at: null,
    targets: [],
    title: 'Failed recording',
    started_at: '2026-09-08T00:00:00Z',
    audio_status: 'saved',
    transcript_status: 'done',
    summary_status: 'done',
    failure_reason: null,
    result: null,
    publications: [],
    ...overrides,
  };
  render(
    <MemoryRouter>
      <RecordingDetailView />
    </MemoryRouter>,
  );
}

describe('RecordingDetailView result feedback', () => {
  it('shows terminal transcription failure instead of claiming that results are being generated', () => {
    showRecording({
      transcript_status: 'failed',
      summary_status: 'pending',
      failure_reason: 'Transcription service unavailable',
    });
    expect(screen.getByText('apps:recording.detail.resultFailed')).toBeTruthy();
    expect(
      screen.queryByText('apps:recording.detail.resultPending'),
    ).toBeNull();
    expect(screen.getByText('Transcription service unavailable')).toBeTruthy();
    expect(
      screen
        .getByRole('button', { name: 'apps:recording.detail.publishToDocs' })
        .hasAttribute('disabled'),
    ).toBe(true);
  });

  it('keeps the completed transcript while explaining a failed summary', () => {
    showRecording({
      summary_status: 'failed',
      result: {
        version: 1,
        transcript_text: 'Saved transcript',
        summary_text: null,
        verifier_note: null,
        generated_at: null,
        updated_at: '2026-09-08T00:00:00Z',
      },
    });
    expect(screen.getByText('Saved transcript')).toBeTruthy();
    expect(screen.getByText('apps:recording.detail.resultFailed')).toBeTruthy();
    expect(
      screen.queryByText('apps:recording.detail.resultPending'),
    ).toBeNull();
  });

  it('only describes an unfinished pipeline as generating results', () => {
    showRecording({
      transcript_status: 'transcribing',
      summary_status: 'pending',
    });
    expect(
      screen.getByText('apps:recording.detail.resultPending'),
    ).toBeTruthy();
    expect(screen.queryByText('apps:recording.detail.resultFailed')).toBeNull();
  });
});
