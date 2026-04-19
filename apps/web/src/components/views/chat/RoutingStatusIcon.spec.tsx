import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type {
  LlmHealthResponse,
  LlmPoolHealthResponse,
} from '@/src/domains/ai/ai-api';

import { RoutingStatusIcon } from './RoutingStatusIcon';

function pool(
  overrides: Partial<LlmPoolHealthResponse> = {},
): LlmPoolHealthResponse {
  return {
    pool: 'local',
    provider: 'ollama',
    base_url: 'http://localhost',
    model: 'qwen3.6-35b',
    canonical_model: 'qwen3.6-35b-a3b',
    status: 'ready',
    ready: true,
    detail: null,
    ...overrides,
  };
}

function health(overrides: Partial<LlmHealthResponse> = {}): LlmHealthResponse {
  return {
    ready: true,
    local: pool(),
    external: null,
    ...overrides,
  };
}

describe('RoutingStatusIcon', () => {
  it('is healthy in local mode when local pool is ready', () => {
    render(
      <RoutingStatusIcon
        backendMode="local"
        health={health()}
        healthError={null}
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('emerald');
  });

  it('is unhealthy in local mode when local is down even if external is up', () => {
    render(
      <RoutingStatusIcon
        backendMode="local"
        health={health({
          local: pool({ ready: false, status: 'unavailable' }),
          external: pool({ pool: 'external', ready: true }),
        })}
        healthError={null}
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('amber');
  });

  it('is healthy in auto mode when external is the only ready pool', () => {
    // Regression: RoutingStatusIcon used to check only local.ready, which
    // showed a false warning even though backend `LlmDualHealth.ready` is
    // `local.ready || external.ready` and routing still worked.
    render(
      <RoutingStatusIcon
        backendMode="auto"
        health={health({
          local: pool({ ready: false, status: 'unavailable' }),
          external: pool({ pool: 'external', ready: true }),
        })}
        healthError={null}
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('emerald');
  });

  it('is unhealthy in auto mode when both pools are down', () => {
    render(
      <RoutingStatusIcon
        backendMode="auto"
        health={health({
          local: pool({ ready: false, status: 'unavailable' }),
          external: pool({ pool: 'external', ready: false, status: 'model_missing' }),
        })}
        healthError={null}
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('amber');
  });

  it('is unhealthy when healthError is set, regardless of pool state', () => {
    render(
      <RoutingStatusIcon
        backendMode="auto"
        health={health()}
        healthError="timeout"
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('amber');
  });

  it('is unhealthy while health is still loading', () => {
    render(
      <RoutingStatusIcon
        backendMode="auto"
        health={null}
        healthError={null}
      />,
    );
    expect(screen.getByLabelText('라우팅 상태').className).toContain('amber');
  });
});
