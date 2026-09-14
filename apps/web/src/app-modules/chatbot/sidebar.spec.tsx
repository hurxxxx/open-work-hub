import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AppSidebarRenderContext } from '@/src/app/shell/sidebar-types';
import { ChatbotSidebarPortal, chatbotSidebarConfig } from './sidebar';

function context(
  overrides: Partial<AppSidebarRenderContext> = {},
): AppSidebarRenderContext {
  return {
    activeAppId: 'chatbot',
    activeNavItemId: '',
    currentPathname: '/apps/chatbot',
    enabledShellAppIds: ['chatbot'],
    canReadApp: true,
    filteredItems: [],
    user: null,
    navigate: vi.fn(),
    isCategoryExpanded: () => true,
    toggleCategory: vi.fn(),
    ...overrides,
  };
}

describe('chatbot sidebar registration', () => {
  it('moves one route-owned list into the mobile host and closes on navigation', () => {
    const close = vi.fn();
    const desktop = context();
    const mobile = context({ onNavigate: close });
    function Surface({ mobileOpen }: { mobileOpen: boolean }) {
      return (
        <>
          <div data-testid="desktop">
            {chatbotSidebarConfig.beforeCategories?.(desktop)}
          </div>
          {mobileOpen ? (
            <div data-testid="mobile">
              {chatbotSidebarConfig.beforeCategories?.(mobile)}
            </div>
          ) : null}
          <ChatbotSidebarPortal>
            {(onNavigate) => (
              <button onClick={onNavigate}>Select conversation</button>
            )}
          </ChatbotSidebarPortal>
        </>
      );
    }
    const { rerender } = render(<Surface mobileOpen={false} />);
    expect(screen.getByTestId('desktop').textContent).toBe(
      'Select conversation',
    );
    rerender(<Surface mobileOpen />);
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getByTestId('desktop').textContent).toBe('');
    fireEvent.click(screen.getByRole('button'));
    expect(close).toHaveBeenCalledOnce();
    rerender(<Surface mobileOpen={false} />);
    expect(screen.getByTestId('desktop').textContent).toBe(
      'Select conversation',
    );
  });

  it('does not provide a destination when app access is denied', () => {
    expect(
      chatbotSidebarConfig.beforeCategories?.(context({ canReadApp: false })),
    ).toBeNull();
  });
});
