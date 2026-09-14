import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import {
  getHermesFileRevision,
  listHermesFileRevisions,
  previewHermesFileRevision,
  type HermesFileRevision,
} from '../../api/hermes-agent-api';
import { HermesFilePanel } from './HermesFilePanel';

const feedback = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => feedback,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token' }),
}));
vi.mock('../../api/hermes-agent-api', async (original) => ({
  ...(await original<typeof import('../../api/hermes-agent-api')>()),
  getHermesFileRevision: vi.fn(),
  listHermesFileRevisions: vi.fn(),
  previewHermesFileRevision: vi.fn(),
}));
const revision: HermesFileRevision = {
  id: 'revision-1',
  file_id: 'file-1',
  session_id: 'session-1',
  run_id: null,
  relative_path: 'chart.png',
  media_type: 'image/png',
  size_bytes: 4,
  sha256: 'a'.repeat(64),
  created_at: '2026-09-14T01:00:00Z',
  expires_at: '2026-10-14T01:00:00Z',
};
const props = () => ({
  sessionId: 'session-1',
  fileId: 'file-1',
  revisionId: 'revision-1',
  onRevisionChange: vi.fn(),
  onClose: vi.fn(),
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
  URL.createObjectURL = vi.fn().mockReturnValue('blob:preview');
  URL.revokeObjectURL = vi.fn();
  vi.mocked(listHermesFileRevisions).mockResolvedValue({
    data: [revision],
    has_more: false,
  });
  vi.mocked(getHermesFileRevision).mockResolvedValue(revision);
  vi.mocked(previewHermesFileRevision).mockResolvedValue(
    new Blob(['test'], { type: 'image/png' }),
  );
});

it('releases the preview URL and aborts observation when the panel closes', async () => {
  const { unmount } = render(<HermesFilePanel {...props()} />);
  expect((await screen.findByRole('img')).getAttribute('src')).toBe(
    'blob:preview',
  );
  const signal = vi.mocked(previewHermesFileRevision).mock.calls[0][3];
  unmount();
  expect(signal.aborted).toBe(true);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview');
});

it('never falls back to the latest version when an exact link is expired or foreign', async () => {
  vi.mocked(getHermesFileRevision).mockResolvedValue({
    ...revision,
    session_id: 'foreign-session',
  });
  const input = props();
  render(<HermesFilePanel {...input} />);
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(previewHermesFileRevision).not.toHaveBeenCalled();
  expect(input.onRevisionChange).not.toHaveBeenCalled();
  expect(
    screen.getByRole('button', { name: '다운로드' }).hasAttribute('disabled'),
  ).toBe(true);
});

it('keeps unsupported files downloadable without fetching a preview', async () => {
  vi.mocked(getHermesFileRevision).mockResolvedValue({
    ...revision,
    media_type: 'application/pdf',
    relative_path: 'report.pdf',
  });
  render(<HermesFilePanel {...props()} />);
  expect(
    await screen.findByText('이 형식은 다운로드해서 확인할 수 있습니다.'),
  ).toBeTruthy();
  expect(
    screen.getByRole('button', { name: '다운로드' }).hasAttribute('disabled'),
  ).toBe(false);
  expect(previewHermesFileRevision).not.toHaveBeenCalled();
});

it('discards a late version response after switching files', async () => {
  let finish!: (value: HermesFileRevision) => void;
  vi.mocked(getHermesFileRevision).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { rerender } = render(<HermesFilePanel {...props()} />);
  const second = {
    ...revision,
    id: 'revision-2',
    file_id: 'file-2',
    relative_path: 'second.png',
  };
  vi.mocked(getHermesFileRevision).mockResolvedValue(second);
  vi.mocked(listHermesFileRevisions).mockResolvedValue({
    data: [second],
    has_more: false,
  });
  rerender(
    <HermesFilePanel {...props()} fileId="file-2" revisionId="revision-2" />,
  );
  expect(await screen.findByRole('img', { name: 'second.png' })).toBeTruthy();
  await act(async () => {
    finish(revision);
  });
  expect(screen.queryByRole('img', { name: 'chart.png' })).toBeNull();
  expect(previewHermesFileRevision).toHaveBeenCalledTimes(1);
});

it('shows an unavailable image instead of a broken-image success state', async () => {
  render(<HermesFilePanel {...props()} />);
  fireEvent.error(await screen.findByRole('img'));
  await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
});

it('rechecks a selected old version even while other versions remain accessible', async () => {
  vi.useFakeTimers();
  const input = props();
  vi.mocked(listHermesFileRevisions).mockResolvedValue({
    data: [{ ...revision, id: 'newer' }],
    has_more: true,
  });
  const { unmount } = render(<HermesFilePanel {...input} />);
  try {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole('img')).toBeTruthy();
    vi.mocked(getHermesFileRevision).mockRejectedValue(
      new Error('unavailable'),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.queryByRole('img')).toBeNull();
    expect(
      screen.getByRole('button', { name: '다운로드' }).hasAttribute('disabled'),
    ).toBe(true);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview');
    expect(input.onRevisionChange).not.toHaveBeenCalled();
  } finally {
    unmount();
    vi.useRealTimers();
  }
});

it('observes new versions while preserving the selected preview and loaded history', async () => {
  vi.useFakeTimers();
  const newer = {
    ...revision,
    id: 'newer',
    created_at: '2026-09-14T02:00:00Z',
  };
  const older = {
    ...revision,
    id: 'older',
    created_at: '2026-09-14T00:00:00Z',
  };
  vi.mocked(listHermesFileRevisions)
    .mockResolvedValueOnce({ data: [revision], has_more: true })
    .mockResolvedValueOnce({ data: [older], has_more: false })
    .mockResolvedValue({ data: [newer], has_more: true });
  const input = props();
  const { unmount } = render(<HermesFilePanel {...input} />);
  try {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByRole('button', { name: '이전 버전 더 보기' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(
      screen.queryByRole('button', { name: '이전 버전 더 보기' }),
    ).toBeNull();
    expect(input.onRevisionChange).not.toHaveBeenCalled();
    expect(previewHermesFileRevision).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '최신 버전 보기' }));
    expect(input.onRevisionChange).toHaveBeenCalledWith('newer');
    unmount();
    const calls = vi.mocked(listHermesFileRevisions).mock.calls.length;
    await vi.advanceTimersByTimeAsync(8000);
    expect(listHermesFileRevisions).toHaveBeenCalledTimes(calls);
  } finally {
    unmount();
    vi.useRealTimers();
  }
});
