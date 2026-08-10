import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { filesWorkspaceRoutes } from './routes';

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
  const route = filesWorkspaceRoutes.find((candidate) =>
    candidate.path.endsWith(
      path.includes('/files/chat') ? '/files/chat' : '/files',
    ),
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
    await renderFilesRoute('/w/hq/files/chat');
    expect(await screen.findByText('files-chat-view')).toBeTruthy();
    expect(screen.queryByText('file-manager-view')).toBeNull();
  });

  it('selects search only for the Files search view query', async () => {
    await renderFilesRoute('/w/hq/files?view=search');
    expect(await screen.findByText('file-search-view')).toBeTruthy();
    expect(screen.queryByText('file-manager-view')).toBeNull();
  });

  it('keeps the existing file manager as the default view', async () => {
    await renderFilesRoute('/w/hq/files');
    expect(await screen.findByText('file-manager-view')).toBeTruthy();
    expect(screen.queryByText('file-search-view')).toBeNull();
  });
});
