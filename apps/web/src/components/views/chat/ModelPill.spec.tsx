import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  LlmHealthResponse,
  LlmPoolHealthResponse,
} from '@/src/domains/ai/ai-api';

import { ModelPill, computePanelPosition } from './ModelPill';

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

describe('ModelPill', () => {
  it('shows loading label when health is null', () => {
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={null}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    expect(screen.getByText('자동 · 확인 중')).not.toBeNull();
  });

  it('shows canonical model name in local mode', () => {
    render(
      <ModelPill
        backendMode="local"
        onBackendModeChange={vi.fn()}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    expect(screen.getByText('qwen3.6-35b-a3b · 로컬')).not.toBeNull();
  });

  it('opens popover on click and renders mode options + refresh control', () => {
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 라우팅/ }));
    expect(screen.getByRole('dialog')).not.toBeNull();
    expect(screen.getByText('자동')).not.toBeNull();
    expect(screen.getByText('로컬')).not.toBeNull();
    expect(screen.getByText('Local pool')).not.toBeNull();
    expect(screen.getByText('External pool')).not.toBeNull();
    expect(screen.getByText('상태 새로고침')).not.toBeNull();
  });

  it('invokes onBackendModeChange when a mode option is clicked', () => {
    const handleChange = vi.fn();
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={handleChange}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 라우팅/ }));
    fireEvent.click(screen.getByText('로컬'));
    expect(handleChange).toHaveBeenCalledWith('local');
  });

  it('invokes onRefreshHealth when refresh button is clicked', () => {
    const handleRefresh = vi.fn();
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={handleRefresh}
        canRefresh
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 라우팅/ }));
    fireEvent.click(screen.getByRole('button', { name: '상태 새로고침' }));
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('disables refresh button when canRefresh is false', () => {
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 라우팅/ }));
    const refreshButton = screen.getByRole('button', { name: '상태 새로고침' });
    expect((refreshButton as HTMLButtonElement).disabled).toBe(true);
  });

  it('surfaces healthError text inside the popover', () => {
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={null}
        healthError="모델 상태를 확인하지 못했습니다."
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 · 확인 중/ }));
    expect(screen.getByText('모델 상태를 확인하지 못했습니다.')).not.toBeNull();
  });

  describe('computePanelPosition', () => {
    // Default desiredWidth=320, margin=8, offset=8 match the production panel.

    it('right-aligns panel with trigger on wide viewports', () => {
      // Trigger at x=800..900 in a 1440px viewport → panel fits fully, right edges aligned.
      const pos = computePanelPosition(
        { bottom: 48, right: 900 },
        1440,
      );
      expect(pos.width).toBe(320);
      expect(pos.left).toBe(580); // 900 - 320
      expect(pos.top).toBe(56);
    });

    it('clamps panel left edge to margin on narrow viewports', () => {
      // iPhone SE 320px viewport, trigger near right edge (x=270..300).
      // Preferred left = 300 - 320 = -20 → would overflow left. Width shrinks
      // to viewport - 2*margin = 304 and left clamps to margin=8.
      const pos = computePanelPosition(
        { bottom: 48, right: 300 },
        320,
      );
      expect(pos.width).toBe(304);
      expect(pos.left).toBe(8);
      expect(pos.left + pos.width).toBeLessThanOrEqual(320 - 8);
    });

    it('clamps panel right edge to margin when trigger is past viewport', () => {
      // Pathological: trigger reported right=500 but viewport is 320.
      // Panel must not extend past viewportWidth - margin.
      const pos = computePanelPosition(
        { bottom: 48, right: 500 },
        320,
      );
      expect(pos.left + pos.width).toBeLessThanOrEqual(320 - 8);
      expect(pos.left).toBeGreaterThanOrEqual(8);
    });

    it('keeps full width when viewport is exactly the desired width plus margins', () => {
      const pos = computePanelPosition(
        { bottom: 48, right: 336 },
        336, // 320 + 2*8
      );
      expect(pos.width).toBe(320);
      expect(pos.left).toBe(8);
    });

    it('always keeps panel within viewport regardless of trigger rect', () => {
      // Fuzz-ish sweep: 320..1920 viewports × a few trigger positions.
      for (const viewport of [320, 375, 414, 768, 1024, 1440, 1920]) {
        for (const triggerRight of [10, viewport / 2, viewport - 10, viewport + 50]) {
          const pos = computePanelPosition(
            { bottom: 48, right: triggerRight },
            viewport,
          );
          expect(pos.left).toBeGreaterThanOrEqual(8);
          expect(pos.left + pos.width).toBeLessThanOrEqual(viewport - 8);
          expect(pos.width).toBeGreaterThan(0);
        }
      }
    });
  });

  it('closes the popover when Escape is pressed', () => {
    render(
      <ModelPill
        backendMode="auto"
        onBackendModeChange={vi.fn()}
        health={health()}
        healthError={null}
        isCheckingHealth={false}
        onRefreshHealth={vi.fn()}
        canRefresh
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /자동 라우팅/ }));
    expect(screen.queryByRole('dialog')).not.toBeNull();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
