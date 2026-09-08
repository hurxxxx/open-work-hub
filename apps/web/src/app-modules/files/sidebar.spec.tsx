import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { FilesChatSidebarLink } from './sidebar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe('FilesChatSidebarLink', () => {
  it('provides a Files chat fallback when workspace bootstrap nav is stale', () => {
    const onNavigate = vi.fn();
    render(
      <MemoryRouter initialEntries={['/apps/files/chat']}>
        <FilesChatSidebarLink
          hasBootstrapItem={false}
          onNavigate={onNavigate}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: 'nav.files-chat' });
    expect(link.getAttribute('href')).toBe('/apps/files/chat');
    expect(link.className).toContain('sidebar-submenu-item-active');
    fireEvent.click(link);
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it('avoids a duplicate after bootstrap starts returning files-chat', () => {
    render(
      <MemoryRouter>
        <FilesChatSidebarLink hasBootstrapItem />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link')).toBeNull();
  });
});
