import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { HealthCheckupSourceStatus } from '../api/health-checkup-api';
import { HealthCheckupSourceStatusPanel } from './HealthCheckupSourceStatusPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number; defaultValue?: string }) => {
      if (key === 'apps:healthCheckup.source.accepted') {
        return `Accepted ${options?.count ?? 0}`;
      }
      return options?.defaultValue ?? key;
    },
  }),
}));

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <span>{value}</span>,
}));

const acceptedStatus = {
  available: true,
  reason: null,
  run_id: 'run-accepted',
  captured_at: '2026-07-22T00:00:00Z',
  employee_count: 711,
  schema_version: 'erp-employee-view-v1',
} as HealthCheckupSourceStatus;

describe('HealthCheckupSourceStatusPanel', () => {
  it('renders the accepted source metadata and refreshes without a sync action', () => {
    const onRefresh = vi.fn();
    render(
      <HealthCheckupSourceStatusPanel
        loading={false}
        onRefresh={onRefresh}
        refreshing={false}
        status={acceptedStatus}
      />,
    );

    expect(screen.getByText('Accepted 711')).toBeTruthy();
    expect(screen.getByText('run-accepted')).toBeTruthy();
    expect(screen.queryByText(/sync/i)).toBeNull();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:healthCheckup.source.refresh',
      }),
    );
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('shows a safe unavailable fallback instead of a raw reason', () => {
    render(
      <HealthCheckupSourceStatusPanel
        loading={false}
        onRefresh={vi.fn()}
        refreshing={false}
        status={{
          ...acceptedStatus,
          available: false,
          reason: 'credentials-with-secret-like-data',
        }}
      />,
    );

    expect(
      screen.getByText('apps:healthCheckup.source.unavailable'),
    ).toBeTruthy();
    expect(screen.queryByText('credentials-with-secret-like-data')).toBeNull();
  });
});
