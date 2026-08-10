import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';
import type { HealthCheckupController } from './useHealthCheckupController';
import { HealthCheckupView } from './HealthCheckupView';

const state = vi.hoisted(() => ({
  controller: null as HealthCheckupController | null,
}));

vi.mock('@ai-do/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ai-do/ui')>()),
  useToast: () => ({ error: vi.fn(), success: vi.fn() }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token' }),
}));

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useParams: () => ({ workspaceSlug: 'management' }),
}));

vi.mock('./useHealthCheckupController', () => ({
  useHealthCheckupController: () => state.controller,
}));

function controller(
  overrides: Partial<HealthCheckupController> = {},
): HealthCheckupController {
  return {
    determinations: {
      run_id: 'run-2026',
      status: 'ready',
      target_year: 2026,
      prior_year: 2025,
      publishable: true,
      publish_blockers: [],
      source: {
        available: true,
        reason: null,
        run_id: 'source-run',
        captured_at: '2026-07-22T00:00:00Z',
        employee_count: 0,
        schema_version: 'erp-employee-view-v1',
      },
      prior_exam_uploaded: true,
      total: 1,
      target_count: 1,
      items: [
        {
          employee_id: 'employee-1',
          employee_code: '100001',
          name: '홍길동',
          dept_name: '인사팀',
          position: '대리',
          hire_date: '2010-01-01',
          birth_date: '1980-01-01',
          age: 47,
          service_years: 16,
          is_senior: false,
          is_adult: true,
          is_long_service: true,
          prior_year_examined: false,
          is_target: true,
          reason: 'adult_or_service',
        },
      ],
    },
    fatalAccessDenied: false,
    history: [],
    loadingDeterminations: false,
    loadingSettings: false,
    loadingSource: false,
    priorStatus: null,
    refreshingSource: false,
    refreshSourceAndDeterminations: vi.fn(),
    saveSettings: vi.fn(),
    savingSettings: false,
    settings: {
      age_calc_method: 'international',
      senior_age: 61,
      adult_age: 43,
      service_years_threshold: 12,
      updated_by: null,
      updated_at: null,
    },
    sourceStatus: {
      available: true,
      reason: null,
      run_id: 'source-run',
      captured_at: '2026-07-22T00:00:00Z',
      employee_count: 0,
      schema_version: 'erp-employee-view-v1',
    },
    uploadPriorExamFile: vi.fn(),
    uploadResult: null,
    uploading: false,
    ...overrides,
  };
}

describe('HealthCheckupView', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('ko-KR');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // Personal data is gated behind a privacy reveal; open it before asserting.
  const revealTargets = () =>
    fireEvent.click(screen.getByRole('button', { name: '대상자 명단 표시' }));

  it('gates personal data until the privacy reveal is clicked', () => {
    state.controller = controller();
    render(<HealthCheckupView />);

    expect(screen.queryByText('61세 이상')).toBeNull();
    revealTargets();
    expect(screen.getAllByText('61세 이상').length).toBeGreaterThan(0);
  });

  it('moves focus into the revealed content and restores it after auto-hide', () => {
    vi.useFakeTimers();
    state.controller = controller();
    render(<HealthCheckupView />);

    const revealControl = screen.getByRole('button', {
      name: '대상자 명단 표시',
    });
    fireEvent.click(revealControl);

    expect(document.activeElement).toBe(
      screen.getByRole('tab', { name: '종합검진 대상자' }),
    );

    act(() => {
      vi.advanceTimersByTime(5 * 60 * 1000);
    });

    const restoredRevealControl = screen.getByRole('button', {
      name: '대상자 명단 표시',
    });
    expect(document.activeElement).toBe(restoredRevealControl);
    expect(restoredRevealControl.getAttribute('aria-expanded')).toBe('false');
  });

  it('gives compact boolean marks localized accessible names', () => {
    state.controller = controller();
    render(<HealthCheckupView />);
    revealTargets();

    expect(screen.getAllByRole('cell', { name: '예' })).toHaveLength(2);
    expect(screen.getAllByRole('cell', { name: '아니오' })).toHaveLength(2);
    for (const mark of screen.getAllByText('O')) {
      expect(mark.getAttribute('aria-hidden')).toBe('true');
    }
    for (const mark of screen.getAllByText('-')) {
      expect(mark.getAttribute('aria-hidden')).toBe('true');
    }
  });

  it('uses the current settings in determination column headers', () => {
    state.controller = controller();
    render(<HealthCheckupView />);
    revealTargets();

    expect(screen.getAllByText('61세 이상').length).toBeGreaterThan(0);
    expect(screen.getAllByText('43세 이상').length).toBeGreaterThan(0);
    expect(screen.getAllByText('근속연수 12년 이상').length).toBeGreaterThan(0);
  });

  it('disables upload and export actions while determinations are loading', () => {
    state.controller = controller({ loadingDeterminations: true });
    render(<HealthCheckupView />);
    revealTargets();

    expect(
      (
        screen.getByRole('button', {
          name: '전년도 명단 업로드',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole('button', {
          name: '최종 명단(xlsx) 산출',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it('renders large employee lists one page at a time', () => {
    const base = controller();
    const first = base.determinations?.items[0];
    if (!base.determinations || !first) throw new Error('missing test fixture');
    state.controller = controller({
      determinations: {
        ...base.determinations,
        total: 51,
        target_count: 51,
        items: Array.from({ length: 51 }, (_, index) => ({
          ...first,
          employee_id: `employee-${index + 1}`,
          employee_code: String(100000 + index + 1),
          name: `직원${index + 1}`,
        })),
      },
    });
    render(<HealthCheckupView />);
    revealTargets();

    expect(screen.queryAllByText('직원25').length).toBeGreaterThan(0);
    expect(screen.queryAllByText('직원26')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: '다음 페이지' }));

    expect(screen.queryAllByText('직원26').length).toBeGreaterThan(0);
    expect(screen.queryAllByText('직원25')).toHaveLength(0);
  });
});
