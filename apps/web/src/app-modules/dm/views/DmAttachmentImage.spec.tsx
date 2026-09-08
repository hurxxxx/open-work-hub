import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getDmAttachmentPreviewUrl } from '../api/dm-api';
import { authenticatedContentObjectUrl } from '@/src/platform/browser/browser-download';
import { DmAttachmentImage } from './DmAttachmentImage';
vi.mock('../api/dm-api', () => ({ getDmAttachmentPreviewUrl: vi.fn() }));
vi.mock('@/src/platform/browser/browser-download', () => ({
  authenticatedContentObjectUrl: vi.fn(),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
const preview = vi.mocked(getDmAttachmentPreviewUrl),
  objectUrl = vi.mocked(authenticatedContentObjectUrl);
function image(token = 'token', attachmentId = 'attachment') {
  return (
    <DmAttachmentImage
      token={token}
      attachmentId={attachmentId}
      alt="Attachment image"
      className="preview"
    />
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  preview.mockResolvedValue({ url: '/api/v1/content#grant=example' });
  objectUrl.mockResolvedValue('blob:resolved');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
});
describe('session-bound DM attachment images', () => {
  it('fetches current-session access and renders a blob without exposing the grant', async () => {
    const result = render(image());
    const rendered = await screen.findByRole('img');
    expect(preview).toHaveBeenCalledWith('token', 'attachment');
    expect(objectUrl).toHaveBeenCalledWith(
      'token',
      '/api/v1/content#grant=example',
    );
    expect(rendered.getAttribute('src')).toBe('blob:resolved');
    expect(document.querySelector('[src*="grant="]')).toBeNull();
    result.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:resolved');
  });
  it('does not fetch bytes for an old account after its grant resolves late', async () => {
    let resolveOld!: (value: { url: string }) => void;
    preview
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValueOnce({ url: '/api/v1/content#grant=current' });
    const result = render(image('old'));
    result.rerender(image('new'));
    await screen.findByRole('img');
    await act(async () => resolveOld({ url: '/api/v1/content#grant=stale' }));
    expect(objectUrl).toHaveBeenCalledTimes(1);
    expect(objectUrl).toHaveBeenCalledWith(
      'new',
      '/api/v1/content#grant=current',
    );
  });
  it('revokes a late blob after unmount instead of rendering stale content', async () => {
    let resolveBlob!: (value: string) => void;
    objectUrl.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveBlob = resolve;
        }),
    );
    const result = render(image());
    await waitFor(() => expect(objectUrl).toHaveBeenCalledTimes(1));
    result.unmount();
    await act(async () => resolveBlob('blob:late'));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:late');
    expect(screen.queryByRole('img')).toBeNull();
  });
  it('does not render a URL when access is denied', async () => {
    preview.mockRejectedValue(new Error('Forbidden'));
    render(image());
    await screen.findByText('dm.errors.attachmentPreviewFailed');
    expect(objectUrl).not.toHaveBeenCalled();
    expect(screen.queryByRole('img')).toBeNull();
  });
});
