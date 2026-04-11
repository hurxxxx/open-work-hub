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
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function Select({
  value,
  onValueChange,
  options,
  placeholder,
  className,
  disabled,
}: SelectProps) {
  return (
      <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectPrimitive.Trigger
        disabled={disabled}
        className={cn(
          'inline-flex h-[var(--ui-density-dense)] min-w-[148px] items-center justify-between gap-2 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-raised px-3 text-[0.84rem] text-[var(--ui-color-ink)]',
          'data-[disabled]:cursor-not-allowed data-[disabled]:opacity-60',
          className,
        )}
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <span aria-hidden="true">▾</span>
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="z-[var(--ui-z-popover)] overflow-hidden rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-raised shadow-[var(--ui-shadow-lg)]"
          position="popper"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="relative flex min-h-[30px] cursor-pointer select-none items-center rounded-[calc(var(--ui-radius-sm)-1px)] px-3 text-[0.84rem] text-[var(--ui-color-ink)] outline-none data-[highlighted]:bg-ui-accent-weak"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
