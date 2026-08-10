import { describe, expect, it } from 'vitest';

import {
  calculateSubSidebarCreateMenuPosition,
  clampSubSidebarWidth,
  isSubSidebarCreateMenuOpen,
  restoreSubSidebarCollapsed,
  restoreSubSidebarPinned,
  restoreSubSidebarWidth,
  resolveSubSidebarPreviewOpenAfterPinnedChange,
  serializeSubSidebarCollapsed,
  serializeSubSidebarPinned,
  setSubSidebarCreateMenuOpen,
  widthFromSubSidebarPointer,
} from './sub-sidebar-frame-model';

describe('sub-sidebar frame model', () => {
  it('restores only persisted widths inside the allowed range', () => {
    expect(restoreSubSidebarWidth('320')).toBe(320);
    expect(restoreSubSidebarWidth('179')).toBe(240);
    expect(restoreSubSidebarWidth('481')).toBe(240);
    expect(restoreSubSidebarWidth('not-a-number')).toBe(240);
    expect(restoreSubSidebarWidth(null)).toBe(240);
  });

  it('clamps pointer-driven widths around the main nav rail', () => {
    expect(clampSubSidebarWidth(160)).toBe(180);
    expect(clampSubSidebarWidth(520)).toBe(480);
    expect(widthFromSubSidebarPointer(64 + 360)).toBe(360);
    expect(widthFromSubSidebarPointer(20)).toBe(180);
  });

  it('serializes and restores collapsed state', () => {
    expect(serializeSubSidebarCollapsed(true)).toBe('1');
    expect(serializeSubSidebarCollapsed(false)).toBe('0');
    expect(restoreSubSidebarCollapsed('1')).toBe(true);
    expect(restoreSubSidebarCollapsed('0')).toBe(false);
    expect(restoreSubSidebarCollapsed(null)).toBe(false);
  });

  it('serializes and restores pinned state', () => {
    expect(serializeSubSidebarPinned(true)).toBe('1');
    expect(serializeSubSidebarPinned(false)).toBe('0');
    expect(restoreSubSidebarPinned('1')).toBe(true);
    expect(restoreSubSidebarPinned('0')).toBe(false);
    expect(restoreSubSidebarPinned(null)).toBe(true);
  });

  it('closes the desktop preview when pinned state changes', () => {
    expect(resolveSubSidebarPreviewOpenAfterPinnedChange()).toBe(false);
  });

  it('scopes create-menu open state to the active app', () => {
    const state = { appId: 'chatbot', open: true };

    expect(isSubSidebarCreateMenuOpen(state, 'chatbot')).toBe(true);
    expect(isSubSidebarCreateMenuOpen(state, 'docs')).toBe(false);
    expect(setSubSidebarCreateMenuOpen(state, 'docs', true)).toEqual({
      appId: 'docs',
      open: true,
    });
    expect(
      setSubSidebarCreateMenuOpen(
        { appId: 'docs', open: true },
        'docs',
        (open) => !open,
      ),
    ).toEqual({
      appId: 'docs',
      open: false,
    });
  });

  it('keeps the create menu inside the sidebar inset when possible', () => {
    expect(
      calculateSubSidebarCreateMenuPosition({
        sidebarRect: { left: 64, right: 304 },
        buttonRect: { right: 296, bottom: 80 },
      }),
    ).toEqual({
      left: 88,
      top: 84,
    });
  });

  it('pins the create menu to the left inset when the button is too far left', () => {
    expect(
      calculateSubSidebarCreateMenuPosition({
        sidebarRect: { left: 64, right: 304 },
        buttonRect: { right: 120, bottom: 80 },
      }),
    ).toEqual({
      left: 72,
      top: 84,
    });
  });
});
