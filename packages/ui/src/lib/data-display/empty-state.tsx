import type { ReactNode } from 'react';

import { Button } from '../primitives/button';

export interface EmptyStateProps {
  title: ReactNode;
  description?: ReactNode;
  action?: {
    label: string;
    onClick?: () => void;
  };
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="grid min-h-[120px] place-items-center rounded-[var(--ui-radius-md)] border border-dashed border-[var(--ui-color-border-strong)] bg-[var(--ui-color-surface-subtle)] p-4 text-center">
      <div className="grid max-w-[30ch] gap-1.5">
        <strong className="text-[0.98rem] text-[var(--ui-color-ink)]">{title}</strong>
        {description ? (
          <p className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">{description}</p>
        ) : null}
        {action ? (
          <div className="pt-1.5">
            <Button onClick={action.onClick}>{action.label}</Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
