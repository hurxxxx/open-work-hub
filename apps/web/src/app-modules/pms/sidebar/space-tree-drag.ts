import type * as React from 'react';
import { useCallback, useEffect, useRef } from 'react';

export function useSuppressClickAfterDrag(isDragging: boolean) {
  const justDraggedRef = useRef(false);
  useEffect(() => {
    if (isDragging) {
      justDraggedRef.current = true;
      return;
    }
    if (!justDraggedRef.current) return;
    const timer = setTimeout(() => {
      justDraggedRef.current = false;
    }, 150);
    return () => clearTimeout(timer);
  }, [isDragging]);
  return useCallback((event: React.MouseEvent) => {
    if (justDraggedRef.current) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, []);
}
