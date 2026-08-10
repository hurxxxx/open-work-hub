import { describe, expect, it } from 'vitest';

import {
  calculateCoreSubSidebarCreateMenuPosition,
  clampCoreSubSidebarWidth,
  isCoreSubSidebarCreateMenuOpen,
  restoreCoreSubSidebarCollapsed,
  restoreCoreSubSidebarPinned,
  restoreCoreSubSidebarWidth,
  resolveCoreSubSidebarPreviewOpenAfterPinnedChange,
  serializeCoreSubSidebarCollapsed,
  serializeCoreSubSidebarPinned,
  setCoreSubSidebarCreateMenuOpen,
  widthFromCoreSubSidebarPointer,
} from './sub-sidebar-frame';

describe('core sub-sidebar frame model', () => {
  it('restores and clamps persisted widths', () => {
    expect(restoreCoreSubSidebarWidth('320')).toBe(320);
    expect(restoreCoreSubSidebarWidth('179')).toBe(240);
    expect(restoreCoreSubSidebarWidth('481')).toBe(240);
    expect(restoreCoreSubSidebarWidth('not-a-number')).toBe(240);
    expect(restoreCoreSubSidebarWidth(null)).toBe(240);
    expect(clampCoreSubSidebarWidth(160)).toBe(180);
    expect(clampCoreSubSidebarWidth(520)).toBe(480);
    expect(widthFromCoreSubSidebarPointer(64 + 360)).toBe(360);
  });

  it('serializes and restores collapsed and pinned state', () => {
    expect(serializeCoreSubSidebarCollapsed(true)).toBe('1');
    expect(serializeCoreSubSidebarCollapsed(false)).toBe('0');
    expect(restoreCoreSubSidebarCollapsed('1')).toBe(true);
    expect(restoreCoreSubSidebarCollapsed('0')).toBe(false);
    expect(restoreCoreSubSidebarCollapsed(null)).toBe(false);

    expect(serializeCoreSubSidebarPinned(true)).toBe('1');
    expect(serializeCoreSubSidebarPinned(false)).toBe('0');
    expect(restoreCoreSubSidebarPinned('1')).toBe(true);
    expect(restoreCoreSubSidebarPinned('0')).toBe(false);
    expect(restoreCoreSubSidebarPinned(null)).toBe(true);
  });

  it('scopes create-menu open state to the active app', () => {
    const state = { appId: 'research', open: true };

    expect(resolveCoreSubSidebarPreviewOpenAfterPinnedChange()).toBe(false);
    expect(isCoreSubSidebarCreateMenuOpen(state, 'research')).toBe(true);
    expect(isCoreSubSidebarCreateMenuOpen(state, 'docs')).toBe(false);
    expect(setCoreSubSidebarCreateMenuOpen(state, 'docs', true)).toEqual({
      appId: 'docs',
      open: true,
    });
    expect(
      setCoreSubSidebarCreateMenuOpen(
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
      calculateCoreSubSidebarCreateMenuPosition({
        sidebarRect: { left: 64, right: 304 },
        buttonRect: { right: 296, bottom: 80 },
      }),
    ).toEqual({
      left: 88,
      top: 84,
    });
  });
});
