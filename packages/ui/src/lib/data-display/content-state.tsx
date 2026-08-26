import { CircleAlert, CircleSlash2, Inbox, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';

import { Button } from '../primitives/button';
import { cn } from '../utils/cn';

export type ContentStateKind = 'loading' | 'empty' | 'error' | 'unavailable';

export interface ContentStateProps {
  kind: ContentStateKind;
  title: ReactNode;
  description?: ReactNode;
  action?: { label: ReactNode; onClick?: () => void };
  size?: 'compact' | 'default' | 'fill';
  className?: string;
}

function ContentStateIcon({ kind }: { kind: ContentStateKind }) {
  const props = { 'aria-hidden': true, size: 22, strokeWidth: 1.8 } as const;
  switch (kind) {
    case 'loading':
      return <Loader2 {...props} className="animate-spin" />;
    case 'error':
      return <CircleAlert {...props} />;
    case 'unavailable':
      return <CircleSlash2 {...props} />;
    default:
      return <Inbox {...props} />;
  }
}

export function ContentState({
  action,
  className,
  description,
  kind,
  size = 'default',
  title,
}: ContentStateProps) {
  const role =
    kind === 'error' ? 'alert' : kind === 'loading' ? 'status' : undefined;
  return (
    <div
      aria-busy={kind === 'loading' ? true : undefined}
      aria-live={kind === 'loading' ? 'polite' : undefined}
      className={cn(
        'grid place-items-center rounded-[var(--ui-radius-md)] border border-dashed border-[var(--ui-color-border-strong)] bg-ui-surface-subtle p-4 text-center',
        size === 'compact' && 'min-h-[120px]',
        size === 'default' && 'min-h-[180px]',
        size === 'fill' && 'h-full min-h-[120px]',
        kind === 'error' &&
          'border-[color-mix(in_oklab,var(--ui-color-danger)_45%,transparent)]',
        className,
      )}
      role={role}
    >
      <div className="grid max-w-[36ch] justify-items-center gap-1.5">
        <span
          className={cn(
            'mb-1 text-[var(--ui-color-ink-muted)]',
            kind === 'error' && 'text-[var(--ui-color-danger)]',
          )}
        >
          <ContentStateIcon kind={kind} />
        </span>
        <strong className="text-[length:var(--ui-text-h3)] text-[var(--ui-color-ink)]">
          {title}
        </strong>
        {description ? (
          <p className="m-0 text-[length:var(--ui-text-body-sm)] text-[var(--ui-color-ink-muted)]">
            {description}
          </p>
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
