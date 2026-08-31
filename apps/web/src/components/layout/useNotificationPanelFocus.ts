import { useCallback, useEffect, useRef, type MouseEventHandler } from 'react';

export const NOTIFICATION_PANEL_ID = 'open-work-hub-notification-panel';

export function useNotificationPanelFocus(open: boolean, toggle: () => void) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const shouldRestoreFocusRef = useRef(false);

  const onToggle = useCallback<MouseEventHandler<HTMLButtonElement>>(
    (event) => {
      if (!open) {
        triggerRef.current = event.currentTarget;
      } else {
        shouldRestoreFocusRef.current = true;
      }
      toggle();
    },
    [open, toggle],
  );

  const onClose = useCallback(() => {
    if (!open) return;
    shouldRestoreFocusRef.current = true;
    toggle();
  }, [open, toggle]);

  useEffect(() => {
    if (open) {
      document.getElementById(NOTIFICATION_PANEL_ID)?.focus();
      return;
    }
    if (!shouldRestoreFocusRef.current) return;
    shouldRestoreFocusRef.current = false;
    const trigger = triggerRef.current;
    if (trigger?.isConnected) {
      trigger.focus();
    }
  }, [open]);

  return { onClose, onToggle };
}
