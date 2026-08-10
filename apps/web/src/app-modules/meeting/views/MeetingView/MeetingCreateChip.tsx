import type { ReactNode } from 'react';
import { Plus, X } from 'lucide-react';

type MeetingCreateChipProps = {
  children: ReactNode;
  icon?: ReactNode;
  meta?: ReactNode;
  onRemove?: () => void;
  removeLabel?: string;
  lockedLabel?: string;
};

export function MeetingCreateChip({
  children,
  icon,
  lockedLabel,
  meta,
  onRemove,
  removeLabel,
}: MeetingCreateChipProps) {
  return (
    <span className="app-text-caption inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink">
      {icon}
      <span className="max-w-[14rem] truncate">{children}</span>
      {meta ? <span className="text-app-ink/40">{meta}</span> : null}
      {lockedLabel ? (
        <span className="text-app-ink/40">· {lockedLabel}</span>
      ) : onRemove && removeLabel ? (
        <button
          type="button"
          onClick={onRemove}
          className="text-app-ink/40 hover:text-app-ink"
          aria-label={removeLabel}
        >
          <X size={12} />
        </button>
      ) : null}
    </span>
  );
}

type MeetingCreateActionButtonProps = {
  children: ReactNode;
  icon: ReactNode;
  onClick: () => void;
};

export function MeetingCreateActionButton({
  children,
  icon,
  onClick,
}: MeetingCreateActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-1.5 text-app-ink hover:bg-app-surface-hover"
    >
      <Plus size={12} />
      {icon}
      {children}
    </button>
  );
}
