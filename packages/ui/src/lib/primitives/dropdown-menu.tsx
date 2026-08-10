import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu';
import { Fragment, type ComponentProps, type ReactNode } from 'react';

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
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  align?: ComponentProps<typeof DropdownMenuPrimitive.Content>['align'];
  side?: ComponentProps<typeof DropdownMenuPrimitive.Content>['side'];
  sideOffset?: number;
  collisionPadding?: ComponentProps<typeof DropdownMenuPrimitive.Content>['collisionPadding'];
  contentClassName?: string;
}

export function DropdownMenu({
  trigger,
  items,
  open,
  onOpenChange,
  align = 'end',
  side = 'right',
  sideOffset = 10,
  collisionPadding = 12,
  contentClassName,
}: DropdownMenuProps) {
  return (
    <DropdownMenuPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align={align}
          collisionPadding={collisionPadding}
          side={side}
          sideOffset={sideOffset}
          className={cn(
            'z-[9999] min-w-[240px] max-w-[280px] rounded-xl border border-[var(--ui-color-border)] bg-ui-surface-raised p-1.5 shadow-xl text-[var(--ui-color-ink)]',
            contentClassName,
          )}
        >
          {items.map((item) => (
            <Fragment key={item.id}>
              {item.separatorBefore ? (
                <DropdownMenuPrimitive.Separator className="my-1.5 h-px bg-ui-border" />
              ) : null}
              <DropdownMenuPrimitive.Item
                disabled={item.disabled}
                onSelect={item.onSelect}
                className={cn(
                  'ui-primitive-menu-item flex min-h-[34px] items-center rounded-lg px-3 py-2 text-[length:var(--ui-text-caption)] text-left outline-none data-[highlighted]:bg-ui-surface-subtle data-[highlighted]:text-[var(--ui-color-accent)] data-[disabled]:cursor-default data-[disabled]:opacity-100 transition-colors',
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
