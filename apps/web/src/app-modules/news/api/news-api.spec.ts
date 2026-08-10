import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchNewsChannel } from './news-api';

const clientMocks = vi.hoisted(() => ({
  apiFetchJsonWithMappedError: vi.fn(),
}));

vi.mock('@/src/platform/api/client', () => clientMocks);

describe('News API paths', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clientMocks.apiFetchJsonWithMappedError.mockResolvedValue({});
  });

  it('requests a news channel from its canonical endpoint', async () => {
    await fetchNewsChannel('token-1', 'keyword');

    expect(
      clientMocks.apiFetchJsonWithMappedError.mock.calls.map(([path]) => path),
    ).toEqual(['/api/v1/news/keyword']);
  });
});
