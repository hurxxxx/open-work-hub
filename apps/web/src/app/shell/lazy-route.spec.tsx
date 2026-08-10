import { fireEvent, render, screen } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
} from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { lazyRoute, LazyRouteErrorBoundary } from './lazy-route';

function BrokenRoute(): ReactNode {
  throw new TypeError('Failed to fetch dynamically imported module');
}

function BrokenRouteWithoutReload(): ReactNode {
  throw new TypeError('Lazy route render failed');
}

function RouteSwitcher() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate('/healthy')}>
        Switch route
      </button>
      <Routes>
        <Route
          path="/broken"
          element={lazyRoute(<BrokenRouteWithoutReload />)}
        />
        <Route path="/healthy" element={lazyRoute(<p>Healthy route</p>)} />
      </Routes>
    </>
  );
}

describe('LazyRouteErrorBoundary', () => {
  it('preserves the route element key on the error boundary', () => {
    const route = lazyRoute(createElement('div', { key: 'route-one' }));

    expect(route.key).toBe('route-one');
  });

  it('recovers stale lazy imports and keeps a reload action on screen', () => {
    const recoverFromError = vi.fn(() => true);
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    render(
      <LazyRouteErrorBoundary recoverFromError={recoverFromError}>
        <BrokenRoute />
      </LazyRouteErrorBoundary>,
    );

    expect(recoverFromError).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Failed to fetch dynamically imported module',
      }),
    );
    expect(screen.getByRole('alert').textContent).toContain(
      '앱 화면을 불러오지 못했습니다.',
    );
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeTruthy();

    consoleError.mockRestore();
  });

  it('clears a failed boundary after navigating to another lazy route', () => {
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    render(
      <MemoryRouter initialEntries={['/broken']}>
        <RouteSwitcher />
      </MemoryRouter>,
    );

    expect(screen.getByRole('alert')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Switch route' }));
    expect(screen.getByText('Healthy route')).toBeTruthy();

    consoleError.mockRestore();
  });
});
