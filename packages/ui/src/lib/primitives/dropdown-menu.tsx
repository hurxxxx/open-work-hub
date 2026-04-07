import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import { Fragment, type ReactNode } from 'react';

import { cn } from '../utils/cn';

export interface DropdownItem {
  id: string;
  label: ReactNode;
  onSelect?: () => void;
  disabled?: boolean;
  separatorBefore?: boolean;
  tone?: 'default' | 'danger';
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
        <DropdownMenuPrimitive.Content
          align="end"
          collisionPadding={12}
          side="right"
          sideOffset={10}
          className="z-[9999] min-w-[240px] max-w-[280px] rounded-xl border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] p-1.5 shadow-xl text-[var(--ui-color-ink)]"
        >
          {items.map((item) => (
            <Fragment key={item.id}>
              {item.separatorBefore ? (
                <DropdownMenuPrimitive.Separator className="my-1.5 h-px bg-[var(--ui-color-border)]" />
              ) : null}
              <DropdownMenuPrimitive.Item
                disabled={item.disabled}
                onSelect={item.onSelect}
                className={cn(
                  'flex min-h-[36px] items-center rounded-lg px-3 py-2 text-sm text-left outline-none data-[highlighted]:bg-[var(--ui-color-surface-subtle)] data-[highlighted]:text-[var(--ui-color-accent)] data-[disabled]:cursor-default data-[disabled]:opacity-100 transition-colors',
                  item.disabled
                    ? 'text-[var(--ui-color-ink-subtle)]'
                    : 'cursor-pointer text-[var(--ui-color-ink)]',
                  item.tone === 'danger' ? 'text-[var(--ui-color-danger)] data-[highlighted]:text-[var(--ui-color-danger)] data-[highlighted]:bg-[color-mix(in_oklab,var(--ui-color-danger)_8%,white)]' : null,
                )}
              >
                <div className="w-full whitespace-normal leading-5">{item.label}</div>
              </DropdownMenuPrimitive.Item>
            </Fragment>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
