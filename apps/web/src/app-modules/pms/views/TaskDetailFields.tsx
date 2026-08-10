import type { ReactNode } from 'react';

export function MetaLabel({ children }: { children: ReactNode }) {
  return (
    <span className="app-text-overline whitespace-nowrap text-app-ink/50">
      {children}
    </span>
  );
}

export { InlineSaveError } from './InlineSaveError';
export { UserRolePicker } from './UserRolePicker';
