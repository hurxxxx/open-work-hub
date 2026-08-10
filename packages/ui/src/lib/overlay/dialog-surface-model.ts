type DialogLayer = 'default' | 'elevated';
type DrawerSide = 'left' | 'right';

export function dialogAccessibilityProps(hasDescription: boolean): {
  'aria-describedby'?: undefined;
} {
  return hasDescription ? {} : { 'aria-describedby': undefined };
}

export function dialogOverlayLayerClass(layer: DialogLayer): string {
  return layer === 'elevated'
    ? 'z-[calc(var(--ui-z-dialog-elevated)-1)]'
    : 'z-[calc(var(--ui-z-drawer)-1)]';
}

export function dialogContentLayerClass(layer: DialogLayer): string {
  return layer === 'elevated'
    ? 'z-[var(--ui-z-dialog-elevated)]'
    : 'z-[var(--ui-z-drawer)]';
}

export function dialogSizeClasses({
  fullSize,
  maxWidth,
}: {
  fullSize: boolean;
  maxWidth: string;
}): string | string[] {
  return fullSize
    ? 'h-[92vh] w-[96vw] max-w-[1600px]'
    : ['w-[calc(100vw-2rem)] max-h-[85vh]', maxWidth];
}

export function shouldBlockOutsideInteraction(
  dismissOnInteractOutside: boolean,
): boolean {
  return !dismissOnInteractOutside;
}

type OutsideInteractionEventDetail = {
  originalEvent?: Event;
};

const FLOATING_LAYER_SELECTOR = '[data-ui-floating-layer]';

function isFloatingLayerTarget(target: unknown): boolean {
  return (
    target instanceof Element &&
    target.closest(FLOATING_LAYER_SELECTOR) !== null
  );
}

function collectOutsideInteractionTargets(event: Event): unknown[] {
  const originalEvent = (
    event as CustomEvent<OutsideInteractionEventDetail>
  ).detail?.originalEvent;
  return [
    event.target,
    ...(typeof event.composedPath === 'function' ? event.composedPath() : []),
    originalEvent?.target,
    ...(typeof originalEvent?.composedPath === 'function'
      ? originalEvent.composedPath()
      : []),
  ];
}

export function isFloatingLayerOutsideEvent(event: Event): boolean {
  return collectOutsideInteractionTargets(event).some(isFloatingLayerTarget);
}

export function shouldPreventOutsideInteraction(
  event: Event,
  dismissOnInteractOutside: boolean,
): boolean {
  return (
    shouldBlockOutsideInteraction(dismissOnInteractOutside) ||
    isFloatingLayerOutsideEvent(event)
  );
}

export function drawerSideClass(side: DrawerSide): string {
  return side === 'left'
    ? 'left-0 border-r border-r-[var(--ui-color-border)]'
    : 'right-0 border-l border-l-[var(--ui-color-border)]';
}

export function drawerModeClass(embedded: boolean): string {
  return embedded ? 'overflow-hidden' : 'gap-3 p-4';
}
