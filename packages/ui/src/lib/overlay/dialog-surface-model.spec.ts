import { describe, expect, it } from 'vitest';

import {
  dialogAccessibilityProps,
  dialogContentLayerClass,
  dialogOverlayLayerClass,
  dialogSizeClasses,
  drawerModeClass,
  drawerSideClass,
  isFloatingLayerOutsideEvent,
  shouldBlockOutsideInteraction,
  shouldPreventOutsideInteraction,
} from './dialog-surface-model';

describe('dialog surface model', () => {
  it('projects accessibility props for dialogs without descriptions', () => {
    expect(dialogAccessibilityProps(true)).toEqual({});
    expect(dialogAccessibilityProps(false)).toEqual({
      'aria-describedby': undefined,
    });
  });

  it('projects dialog layer classes', () => {
    expect(dialogOverlayLayerClass('default')).toBe(
      'z-[calc(var(--ui-z-drawer)-1)]',
    );
    expect(dialogContentLayerClass('default')).toBe('z-[var(--ui-z-drawer)]');
    expect(dialogOverlayLayerClass('elevated')).toBe(
      'z-[calc(var(--ui-z-dialog-elevated)-1)]',
    );
    expect(dialogContentLayerClass('elevated')).toBe(
      'z-[var(--ui-z-dialog-elevated)]',
    );
  });

  it('projects dialog size classes without applying max width to full-size dialogs', () => {
    expect(dialogSizeClasses({ fullSize: true, maxWidth: 'max-w-lg' })).toBe(
      'h-[92vh] w-[96vw] max-w-[1600px]',
    );
    expect(
      dialogSizeClasses({ fullSize: false, maxWidth: 'max-w-3xl' }),
    ).toEqual(['w-[calc(100vw-2rem)] max-h-[85vh]', 'max-w-3xl']);
  });

  it('projects outside interaction blocking', () => {
    expect(shouldBlockOutsideInteraction(true)).toBe(false);
    expect(shouldBlockOutsideInteraction(false)).toBe(true);
  });

  it('keeps floating layers from dismissing dialogs', () => {
    const layer = document.createElement('div');
    const target = document.createElement('button');
    layer.setAttribute('data-ui-floating-layer', '');
    layer.append(target);
    document.body.append(layer);

    const event = new MouseEvent('mousedown', { bubbles: true });
    target.dispatchEvent(event);

    expect(isFloatingLayerOutsideEvent(event)).toBe(true);
    expect(shouldPreventOutsideInteraction(event, true)).toBe(true);

    layer.remove();
  });

  it('recognizes floating layer targets from Radix outside event details', () => {
    const layer = document.createElement('div');
    const target = document.createElement('button');
    layer.setAttribute('data-ui-floating-layer', '');
    layer.append(target);
    document.body.append(layer);

    const originalEvent = new MouseEvent('pointerdown', { bubbles: true });
    target.dispatchEvent(originalEvent);

    const outsideEvent = new CustomEvent('dismissableLayer.pointerDownOutside', {
      bubbles: false,
      cancelable: true,
      detail: { originalEvent },
    });
    document.body.dispatchEvent(outsideEvent);

    expect(isFloatingLayerOutsideEvent(outsideEvent)).toBe(true);
    expect(shouldPreventOutsideInteraction(outsideEvent, true)).toBe(true);

    layer.remove();
  });

  it('projects drawer side and mode classes', () => {
    expect(drawerSideClass('left')).toBe(
      'left-0 border-r border-r-[var(--ui-color-border)]',
    );
    expect(drawerSideClass('right')).toBe(
      'right-0 border-l border-l-[var(--ui-color-border)]',
    );
    expect(drawerModeClass(true)).toBe('overflow-hidden');
    expect(drawerModeClass(false)).toBe('gap-3 p-4');
  });
});
