import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import type { ReactNode } from 'react';

export interface DropdownItem {
  id: string;
  label: string;
  onSelect?: () => void;
}

export interface DropdownMenuProps {
  trigger: ReactNode;
  items: DropdownItem[];
}

export function DropdownMenu({ trigger, items }: DropdownMenuProps) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content className="z-[var(--ui-z-drawer)] min-w-[180px] rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] p-1 shadow-[var(--ui-shadow-lg)]">
          {items.map((item) => (
            <DropdownMenuPrimitive.Item
              key={item.id}
              onSelect={item.onSelect}
              className="flex min-h-[32px] cursor-pointer items-center rounded-[calc(var(--ui-radius-md)-2px)] px-3 text-sm text-[var(--ui-color-ink)] outline-none data-[highlighted]:bg-[var(--ui-color-accent-weak)]"
            >
              {item.label}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
