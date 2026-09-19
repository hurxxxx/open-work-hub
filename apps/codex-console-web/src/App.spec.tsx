import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from './App';
import { api, ApiError, type Detail } from './api';

vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: vi.fn(),
}));
vi.mock('@pierre/diffs/react', () => ({ MultiFileDiff: () => <div /> }));

class Stream extends EventTarget {
  static current: Stream;
  constructor() {
    super();
    Stream.current = this;
  }
  close() {}
}

const taskId = '00000000-0000-4000-8000-000000000001';
let detail: Detail;
let submit: (body: Record<string, unknown>) => Promise<Detail>;
let recover: () => Promise<Detail>;

beforeEach(() => {
  vi.stubGlobal('EventSource', Stream);
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  window.history.replaceState(null, '', `?task=${taskId}`);
  detail = {
    id: taskId,
    title: 'Test task',
    stage: 'requirements',
    status: 'idle',
    thread_id: 'thread',
    turn_id: null,
    root: '/repo/dev',
    isolated: false,
    approved_revision: null,
    error_code: null,
    updated_at: '2026-09-19T00:00:00Z',
    event_id: 1,
    attachments: [],
    attachment_limits: {
      file_bytes: 52428800,
      task_bytes: 524288000,
      files: 200,
      selection: 20,
    },
    items: [],
    history_truncated: false,
    requests: [],
    revisions: [],
  };
  submit = async () => detail;
  recover = async () => detail;
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, body) => {
    if (path === '/session') return { authenticated: true };
    if (path === '/tasks') return [detail];
    if (path === '/codex/account')
      return { connected: true, auth_type: 'chatgpt' };
    if (path === `/tasks/${taskId}`) return detail;
    if (path === `/tasks/${taskId}/messages`)
      return submit(body as Record<string, unknown>);
    if (path === `/tasks/${taskId}/recover`) return recover();
    if (path === `/tasks/${taskId}/interrupt`) return detail;
    throw new Error(`Unexpected test endpoint: ${path}`);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

async function openAndCompose() {
  render(<App />);
  await screen.findByRole('heading', { name: 'Test task' });
  fireEvent.change(screen.getByLabelText('요청 내용 입력'), {
    target: { value: 'Same request' },
  });
}

it('offers explicit stop for an uncertain native thread without a saved turn ID', async () => {
  detail = {
    ...detail,
    status: 'uncertain',
    error_code: 'codex_request_uncertain',
  };
  render(<App />);
  const stop = await screen.findByRole('button', { name: '중단' });
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/interrupt')),
  ).toBe(false);
  fireEvent.click(stop);
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      `/tasks/${taskId}/interrupt`,
      {},
      undefined,
    ),
  );
});

it('keeps a newer SSE result when an older submission response arrives last', async () => {
  let resolve!: (value: Detail) => void;
  submit = () =>
    new Promise((done) => {
      resolve = done;
    });
  await openAndCompose();
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() => expect(resolve).toBeTypeOf('function'));
  const older = { ...detail, status: 'running', event_id: 2 };
  detail = {
    ...detail,
    event_id: 3,
    items: [{ id: 'final', type: 'agentMessage', text: 'Completed result' }],
  };
  act(() => Stream.current.dispatchEvent(new Event('changed')));
  await screen.findByText('Completed result');
  await act(async () => resolve(older));
  expect(screen.getByText('Completed result')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('요청 내용 입력'), {
    target: { value: 'Next request' },
  });
  expect(
    (
      screen.getByRole('button', {
        name: '보내기',
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(false);
});

it('retains retry identity on failed recovery and creates a new one only after successful explicit recovery', async () => {
  const attempts: string[] = [];
  submit = async (body) => {
    attempts.push(body.operation_id as string);
    detail = {
      ...detail,
      status: 'uncertain',
      error_code: 'codex_request_uncertain',
      event_id: detail.event_id + 1,
    };
    Stream.current.dispatchEvent(new Event('changed'));
    throw new ApiError('codex_request_uncertain');
  };
  recover = async () => {
    throw new ApiError('turn_not_finished');
  };
  await openAndCompose();
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await screen.findByRole('button', { name: '실행 상태 확인' });
  fireEvent.click(screen.getByRole('button', { name: '실행 상태 확인' }));
  await waitFor(() =>
    expect(
      (
        screen.getByRole('button', {
          name: '실행 상태 확인',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  // An ordinary state refresh does not authorize a new identity.
  detail = {
    ...detail,
    status: 'interrupted',
    error_code: null,
    event_id: detail.event_id + 1,
  };
  act(() => Stream.current.dispatchEvent(new Event('changed')));
  await waitFor(() =>
    expect(
      (
        screen.getByRole('button', {
          name: '보내기',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() => expect(attempts).toHaveLength(2));
  expect(attempts[1]).toBe(attempts[0]);
  recover = async () => {
    detail = {
      ...detail,
      status: 'interrupted',
      error_code: null,
      event_id: detail.event_id + 1,
    };
    return detail;
  };
  fireEvent.click(
    await screen.findByRole('button', { name: '실행 상태 확인' }),
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole('button', {
          name: '보내기',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(attempts).toHaveLength(2);
  expect(
    (screen.getByLabelText('요청 내용 입력') as HTMLTextAreaElement).value,
  ).toBe('Same request');
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() => expect(attempts).toHaveLength(3));
  expect(attempts[2]).not.toBe(attempts[0]);
});
