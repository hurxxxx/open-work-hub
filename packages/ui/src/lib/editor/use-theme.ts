import { useSyncExternalStore } from 'react';

function getIsDark() {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
}

function subscribe(cb: () => void) {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  return () => observer.disconnect();
}

/** Returns 'dark' or 'light' based on the <html> class. */
export function useResolvedTheme(): 'dark' | 'light' {
  const isDark = useSyncExternalStore(subscribe, getIsDark, () => true);
  return isDark ? 'dark' : 'light';
}
