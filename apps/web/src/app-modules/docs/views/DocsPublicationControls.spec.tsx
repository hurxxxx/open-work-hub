import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useState } from 'react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resources } from '@/src/platform/i18n/resources';
import {
  deleteDocTarget,
  updateDocsCompanySharing,
  updateDocTarget,
  type DocsHubItem,
} from '../api/docs-api';
import { DocsPublicationControls } from './DocsPublicationControls';

const feedback = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  confirm: vi.fn(),
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => feedback,
  useConfirm: () => ({ confirm: feedback.confirm, confirmDialog: null }),
}));
vi.mock('../api/docs-api', async (original) => ({
  ...(await original<typeof import('../api/docs-api')>()),
  deleteDocTarget: vi.fn(),
  updateDocsCompanySharing: vi.fn(),
  updateDocTarget: vi.fn(),
}));

const spaces = [
  { id: 'space-a', name: 'Alpha' },
  { id: 'space-b', name: 'Beta' },
];
function document(overrides: Partial<DocsHubItem> = {}): DocsHubItem {
  return {
    id: 'doc-1',
    ownership_kind: 'company',
    company_visible: true,
    source_app: 'docs',
    source_type: 'native_doc',
    source_id: 'doc-1',
    source_kind: 'manual',
    source_ref: null,
    generation_kind: 'manual',
    rag_scope: 'official',
    doc_type: 'general',
    content_format: 'block',
    structure_kind: 'page_tree',
    location_label: 'Alpha',
    target_label: 'Alpha',
    collection: null,
    primary_target: { app: 'pms', type: 'space', id: 'space-a', sort_order: 0 },
    source_badge: 'Docs',
    source_deeplink: null,
    title: 'Shared document',
    page_count: 0,
    created_by_id: 'owner',
    created_by_name: 'Owner',
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    trashed_at: null,
    is_favorite: false,
    is_private: false,
    last_viewed_at: null,
    can_view: true,
    can_edit: true,
    can_share: true,
    can_manage: true,
    sharing_summary: {
      visibility: 'shared',
      user_share_count: 1,
      link_active: true,
      link_access_level: 'read',
    },
    ...overrides,
  };
}

async function renderControls(initial = document(), language = 'en-US') {
  const i18n = createInstance();
  await i18n.init({ resources, lng: language, fallbackLng: false });
  const updated = vi.fn<(doc: DocsHubItem) => void>();
  function Harness() {
    const [doc, setDoc] = useState(initial);
    return (
      <DocsPublicationControls
        token="session-a"
        doc={doc}
        spaces={spaces}
        onUpdated={(next) => {
          updated(next);
          setDoc(next);
        }}
      />
    );
  }
  return {
    ...render(
      <I18nextProvider i18n={i18n}>
        <Harness />
      </I18nextProvider>,
    ),
    updated,
    i18n,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  feedback.confirm.mockResolvedValue(true);
});

describe('Docs publication controls', () => {
  it('changes the primary PMS connection while keeping company visibility and existing shares', async () => {
    const updated = document({
      primary_target: {
        app: 'pms',
        type: 'space',
        id: 'space-b',
        sort_order: 0,
      },
      target_label: 'Beta',
    });
    vi.mocked(updateDocTarget).mockResolvedValue(updated);
    const view = await renderControls();
    expect(
      screen.getByRole<HTMLInputElement>('checkbox', {
        name: 'Company-wide visibility',
      }).checked,
    ).toBe(true);
    expect(
      screen
        .getByRole('button', { name: /Alpha/ })
        .getAttribute('aria-pressed'),
    ).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: /Beta/ }));
    await waitFor(() => expect(view.updated).toHaveBeenCalledWith(updated));
    expect(updateDocTarget).toHaveBeenCalledWith('session-a', 'doc-1', {
      app: 'pms',
      type: 'space',
      id: 'space-b',
      company_admin_read_acknowledged: true,
    });
    expect(updateDocsCompanySharing).not.toHaveBeenCalled();
    expect(deleteDocTarget).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(true);
    expect(
      screen.getByRole('button', { name: /Beta/ }).getAttribute('aria-pressed'),
    ).toBe('true');
    expect(
      screen.getByText(/User, group, link and other project grants remain/),
    ).not.toBeNull();
  });

  it('removes company visibility without removing the primary target or direct and link shares', async () => {
    const updated = document({ company_visible: false });
    vi.mocked(updateDocsCompanySharing).mockResolvedValue(updated);
    const view = await renderControls();
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    await waitFor(() => expect(view.updated).toHaveBeenCalledWith(updated));
    expect(updateDocsCompanySharing).toHaveBeenCalledWith(
      'session-a',
      'doc-1',
      false,
      false,
    );
    expect(deleteDocTarget).not.toHaveBeenCalled();
    expect(updateDocTarget).not.toHaveBeenCalled();
    expect(feedback.confirm).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(false);
    expect(
      screen
        .getByRole('button', { name: /Alpha/ })
        .getAttribute('aria-pressed'),
    ).toBe('true');
    expect(updated.ownership_kind).toBe('company');
    expect(updated.sharing_summary?.user_share_count).toBe(1);
    expect(updated.sharing_summary?.link_active).toBe(true);
  });

  it('removes only the primary connection while keeping company visibility', async () => {
    const updated = document({ primary_target: null });
    vi.mocked(deleteDocTarget).mockResolvedValue(updated);
    const view = await renderControls();
    fireEvent.click(
      screen.getByRole('button', { name: /No primary connection/ }),
    );
    await waitFor(() => expect(view.updated).toHaveBeenCalledWith(updated));
    expect(deleteDocTarget).toHaveBeenCalledWith('session-a', 'doc-1');
    expect(updateDocsCompanySharing).not.toHaveBeenCalled();
    expect(updateDocTarget).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(true);
    expect(
      screen
        .getByRole('button', { name: /No primary connection/ })
        .getAttribute('aria-pressed'),
    ).toBe('true');
  });

  it('makes no publication request when the company ownership acknowledgment is cancelled', async () => {
    feedback.confirm.mockResolvedValue(false);
    await renderControls(document({ company_visible: false }));
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    await waitFor(() =>
      expect(screen.getByRole<HTMLInputElement>('checkbox').disabled).toBe(
        false,
      ),
    );
    expect(feedback.confirm).toHaveBeenCalledOnce();
    expect(updateDocsCompanySharing).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(false);
  });

  it('does not expose a company or target write to a viewer without sharing authority', async () => {
    await renderControls(document({ can_share: false, can_manage: false }));
    expect(screen.getByRole<HTMLInputElement>('checkbox').disabled).toBe(true);
    for (const button of screen.getAllByRole<HTMLButtonElement>('button'))
      expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    expect(updateDocsCompanySharing).not.toHaveBeenCalled();
  });

  it('does not restore a resource after its controls unmount during an in-flight update', async () => {
    let resolve!: (doc: DocsHubItem) => void;
    vi.mocked(updateDocsCompanySharing).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const view = await renderControls();
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    await waitFor(() =>
      expect(updateDocsCompanySharing).toHaveBeenCalledOnce(),
    );
    view.unmount();
    await act(async () => resolve(document({ company_visible: false })));
    expect(view.updated).not.toHaveBeenCalled();
    expect(feedback.success).not.toHaveBeenCalled();
  });

  it('discards a late update after sharing authority is revoked', async () => {
    let resolve!: (doc: DocsHubItem) => void;
    vi.mocked(updateDocsCompanySharing).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const view = await renderControls();
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    await waitFor(() =>
      expect(updateDocsCompanySharing).toHaveBeenCalledOnce(),
    );
    view.rerender(
      <I18nextProvider i18n={view.i18n}>
        <DocsPublicationControls
          token="session-a"
          doc={document({ can_share: false, can_manage: false })}
          spaces={spaces}
          onUpdated={view.updated}
        />
      </I18nextProvider>,
    );
    await act(async () => resolve(document({ company_visible: false })));
    expect(view.updated).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(true);
    expect(screen.getByRole<HTMLInputElement>('checkbox').disabled).toBe(true);
  });

  it('retains the server audience after an update fails and reports the error', async () => {
    vi.mocked(updateDocsCompanySharing).mockRejectedValue(
      new Error('Access revoked'),
    );
    const view = await renderControls();
    fireEvent.click(screen.getByRole<HTMLInputElement>('checkbox'));
    await waitFor(() =>
      expect(feedback.error).toHaveBeenCalledWith('Access revoked'),
    );
    expect(view.updated).not.toHaveBeenCalled();
    expect(screen.getByRole<HTMLInputElement>('checkbox').checked).toBe(true);
    expect(
      screen
        .getByRole('button', { name: /Alpha/ })
        .getAttribute('aria-pressed'),
    ).toBe('true');
  });

  it('renders Korean copy that describes retained permissions instead of exclusive private access', async () => {
    await renderControls(document(), 'ko-KR');
    expect(
      screen.getByRole<HTMLInputElement>('checkbox', { name: '전사 공개' }),
    ).not.toBeNull();
    expect(
      screen.getByText(
        /사용자·그룹·링크 및 다른 프로젝트 연결 권한은 유지됩니다/,
      ),
    ).not.toBeNull();
    expect(screen.queryByText(/나만 볼|멤버만 볼/)).toBeNull();
  });
});
