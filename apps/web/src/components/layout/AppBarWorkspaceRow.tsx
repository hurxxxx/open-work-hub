import { Check } from 'lucide-react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { cn } from '@/src/lib/utils';
import { getInitials } from './app-bar-model';

export function AppBarWorkspaceRow({
  defaultBadgeLabel,
  isDefault = false,
  isCurrent = false,
  onClick,
  workspace,
}: {
  defaultBadgeLabel: string;
  isDefault?: boolean;
  isCurrent?: boolean;
  onClick: () => void;
  workspace: AuthUser['workspaces'][number];
}) {
  return (
    <button
      aria-current={isCurrent ? 'true' : undefined}
      className={cn(
        'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-app-accent/25',
        isCurrent && 'bg-app-bg',
      )}
      onClick={onClick}
      type="button"
    >
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-bg text-app-ink">
        <span className="app-text-body-sm font-semibold">
          {getInitials(workspace.name, 'WS')}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="app-text-body-sm truncate text-app-ink">
            {workspace.name}
          </span>
          {isDefault ? (
            <span className="app-text-micro shrink-0 rounded-full border border-app-border px-1.5 py-0.5 text-app-ink/55">
              {defaultBadgeLabel}
            </span>
          ) : null}
        </div>
        <div className="app-text-caption mt-0.5 truncate text-app-ink/55">
          {workspace.slug}
        </div>
      </div>

      {isCurrent ? (
        <Check size={15} className="shrink-0 text-app-accent" />
      ) : null}
    </button>
  );
}
