import type * as React from 'react';
import { useEffect, useRef } from 'react';

function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}

export function useFloatingAnchorPosition(
  open: boolean,
  anchorRef: React.RefObject<HTMLElement | null>,
) {
  const rect = open ? anchorRef.current?.getBoundingClientRect() : null;
  return {
    left: rect ? rect.right + 4 : 0,
    top: rect ? rect.top : 0,
  };
}

export function useDismissOnOutside(
  open: boolean,
  ref: React.RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  const onCloseRef = useLatestRef(onClose);
  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onCloseRef.current();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, ref, onCloseRef]);
}
