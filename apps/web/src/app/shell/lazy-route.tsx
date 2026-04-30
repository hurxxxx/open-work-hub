import { Suspense, type ReactElement } from 'react';

export function lazyRoute(element: ReactElement): ReactElement {
  return (
    <Suspense
      fallback={(
        <div
          aria-label="Loading"
          role="status"
          className="flex h-full min-h-32 items-center justify-center text-app-ink/40"
        />
      )}
    >
      {element}
    </Suspense>
  );
}
