import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resources } from '@/src/platform/i18n/resources';
import type { WhiteboardDetail } from '../api/whiteboard-api';
import { WhiteboardContextSlotPanel } from './WhiteboardContextSlotPanel';

const mocks = vi.hoisted(() => ({
  confirm: vi.fn(),
  error: vi.fn(),
  getWhiteboardContextSlot: vi.fn(),
  createWhiteboardContextSlot: vi.fn(),
  attachWhiteboardContextSlot: vi.fn(),
  listWhiteboardHub: vi.fn(),
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({ confirm: mocks.confirm, confirmDialog: null }),
  useFeedback: () => ({ error: mocks.error }),
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-session', user: { time_zone: 'UTC' } }),
}));
vi.mock('../api/whiteboard-api', async (original) => ({
  ...(await original<typeof import('../api/whiteboard-api')>()),
  ...mocks,
}));
vi.mock('./WhiteboardEditorSurface', () => ({
  WhiteboardEditorSurface: ({ boardId }: { boardId: string }) => (
    <div>Editor {boardId}</div>
  ),
}));

function board(
  ownership: 'personal' | 'company' = 'personal',
): WhiteboardDetail {
  return {
    id: 'selected-board',
    title: 'Design draft',
    ownership_kind: ownership,
    company_visible: false,
    source_app: 'whiteboard',
    source_type: 'whiteboard',
    source_id: 'selected-board',
    source_kind: 'native',
    source_ref: null,
    generation_kind: 'manual',
    location_label: 'Personal',
    target_label: '',
    primary_target: null,
    targets: [],
    source_badge: '',
    source_deeplink: null,
    created_by_id: 'creator',
    created_by_name: 'Creator',
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    trashed_at: null,
    is_favorite: false,
    is_private: ownership === 'personal',
    last_viewed_at: null,
    can_view: true,
    can_edit: true,
    can_share: true,
    can_manage: true,
    scene: { elements: [], appState: {}, files: {} },
  };
}
const context = { app: 'pms', type: 'task_list', id: 'delivery-list' };
async function setup() {
  const i18n = createInstance();
  await i18n.init({ lng: 'ko-KR', resources, defaultNS: 'apps' });
  const view = render(
    <I18nextProvider i18n={i18n}>
      <WhiteboardContextSlotPanel
        context={context}
        defaultTitle="Delivery board"
        canEditContext
      />
    </I18nextProvider>,
  );
  await screen.findByRole('button', { name: '새 화이트보드' });
  return view;
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.confirm.mockResolvedValue(true);
  mocks.getWhiteboardContextSlot.mockResolvedValue({ item: null });
  mocks.listWhiteboardHub.mockResolvedValue({ items: [board()] });
  mocks.createWhiteboardContextSlot.mockResolvedValue(board('company'));
  mocks.attachWhiteboardContextSlot.mockResolvedValue(board('company'));
});

describe('Whiteboard project publication', () => {
  it('sends no creation request until the user confirms company ownership', async () => {
    mocks.confirm.mockResolvedValueOnce(false);
    await setup();
    fireEvent.click(screen.getByRole('button', { name: '새 화이트보드' }));
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledOnce());
    expect(mocks.createWhiteboardContextSlot).not.toHaveBeenCalled();
    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: '회사 콘텐츠로 전환',
        description: expect.stringContaining('플랫폼 관리자'),
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: '새 화이트보드' }));
    await screen.findByText('Editor selected-board');
    expect(mocks.createWhiteboardContextSlot).toHaveBeenCalledWith(
      'test-session',
      {
        ...context,
        title: 'Delivery board',
        company_admin_read_acknowledged: true,
      },
    );
  });

  it('keeps the picker open on cancellation and attaches only after explicit confirmation', async () => {
    mocks.confirm.mockResolvedValueOnce(false);
    await setup();
    fireEvent.click(screen.getByRole('button', { name: '기존에서 선택' }));
    fireEvent.click(await screen.findByText('Design draft'));
    await waitFor(() => expect(mocks.confirm).toHaveBeenCalledOnce());
    expect(mocks.attachWhiteboardContextSlot).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.click(screen.getByText('Design draft'));
    await screen.findByText('Editor selected-board');
    expect(mocks.attachWhiteboardContextSlot).toHaveBeenCalledWith(
      'test-session',
      {
        ...context,
        whiteboard_id: 'selected-board',
        company_admin_read_acknowledged: true,
      },
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('does not invent an acknowledgement when linking an already company-owned board', async () => {
    mocks.listWhiteboardHub.mockResolvedValue({ items: [board('company')] });
    await setup();
    fireEvent.click(screen.getByRole('button', { name: '기존에서 선택' }));
    fireEvent.click(await screen.findByText('Design draft'));
    await screen.findByText('Editor selected-board');
    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(mocks.attachWhiteboardContextSlot).toHaveBeenCalledWith(
      'test-session',
      {
        ...context,
        whiteboard_id: 'selected-board',
        company_admin_read_acknowledged: false,
      },
    );
  });

  it('does not submit a confirmed write after the context has been removed', async () => {
    let approve!: (value: boolean) => void;
    mocks.confirm.mockReturnValue(
      new Promise<boolean>((resolve) => {
        approve = resolve;
      }),
    );
    const view = await setup();
    fireEvent.click(screen.getByRole('button', { name: '새 화이트보드' }));
    view.unmount();
    await act(async () => {
      approve(true);
    });
    expect(mocks.createWhiteboardContextSlot).not.toHaveBeenCalled();
  });

  it('blocks another publication while a dismissed picker is still attaching', async () => {
    let finish: (value: WhiteboardDetail) => void = () => undefined;
    mocks.attachWhiteboardContextSlot.mockReturnValue(
      new Promise<WhiteboardDetail>((resolve) => {
        finish = resolve;
      }),
    );
    await setup();
    fireEvent.click(screen.getByRole('button', { name: '기존에서 선택' }));
    fireEvent.click(await screen.findByText('Design draft'));
    await waitFor(() =>
      expect(mocks.attachWhiteboardContextSlot).toHaveBeenCalledOnce(),
    );
    fireEvent.click(screen.getAllByRole('button', { name: '닫기' })[0]);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(
      screen
        .getByRole('button', { name: '새 화이트보드' })
        .hasAttribute('disabled'),
    ).toBe(true);
    expect(
      screen
        .getByRole('button', { name: '기존에서 선택' })
        .hasAttribute('disabled'),
    ).toBe(true);
    await act(async () => {
      finish(board('company'));
    });
    await screen.findByText('Editor selected-board');
    expect(mocks.createWhiteboardContextSlot).not.toHaveBeenCalled();
  });
});
