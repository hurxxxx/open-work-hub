import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AdminModelRuntimeStatusSection } from './admin-model-runtime-status-section';
import { getAdminModelRuntimeStatus } from './admin-model-runtime-status-api';

vi.mock('./admin-model-runtime-status-api', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('./admin-model-runtime-status-api')>();
  return { ...actual, getAdminModelRuntimeStatus: vi.fn() };
});

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

const getStatusMock = vi.mocked(getAdminModelRuntimeStatus);

describe('AdminModelRuntimeStatusSection', () => {
  beforeEach(() => {
    getStatusMock.mockReset();
  });

  it('shows target availability and loaded model names', async () => {
    getStatusMock.mockResolvedValue({
      checked_at: '2026-07-13T02:00:00Z',
      status: 'degraded',
      targets: [
        {
          id: 'inference-gateway',
          display_name: 'Inference gateway',
          kind: 'inference_gateway',
          role: 'diagnostic',
          provider_id: null,
          status: 'online',
          error_code: null,
          models: [
            {
              name: 'dragonkue/snowflake-arctic-embed-l-v2.0-ko',
              task: 'embedding',
              loaded: true,
            },
          ],
        },
        {
          id: 'local-model-a',
          display_name: 'Local Model A',
          kind: 'llm',
          role: 'redundancy',
          provider_id: 'local',
          status: 'offline',
          error_code: 'timeout',
          models: [],
        },
      ],
    });

    render(<AdminModelRuntimeStatusSection token="token" />);

    expect(
      await screen.findByText('dragonkue/snowflake-arctic-embed-l-v2.0-ko'),
    ).toBeTruthy();
    expect(screen.getByText('2026-07-13T02:00:00Z')).toBeTruthy();
    await waitFor(() => {
      expect(getStatusMock).toHaveBeenCalledWith('token');
    });
  });

  it('keeps the page usable when loading fails', async () => {
    getStatusMock.mockRejectedValue(new Error('network'));

    render(<AdminModelRuntimeStatusSection token="token" />);

    expect(await screen.findByRole('alert')).toBeTruthy();
    expect(screen.getByRole('button')).toBeTruthy();
  });
});
