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
            workspace: { id: 'w1', slug: 'hq', name: 'HQ', role: 'admin' },
            apps: [
              {
                app_id: 'ai',
                title: 'AI',
                route_base: 'ai',
                icon_key: 'ai',
                enabled: true,
                nav_items: [],
              },
              {
                app_id: 'pms',
                title: 'PMS',
                route_base: 'pms',
                icon_key: 'pms',
                enabled: true,
                nav_items: [],
              },
            ],
            nav: [],
          },
        })}
      >
        <Probe />
      </WorkspaceBootstrapProvider>,
    );
    expect(screen.getByTestId('apps-count').textContent).toBe('2');
  });
});
