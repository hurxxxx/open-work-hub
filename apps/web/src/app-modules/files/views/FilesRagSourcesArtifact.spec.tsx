import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import {
  buildFilesRagSourcesPreview,
  FilesRagSourcesArtifact,
} from './FilesRagSourcesArtifact';
import { getFileDownloadUrl } from '../api/files-api';
import { openDownloadUrl } from '@/src/platform/browser/browser-download';

const logout = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options?.name ? `${key}:${options.name}` : key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    logout,
    token: 'token-1',
  }),
}));

vi.mock('../api/files-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/files-api')>();
  return {
    ...actual,
    getFileDownloadUrl: vi
      .fn()
      .mockResolvedValue({ url: '/fresh-download/file-1' }),
  };
});

vi.mock('@/src/platform/browser/browser-download', async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import('@/src/platform/browser/browser-download')
    >();
  return {
    ...actual,
    openDownloadUrl: vi.fn(),
  };
});

function renderSources(content: string) {
  render(
    <MemoryRouter initialEntries={['/w/hq/files/chat']}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/files/chat"
          element={<FilesRagSourcesArtifact content={content} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('FilesRagSourcesArtifact', () => {
  it('builds a compact filename preview for the collapsed artifact card', () => {
    expect(
      buildFilesRagSourcesPreview(
        JSON.stringify({
          version: 1,
          sources: [
            { ref: 'F1', file_id: 'file-1', filename: 'roadmap.pdf' },
            { ref: 'F2', file_id: 'file-2', filename: 'release-notes.md' },
          ],
        }),
      ),
    ).toBe('roadmap.pdf · release-notes.md');
    expect(buildFilesRagSourcesPreview('not-json')).toBeNull();
  });

  it('renders document citations and requests a fresh ACL-checked download URL', async () => {
    renderSources(
      JSON.stringify({
        version: 1,
        sources: [
          {
            ref: 'F1',
            file_id: 'file-1',
            filename: 'roadmap.pdf',
            locator: 'page 4',
            methods: ['bm25', 'dense_vector'],
          },
        ],
      }),
    );

    expect(screen.getByText('F1')).toBeTruthy();
    expect(screen.getByText('roadmap.pdf')).toBeTruthy();
    expect(screen.getByText('page 4')).toBeTruthy();
    expect(screen.getByText('bm25')).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'files.chat.sources.download:roadmap.pdf',
      }),
    );

    await waitFor(() => {
      expect(getFileDownloadUrl).toHaveBeenCalledWith(
        'token-1',
        'hq',
        'file-1',
      );
      expect(openDownloadUrl).toHaveBeenCalledWith('/fresh-download/file-1');
    });
  });

  it('fails closed when the artifact payload is malformed', () => {
    renderSources('not-json');
    expect(screen.getByText('files.chat.sources.invalid')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
