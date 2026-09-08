import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { AppsBootstrapResponse } from '@/src/platform/apps/apps-api';
import { AppLauncherView } from './AppLauncherView';
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      [key, ...Object.values(options ?? {})].join(' '),
  }),
}));
const data = (apps: unknown[] = []) => ({ apps }) as AppsBootstrapResponse;
const app = (id: string, scope: string, enabled = true) => ({
  app_id: id,
  execution_context_kind: scope,
  enabled,
  title: id,
  icon_key: 'file',
});
function view(
  value: AppsBootstrapResponse | null,
  error: string | null = null,
  loading = false,
) {
  return render(
    <MemoryRouter>
      <AppLauncherView data={value} error={error} loading={loading} />
    </MemoryRouter>,
  );
}
describe('company launcher', () => {
  it('shows an empty catalog without requesting an outer container', () => {
    view(data());
    expect(
      screen.getByRole('heading', { name: 'launcher.noAppsTitle' }),
    ).toBeTruthy();
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });
  it('groups admitted company and personal apps and uses direct routes', () => {
    view(data([app('docs', 'company'), app('planner', 'personal')]));
    expect(
      screen.getByRole('heading', { name: 'launcher.companyApp' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: 'launcher.personalApp' }),
    ).toBeTruthy();
    expect(
      screen.getByRole('link', { name: /apps.docs/ }).getAttribute('href'),
    ).toBe('/apps/docs');
    expect(
      screen.getByRole('link', { name: /apps.planner/ }).getAttribute('href'),
    ).toBe('/apps/planner');
  });
  it('removes revoked apps and shows empty state if every app is disabled', () => {
    const rendered = view(data([app('docs', 'company')]));
    expect(screen.getByRole('link', { name: /apps.docs/ })).toBeTruthy();
    rendered.rerender(
      <MemoryRouter>
        <AppLauncherView
          data={data([app('docs', 'company', false)])}
          error={null}
          loading={false}
        />
      </MemoryRouter>,
    );
    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(
      screen.getByRole('heading', { name: 'launcher.noAppsTitle' }),
    ).toBeTruthy();
  });
  it('shows loading and fetch errors', () => {
    const rendered = view(null, null, true);
    expect(screen.getByRole('status')).toBeTruthy();
    rendered.rerender(
      <MemoryRouter>
        <AppLauncherView data={null} error="Load failed" loading={false} />
      </MemoryRouter>,
    );
    expect(screen.getByText('Load failed')).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
  });
});
