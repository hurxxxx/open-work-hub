import { createElement } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SpaceDocsView } from './SpaceDocsView';
import { resolveSpaceWhiteboardsRedirectPath } from './SpaceWhiteboardsView';

const mocks = vi.hoisted(() => ({
  listDocsHub: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: null }),
}));

vi.mock('@/src/app-modules/docs/public-api', async () => {
  const React = await import('react');
  return {
    DocsEmbeddedViewer: ({ itemId }: { itemId?: string | null }) =>
      React.createElement(
        'div',
        { 'data-testid': 'docs-embedded-viewer' },
        itemId,
      ),
    listDocsHub: mocks.listDocsHub,
  };
});

vi.mock('react-router-dom', async () => {
  const actual =
    await vi.importActual<typeof import('react-router-dom')>(
      'react-router-dom',
    );
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    useParams: () => ({}),
  };
});

const user = {
  workspaces: [{ id: 'default-workspace', slug: 'default' }],
};

describe('PMS space scoped redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders space docs deep links inside the PMS content surface', () => {
    render(
      createElement(
        MemoryRouter,
        null,
        createElement(SpaceDocsView, {
          docId: 'doc-1',
          spaceId: 'space-1',
        }),
      ),
    );

    expect(screen.getByTestId('docs-embedded-viewer').textContent).toBe(
      'doc-1',
    );
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy();
    expect(
      screen
        .getByRole('button', { name: /Space Docs|스페이스 문서/ })
        .getAttribute('aria-current'),
    ).toBe('page');
    expect(mocks.navigate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Gantt|간트/ }));
    expect(mocks.navigate).toHaveBeenCalledWith(
      '/apps/pms/spaces/space-1?tab=gantt',
    );
  });

  it('uses the explicit workspace slug for space whiteboard deep links', () => {
    expect(
      resolveSpaceWhiteboardsRedirectPath({
        spaceId: 'space-1',
        user,
        whiteboardId: 'board-1',
      }),
    ).toBe('/apps/whiteboard/boards/board-1?space_id=space-1');
  });
});
