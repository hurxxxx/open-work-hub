import type { CoreSetStateAction } from './mobile-shell-menu.js';

export const CORE_SUB_SIDEBAR_MIN_WIDTH = 180;
export const CORE_SUB_SIDEBAR_MAX_WIDTH = 480;
export const CORE_SUB_SIDEBAR_DEFAULT_WIDTH = 240;
export const CORE_SUB_SIDEBAR_CREATE_MENU_WIDTH = 208;
export const CORE_SUB_SIDEBAR_CREATE_MENU_INSET = 8;
export const CORE_SUB_SIDEBAR_CREATE_MENU_GAP = 4;
export const CORE_SUB_SIDEBAR_MAIN_NAV_WIDTH = 64;
export const CORE_SUB_SIDEBAR_PINNED_STORAGE_KEY = 'open-work-hub:sub-sidebar-pinned';

export interface CoreSubSidebarCreateMenuState {
  appId: string;
  open: boolean;
}

export interface CoreSubSidebarRect {
  left: number;
  right: number;
  bottom?: number;
}

export interface CoreSubSidebarCreateMenuPosition {
  left: number;
  top: number;
}

export function restoreCoreSubSidebarWidth(rawValue: string | null): number {
  const parsed = rawValue ? parseInt(rawValue, 10) : NaN;
  if (
    Number.isFinite(parsed) &&
    parsed >= CORE_SUB_SIDEBAR_MIN_WIDTH &&
    parsed <= CORE_SUB_SIDEBAR_MAX_WIDTH
  ) {
    return parsed;
  }
  return CORE_SUB_SIDEBAR_DEFAULT_WIDTH;
}

export function clampCoreSubSidebarWidth(width: number): number {
  return Math.min(
    CORE_SUB_SIDEBAR_MAX_WIDTH,
    Math.max(CORE_SUB_SIDEBAR_MIN_WIDTH, width),
  );
}

export function widthFromCoreSubSidebarPointer(clientX: number): number {
  return clampCoreSubSidebarWidth(clientX - CORE_SUB_SIDEBAR_MAIN_NAV_WIDTH);
}

export function restoreCoreSubSidebarCollapsed(
  rawValue: string | null,
): boolean {
  return rawValue === '1';
}

export function serializeCoreSubSidebarCollapsed(isCollapsed: boolean): string {
  return isCollapsed ? '1' : '0';
}

export function restoreCoreSubSidebarPinned(rawValue: string | null): boolean {
  return rawValue !== '0';
}

export function serializeCoreSubSidebarPinned(isPinned: boolean): string {
  return isPinned ? '1' : '0';
}

export function resolveCoreSubSidebarPreviewOpenAfterPinnedChange(): boolean {
  return false;
}

export function isCoreSubSidebarCreateMenuOpen(
  state: CoreSubSidebarCreateMenuState,
  activeAppId: string,
): boolean {
  return state.appId === activeAppId && state.open;
}

export function setCoreSubSidebarCreateMenuOpen(
  state: CoreSubSidebarCreateMenuState,
  activeAppId: string,
  nextOpen: CoreSetStateAction<boolean>,
): CoreSubSidebarCreateMenuState {
  const currentOpen = isCoreSubSidebarCreateMenuOpen(state, activeAppId);
  return {
    appId: activeAppId,
    open: typeof nextOpen === 'function' ? nextOpen(currentOpen) : nextOpen,
  };
}

export function calculateCoreSubSidebarCreateMenuPosition({
  sidebarRect,
  buttonRect,
  menuWidth = CORE_SUB_SIDEBAR_CREATE_MENU_WIDTH,
  inset = CORE_SUB_SIDEBAR_CREATE_MENU_INSET,
  gap = CORE_SUB_SIDEBAR_CREATE_MENU_GAP,
}: {
  sidebarRect: Required<Pick<CoreSubSidebarRect, 'left' | 'right'>>;
  buttonRect: Required<Pick<CoreSubSidebarRect, 'right' | 'bottom'>>;
  menuWidth?: number;
  inset?: number;
  gap?: number;
}): CoreSubSidebarCreateMenuPosition {
  return {
    left: Math.max(
      sidebarRect.left + inset,
      Math.min(
        buttonRect.right - menuWidth,
        sidebarRect.right - menuWidth - inset,
      ),
    ),
    top: buttonRect.bottom + gap,
  };
}
