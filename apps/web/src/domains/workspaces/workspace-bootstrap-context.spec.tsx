import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  WorkspaceBootstrapProvider,
  useWorkspaceBootstrapContext,
  type WorkspaceBootstrapContextValue,
} from './workspace-bootstrap-context';

function Probe() {
  const ctx = useWorkspaceBootstrapContext();
  return (
    <div>
      <span data-testid="loading">{String(ctx.loading)}</span>
      <span data-testid="error">{ctx.error ?? 'null'}</span>
      <span data-testid="apps-count">
        {ctx.data ? String(ctx.data.apps.length) : 'no-data'}
      </span>
    </div>
  );
}

function makeValue(
  overrides: Partial<WorkspaceBootstrapContextValue> = {},
): WorkspaceBootstrapContextValue {
  return {
    data: null,
    error: null,
    loading: false,
    ...overrides,
  };
}

describe('WorkspaceBootstrapContext', () => {
  it('returns the default value when no provider wraps the consumer', () => {
    // Consumers rendered outside the provider (storybook, forgotten test
    // wrappers) should degrade gracefully instead of throwing.
    render(<Probe />);
    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('error').textContent).toBe('null');
    expect(screen.getByTestId('apps-count').textContent).toBe('no-data');
  });

  it('exposes provider value to descendants', () => {
    render(
      <WorkspaceBootstrapProvider
        value={makeValue({
          loading: true,
          error: 'temporary error',
        })}
      >
        <Probe />
      </WorkspaceBootstrapProvider>,
    );
    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('error').textContent).toBe('temporary error');
  });

  it('surfaces bootstrap data to descendants', () => {
    render(
      <WorkspaceBootstrapProvider
        value={makeValue({
          data: {
            apps: [
              { app_id: 'ai', enabled: true },
              { app_id: 'pms', enabled: true },
            ],
            nav: [],
          } as WorkspaceBootstrapContextValue['data'],
        })}
      >
        <Probe />
      </WorkspaceBootstrapProvider>,
    );
    expect(screen.getByTestId('apps-count').textContent).toBe('2');
  });
});
