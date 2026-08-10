import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { newsGlobalRoutes } from './routes';

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location">
      {location.pathname}
      {location.search}
      {location.hash}
    </div>
  );
}

describe('news routes', () => {
  it('keeps the canonical and legacy alias in the global route registry', () => {
    expect(newsGlobalRoutes.map((route) => route.path)).toEqual([
      '/news',
      '/w/:workspaceSlug/news',
    ]);
  });

  it('redirects the legacy workspace URL while preserving query and hash', async () => {
    const legacyRoute = newsGlobalRoutes.find(
      (route) => route.path === '/w/:workspaceSlug/news',
    );
    expect(legacyRoute).toBeDefined();

    render(
      <MemoryRouter
        initialEntries={['/w/research/news?view=report&tab=kdi#report-section']}
      >
        <Routes>
          {legacyRoute ? (
            <Route path={legacyRoute.path} element={legacyRoute.element} />
          ) : null}
          <Route path="/news" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    expect((await screen.findByTestId('location')).textContent).toBe(
      '/news?view=report&tab=kdi#report-section',
    );
  });
});
