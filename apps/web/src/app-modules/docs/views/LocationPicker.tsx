import { cn } from '@/src/lib/utils';
import type { LocationOption } from './docs-view-model';

interface LocationPickerProps {
  value: string;
  onChange: (value: string) => void;
  options: LocationOption[];
  busy?: boolean;
}

export function LocationPicker({
  value,
  onChange,
  options,
  busy,
}: LocationPickerProps) {
  return (
    <div className="space-y-1.5">
      {options.map((option) => {
        const Icon = option.icon;
        const isSelected = value === option.value;
        const isDisabled = busy || option.disabled;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => !isDisabled && onChange(option.value)}
            disabled={isDisabled}
            title={option.disabled ? option.disabledReason : undefined}
            className={cn(
              'flex w-full items-center gap-3 rounded-md border px-3 py-2.5 text-left transition-colors',
              isSelected
                ? 'border-app-accent bg-app-accent/10 ring-1 ring-app-accent'
                : 'border-app-border bg-app-bg hover:border-app-accent/50 hover:bg-app-surface-hover',
              isDisabled &&
                'cursor-not-allowed opacity-50 hover:border-app-border hover:bg-app-bg',
            )}
          >
            <span
              className={cn(
                'flex size-8 shrink-0 items-center justify-center rounded-full',
                isSelected
                  ? 'bg-app-accent text-app-accent-fg'
                  : 'bg-app-surface-hover text-app-ink/55',
              )}
            >
              <Icon size={15} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="app-text-control block truncate text-app-ink">
                {option.title}
              </span>
              <span className="app-text-micro block truncate text-app-ink/55">
                {option.desc}
              </span>
            </span>
            {isSelected ? (
              <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-app-accent">
                <span className="block size-1.5 rounded-full bg-app-accent-fg" />
              </span>
            ) : (
              <span className="block size-4 shrink-0 rounded-full border border-app-border" />
            )}
          </button>
        );
      })}
    </div>
  );
}
