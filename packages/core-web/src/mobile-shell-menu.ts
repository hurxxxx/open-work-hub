export type CoreSetStateAction<T> = T | ((value: T) => T);

export type CoreMobileShellMenuState = {
  appMenuOpen: boolean;
  navOpen: boolean;
  routeKey: string;
};

export function createCoreMobileShellRouteKey(
  pathname: string,
  search: string,
) {
  return `${pathname}\u0000${search}`;
}

export function createClosedCoreMobileShellMenuState(
  routeKey: string,
): CoreMobileShellMenuState {
  return {
    appMenuOpen: false,
    navOpen: false,
    routeKey,
  };
}

function resolveNextStateValue<T>(
  nextValue: CoreSetStateAction<T>,
  currentValue: T,
): T {
  return typeof nextValue === 'function'
    ? (nextValue as (value: T) => T)(currentValue)
    : nextValue;
}

export function resolveActiveCoreMobileShellMenuState(
  current: CoreMobileShellMenuState,
  routeKey: string,
): CoreMobileShellMenuState {
  return current.routeKey === routeKey
    ? current
    : createClosedCoreMobileShellMenuState(routeKey);
}

export function applyCoreMobileNavOpenChange(
  current: CoreMobileShellMenuState,
  routeKey: string,
  nextOpen: CoreSetStateAction<boolean>,
): CoreMobileShellMenuState {
  const activeState = resolveActiveCoreMobileShellMenuState(current, routeKey);
  return {
    ...activeState,
    navOpen: resolveNextStateValue(nextOpen, activeState.navOpen),
  };
}

export function applyCoreMobileAppMenuOpenChange(
  current: CoreMobileShellMenuState,
  routeKey: string,
  nextOpen: CoreSetStateAction<boolean>,
): CoreMobileShellMenuState {
  const activeState = resolveActiveCoreMobileShellMenuState(current, routeKey);
  return {
    ...activeState,
    appMenuOpen: resolveNextStateValue(nextOpen, activeState.appMenuOpen),
  };
}
