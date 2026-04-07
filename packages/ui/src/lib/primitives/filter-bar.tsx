import { cn } from '../utils/cn';
import type { FilterOption } from '../types';
import { Button } from './button';

export interface FilterBarProps {
  options: FilterOption[];
  className?: string;
}

export function FilterBar({ options, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1.5 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-subtle p-1',
        className,
      )}
    >
      {options.map((option) => (
        <Button
          key={option.id}
          variant={option.active ? 'subtle' : 'ghost'}
          size="dense"
          onClick={option.onSelect}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
