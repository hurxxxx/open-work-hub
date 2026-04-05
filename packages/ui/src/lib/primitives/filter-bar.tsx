import { cn } from '../utils/cn';
import type { FilterOption } from '../types';
import { Button } from './button';

export interface FilterBarProps {
  options: FilterOption[];
  className?: string;
}

export function FilterBar({ options, className }: FilterBarProps) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {options.map((option) => (
        <Button
          key={option.id}
          variant={option.active ? 'subtle' : 'secondary'}
          size="dense"
          onClick={option.onSelect}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}
