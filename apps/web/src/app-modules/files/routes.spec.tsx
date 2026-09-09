import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { filesAppRoutes } from './routes';

vi.mock('./views/FileManagerView', () => ({
  FileManagerView: () => <div>file-manager-view</div>,
}));

vi.mock('./views/FileSearchView', () => ({
  FileSearchView: () => <div>file-search-view</div>,
}));

vi.mock('./views/FilesChatView', () => ({
  FilesChatView: () => <div>files-chat-view</div>,
}));

async function renderFilesRoute(path: string) {
  const route = filesAppRoutes.find((candidate) =>
    path.endsWith('/chat')
      ? candidate.path.endsWith('/chat')
      : candidate.path === '/apps/files',
  );
  if (!route) {
    throw new Error(`Files route is not registered for ${path}`);
  }
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={route.element} path={route.path} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Files routes', () => {
  it('renders document chat at the dedicated Files route', async () => {
    await renderFilesRoute('/apps/files/chat');
    expect(await screen.findByText('files-chat-view')).toBeTruthy();
    expect(screen.queryByText('file-manager-view')).toBeNull();
  });

  it('selects search only for the Files search view query', async () => {
    await renderFilesRoute('/apps/files?view=search');
    expect(await screen.findByText('file-search-view')).toBeTruthy();
    expect(screen.queryByText('file-manager-view')).toBeNull();
  });

  it('keeps the existing file manager as the default view', async () => {
    await renderFilesRoute('/apps/files');
    expect(await screen.findByText('file-manager-view')).toBeTruthy();
    expect(screen.queryByText('file-search-view')).toBeNull();
  });
});
