import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from './App';
import { api, ApiError, type Detail, type GitState } from './api';

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
let gitState: GitState;
let submit: (body: Record<string, unknown>) => Promise<Detail>;
let recover: () => Promise<Detail>;
let searchTasks: (query: string) => Promise<Detail[]>;

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
    stage: 'plan',
    status: 'idle',
    permissions: 'read-only',
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
  gitState = {
    root: '/repo/dev',
    branch: 'dev',
    head: 'a'.repeat(40),
    detached: false,
    upstream: 'origin/dev',
    ahead: 1,
    behind: 0,
    staged: 0,
    unstaged: 2,
    untracked: 1,
    conflicts: 0,
    changed: 3,
    checked_at: '2026-09-20T00:00:00Z',
  };
  submit = async () => detail;
  recover = async () => detail;
  searchTasks = async () => [];
  vi.mocked(api).mockReset();
  vi.mocked(api).mockImplementation(async (path, body) => {
    if (path === '/session') return { authenticated: true };
    if (path === '/tasks') return [detail];
    if (path.startsWith('/tasks?search=')) return searchTasks(path);
    if (path === '/codex/models')
      return [
        {
          model: 'gpt-5.6-sol',
          name: 'GPT-5.6-Sol',
          is_default: false,
          default_effort: 'high',
          efforts: ['low', 'medium', 'high'],
        },
        {
          model: 'alternate',
          name: 'Alternate',
          is_default: true,
          default_effort: 'medium',
          efforts: ['low', 'medium', 'high'],
        },
      ];
    if (path === '/codex/account')
      return { connected: true, auth_type: 'chatgpt' };
    if (path === `/tasks/${taskId}`) return detail;
    if (path === `/tasks/${taskId}/git`) return gitState;
    if (path === `/tasks/${taskId}/implement`)
      return submit(body as Record<string, unknown>);
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

it('retries an unavailable initial session check without a page reload', async () => {
  vi.mocked(api).mockRejectedValueOnce(new ApiError('request_failed'));
  render(<App />);
  const retry = await screen.findByRole('button', { name: '연결 다시 시도' });
  expect(
    (screen.getByRole('button', { name: '로그인' }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(retry);
  await screen.findByRole('heading', { name: 'Test task' });
  expect(screen.queryByRole('button', { name: '연결 다시 시도' })).toBeNull();
});

it('exchanges an Open Work Hub handoff before checking the existing session', async () => {
  const code = `cc1_${'a'.repeat(32)}`;
  window.history.replaceState(
    null,
    '',
    `/?task=${taskId}#${new URLSearchParams({
      owh_issuer: 'https://dev.example.test',
      owh_code: code,
    })}`,
  );
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (path === '/session/owh') {
      expect(args[0]).toEqual({
        issuer: 'https://dev.example.test',
        code,
      });
      return { authenticated: true };
    }
    return original(path, ...args);
  });

  render(<App />);

  await screen.findByRole('heading', { name: 'Test task' });
  expect(window.location.hash).toBe('');
  expect(api).toHaveBeenCalledWith('/session/owh', {
    issuer: 'https://dev.example.test',
    code,
  });
  expect(api).not.toHaveBeenCalledWith('/session');
});

it('preserves separate document drafts across result tabs and tasks and warns before leaving the page', async () => {
  const other = {
    ...detail,
    id: '00000000-0000-4000-8000-000000000002',
    title: 'Another task',
  };
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) => {
    if (path === '/tasks') return [detail, other];
    if (path === `/tasks/${other.id}`) return other;
    return original(path, ...args);
  });
  await openAndCompose();
  fireEvent.click(screen.getByRole('button', { name: '문서 편집' }));
  fireEvent.change(screen.getByRole('textbox', { name: '문서 편집' }), {
    target: { value: 'Requirements draft' },
  });
  const results = within(screen.getByRole('navigation', { name: '결과물' }));
  fireEvent.click(results.getByRole('button', { name: '계획' }));
  fireEvent.click(screen.getByRole('button', { name: '문서 편집' }));
  fireEvent.change(screen.getByRole('textbox', { name: '문서 편집' }), {
    target: { value: 'Plan draft' },
  });
  fireEvent.click(results.getByRole('button', { name: '파일' }));
  fireEvent.click(results.getByRole('button', { name: '요구사항' }));
  expect(screen.getByText('Requirements draft')).toBeTruthy();
  fireEvent.click(await screen.findByRole('button', { name: /Another task/ }));
  await screen.findByRole('heading', { name: 'Another task' });
  expect(screen.queryByText('Requirements draft')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /Test task/ }));
  await screen.findByText('Requirements draft');
  fireEvent.click(
    within(screen.getByRole('navigation', { name: '결과물' })).getByRole(
      'button',
      { name: '계획' },
    ),
  );
  expect(screen.getByText('Plan draft')).toBeTruthy();
  const leaving = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(leaving);
  expect(leaving.defaultPrevented).toBe(true);
});

it('searches all tasks on the server without clearing the open draft or accepting stale results', async () => {
  let resolveOld!: (rows: Detail[]) => void;
  searchTasks = async (query) =>
    query.endsWith('old')
      ? new Promise((resolve) => {
          resolveOld = resolve;
        })
      : [{ ...detail, id: 'other', title: 'New search result' }];
  await openAndCompose();
  fireEvent.change(screen.getByLabelText('작업 검색'), {
    target: { value: 'old' },
  });
  await waitFor(() => expect(resolveOld).toBeTypeOf('function'));
  fireEvent.change(screen.getByLabelText('작업 검색'), {
    target: { value: 'new' },
  });
  await screen.findByRole('button', { name: /New search result/ });
  await act(async () =>
    resolveOld([{ ...detail, id: 'old', title: 'Old result' }]),
  );
  expect(screen.queryByRole('button', { name: /Old result/ })).toBeNull();
  expect(
    (screen.getByLabelText('요청 내용 입력') as HTMLTextAreaElement).value,
  ).toBe('Same request');
});

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

it('executes an explicit prompt with selected model and YOLO without requiring a document', async () => {
  await openAndCompose();
  fireEvent.click(await screen.findByRole('button', { name: '설정 변경' }));
  await screen.findByRole('option', { name: 'Alternate' });
  fireEvent.change(screen.getByLabelText('모델'), {
    target: { value: 'alternate' },
  });
  fireEvent.change(screen.getByLabelText('추론 강도'), {
    target: { value: 'high' },
  });
  fireEvent.change(screen.getByLabelText('실행 모드'), {
    target: { value: 'implement' },
  });
  fireEvent.change(screen.getByLabelText('실행 권한'), {
    target: { value: 'yolo' },
  });
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      `/tasks/${taskId}/implement`,
      expect.objectContaining({
        model: 'alternate',
        effort: 'high',
        permissions: 'yolo',
        text: 'Same request',
      }),
    ),
  );
  const body = vi
    .mocked(api)
    .mock.calls.find(([path]) => path.endsWith('/implement'))![1];
  expect(body).not.toHaveProperty('revision_id');
});

it('resets a saved effort absent from the catalog before the next message', async () => {
  detail = { ...detail, model: 'alternate', effort: 'max' };
  await openAndCompose();
  fireEvent.click(await screen.findByRole('button', { name: '설정 변경' }));
  await screen.findByRole('option', { name: 'Alternate' });
  expect((screen.getByLabelText('추론 강도') as HTMLSelectElement).value).toBe(
    'medium',
  );
  expect(screen.queryByRole('option', { name: 'max' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      `/tasks/${taskId}/messages`,
      expect.objectContaining({ model: 'alternate', effort: 'medium' }),
    ),
  );
});

it('uses GPT-5.6-Sol with medium reasoning instead of an ambiguous default', async () => {
  await openAndCompose();
  expect(await screen.findByText('GPT-5.6-Sol · medium')).toBeTruthy();
  expect(screen.queryByText('Codex 기본 설정')).toBeNull();
  expect(screen.queryByText('기본값')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      `/tasks/${taskId}/messages`,
      expect.objectContaining({
        model: 'gpt-5.6-sol',
        effort: 'medium',
      }),
    ),
  );
});

it('falls back to the catalog default when GPT-5.6-Sol is unavailable', async () => {
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) =>
    path === '/codex/models'
      ? [
          {
            model: 'alternate',
            name: 'Alternate',
            is_default: true,
            default_effort: 'medium',
            efforts: ['low', 'medium', 'high'],
          },
        ]
      : original(path, ...args),
  );
  await openAndCompose();
  expect(await screen.findByText('Alternate · medium')).toBeTruthy();
});

it('allows an explicit continuation prompt after interruption without a dedicated resume button', async () => {
  detail = {
    ...detail,
    stage: 'implement',
    status: 'uncertain',
    permissions: 'ask',
  };
  await openAndCompose();
  expect(
    screen.queryByRole('button', { name: '중단 지점부터 계속' }),
  ).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      `/tasks/${taskId}/implement`,
      expect.objectContaining({ text: 'Same request' }),
    ),
  );
});

it('shows native progress and keeps execution settings fixed while steering', async () => {
  detail = {
    ...detail,
    stage: 'implement',
    status: 'running',
    permissions: 'yolo',
    model: 'alternate',
    progress: {
      steps: [
        { step: 'Inspect source', status: 'completed' },
        { step: 'Check gameplay', status: 'inProgress' },
      ],
    },
  };
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) =>
    path.endsWith('/steer') ? detail : original(path, ...args),
  );
  await openAndCompose();
  expect(screen.getByText('Inspect source')).toBeTruthy();
  expect(screen.getByText('Check gameplay')).toBeTruthy();
  const progress = screen
    .getByText('Inspect source')
    .closest('details') as HTMLDetailsElement | null;
  expect(progress?.open).toBe(false);
  expect(
    screen
      .getByText('YOLO는 승인 요청과 샌드박스 제한 없이 명령을 실행합니다.')
      .closest('.composer-help'),
  ).toBeTruthy();
  expect(
    (screen.getByLabelText('실행 모드') as HTMLSelectElement).disabled,
  ).toBe(true);
  expect(
    (screen.getByRole('button', { name: '설정 변경' }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '보충 지시 보내기' }));
  await waitFor(() =>
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/steer')),
    ).toBe(true),
  );
  const request = vi
    .mocked(api)
    .mock.calls.find(([path]) => path.endsWith('/steer'))![1] as Record<
    string,
    unknown
  >;
  expect(request.text).toBe('Same request');
  expect(request).not.toHaveProperty('model');
  expect(request).not.toHaveProperty('stage');
});

it('uses planning by default without saving a document from the browser', async () => {
  await openAndCompose();
  expect((screen.getByLabelText('실행 모드') as HTMLSelectElement).value).toBe(
    'plan',
  );
  fireEvent.click(screen.getByRole('button', { name: '보내기' }));
  await waitFor(() =>
    expect(
      vi
        .mocked(api)
        .mock.calls.some(
          ([path, body]) =>
            path.endsWith('/messages') &&
            (body as Record<string, unknown>).stage === 'plan',
        ),
    ).toBe(true),
  );
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/documents')),
  ).toBe(false);
});

it('shows the actual branch and changes in a read-only branch tab without merge targets', async () => {
  gitState.branch = null;
  gitState.detached = true;
  gitState.upstream = null;
  const original = vi.mocked(api).getMockImplementation()!;
  vi.mocked(api).mockImplementation(async (path, ...args) =>
    path.endsWith('/changes') ? [] : original(path, ...args),
  );
  await openAndCompose();
  await screen.findByText('브랜치 없음 (detached HEAD)');
  expect(screen.queryByRole('button', { name: '병합 요청' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '브랜치' }));
  await screen.findByText('/repo/dev');
  expect(screen.queryByLabelText('대상 브랜치')).toBeNull();
  expect(
    (screen.getByLabelText('요청 내용 입력') as HTMLTextAreaElement).value,
  ).toBe('Same request');
  expect(
    within(screen.getByLabelText('실행 모드'))
      .getAllByRole('option')
      .map((option) => option.textContent),
  ).toEqual(['계획', '실행']);
});

it('restores a request rejected before execution without automatically sending it', async () => {
  detail.status = 'failed';
  detail.error_code = 'sandbox_policy_mismatch';
  detail.failed_request_text = 'An unsent ordinary question';
  render(<App />);
  fireEvent.click(
    await screen.findByRole('button', { name: '전송하지 못한 요청 불러오기' }),
  );
  expect(
    (screen.getByLabelText('요청 내용 입력') as HTMLTextAreaElement).value,
  ).toBe('An unsent ordinary question');
  expect(
    vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/messages')),
  ).toBe(false);
});
