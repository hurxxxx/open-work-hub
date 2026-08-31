import * as SelectPrimitive from '@radix-ui/react-select';

import { cn } from '../utils/cn';

export type SelectOption = {
  value: string;
  label: string;
};

export interface SelectProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  ariaLabel?: string;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function Select({
  value,
  onValueChange,
  options,
  ariaLabel,
  placeholder,
  className,
  disabled,
}: SelectProps) {
  return (
    <SelectPrimitive.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        disabled={disabled}
        className={cn(
          'ui-primitive-control-normal inline-flex h-[var(--ui-density-dense)] min-w-[148px] items-center justify-between gap-2 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-raised px-2 text-[length:var(--ui-text-caption)] text-[var(--ui-color-ink)] outline-none transition-colors',
          'focus:border-[var(--ui-color-accent)] focus:ring-2 focus:ring-[var(--ui-color-accent-weak)]',
          'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-60',
          className,
        )}
      >
        <span className="min-w-0 flex-1 truncate text-left">
          <SelectPrimitive.Value placeholder={placeholder} />
        </span>
        <SelectPrimitive.Icon className="shrink-0">
          <span aria-hidden="true">▾</span>
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="z-[var(--ui-z-popover)] max-h-[min(320px,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-raised shadow-[var(--ui-shadow-lg)]"
          position="popper"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="ui-primitive-menu-item relative flex min-h-[var(--ui-density-dense)] cursor-pointer select-none items-center rounded-[calc(var(--ui-radius-sm)-1px)] px-2 text-[length:var(--ui-text-caption)] text-[var(--ui-color-ink)] outline-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50 data-[highlighted]:bg-ui-accent-weak"
              >
                <SelectPrimitive.ItemText>
                  {option.label}
                </SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
