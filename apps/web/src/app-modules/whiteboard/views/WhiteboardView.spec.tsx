import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { resources } from '@/src/platform/i18n/resources';
import type { WhiteboardHubItem } from '../api/whiteboard-api';
import { VIEW_MODE_STORAGE_KEY } from './whiteboard-hub-model';
import { WhiteboardView } from './WhiteboardView';

const api = vi.hoisted(() => ({
  listWhiteboardHub: vi.fn(),
  updateWhiteboardCompanySharing: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-session', user: { time_zone: 'UTC' } }),
}));
vi.mock('../api/whiteboard-api', async (original) => ({
  ...(await original<typeof import('../api/whiteboard-api')>()),
  ...api,
}));
vi.mock('./whiteboard-preview-loader', async (original) => ({
  ...(await original<typeof import('./whiteboard-preview-loader')>()),
  whiteboardPreviewLoader: { load: vi.fn().mockResolvedValue(null) },
}));

function projectBoard(companyVisible = false): WhiteboardHubItem {
  const target = { app: 'pms', type: 'space', id: 'project', sort_order: 0 };
  return {
    id: 'board',
    title: 'Project board',
    ownership_kind: 'company',
    company_visible: companyVisible,
    is_private: false,
    source_app: 'whiteboard',
    source_type: 'whiteboard',
    source_id: 'board',
    source_kind: 'native',
    source_ref: null,
    generation_kind: 'manual',
    location_label: 'Project',
    target_label: 'Project',
    primary_target: target,
    targets: [{ ...target, is_primary: true }],
    source_badge: '',
    source_deeplink: null,
    created_by_id: 'owner',
    created_by_name: 'Owner',
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    trashed_at: null,
    is_favorite: false,
    last_viewed_at: null,
    can_view: true,
    can_edit: true,
    can_share: true,
    can_manage: true,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('Whiteboard company publication controls', () => {
  it.each(['cards', 'list'])(
    'keeps a project board restricted and allows independent company publication in %s layout',
    async (layout) => {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, layout);
      const board = projectBoard();
      api.listWhiteboardHub.mockResolvedValue({ items: [board] });
      api.updateWhiteboardCompanySharing.mockImplementation(
        (_token: string, _id: string, companyVisible: boolean) =>
          Promise.resolve({ ...board, company_visible: companyVisible }),
      );
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      const i18n = createInstance();
      await i18n.init({ lng: 'ko-KR', resources, defaultNS: 'apps' });
      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <WhiteboardView />
          </MemoryRouter>
        </I18nextProvider>,
      );
      await screen.findByText(board.title);
      const restricted = screen
        .getByRole('heading', {
          name: i18n.t('whiteboard.personalSectionTitle'),
        })
        .closest('section');
      const company = screen
        .getByRole('heading', {
          name: i18n.t('whiteboard.companySectionTitle'),
        })
        .closest('section');
      if (!restricted || !company) throw new Error('Missing board sections');
      expect(within(restricted).getByText(board.title)).toBeTruthy();
      expect(within(company).queryByText(board.title)).toBeNull();

      fireEvent.keyDown(
        screen.getByRole('button', { name: i18n.t('whiteboard.actionsMenu') }),
        { key: 'ArrowDown' },
      );
      const publish = screen.getByRole('menuitem', {
        name: i18n.t('whiteboard.changeToCompany'),
      });
      expect(publish.getAttribute('aria-disabled')).not.toBe('true');
      fireEvent.click(publish);
      await waitFor(() =>
        expect(api.updateWhiteboardCompanySharing).toHaveBeenCalledWith(
          'test-session',
          board.id,
          true,
          true,
        ),
      );
      await waitFor(() =>
        expect(within(company).getByText(board.title)).toBeTruthy(),
      );

      fireEvent.keyDown(
        screen.getByRole('button', { name: i18n.t('whiteboard.actionsMenu') }),
        { key: 'ArrowDown' },
      );
      expect(
        screen.getByText(i18n.t('whiteboard.visibilityScopeNotice')),
      ).toBeTruthy();
      fireEvent.click(
        screen.getByRole('menuitem', {
          name: i18n.t('whiteboard.changeToPersonal'),
        }),
      );
      await waitFor(() =>
        expect(api.updateWhiteboardCompanySharing).toHaveBeenLastCalledWith(
          'test-session',
          board.id,
          false,
          true,
        ),
      );
      await waitFor(() =>
        expect(within(restricted).getByText(board.title)).toBeTruthy(),
      );
      expect(within(company).queryByText(board.title)).toBeNull();
      expect(window.confirm).toHaveBeenCalledTimes(1);
    },
  );
});
