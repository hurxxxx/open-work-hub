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
          className="z-[9999] min-w-[240px] max-w-[280px] rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1e1f21] p-1.5 shadow-xl text-clickup-text"
        >
          {items.map((item) => (
            <Fragment key={item.id}>
              {item.separatorBefore ? (
                <DropdownMenuPrimitive.Separator className="my-1.5 h-px bg-gray-200 dark:bg-gray-700" />
              ) : null}
              <DropdownMenuPrimitive.Item
                disabled={item.disabled}
                onSelect={item.onSelect}
                className={cn(
                  'flex min-h-[36px] items-center rounded-lg px-3 py-2 text-sm text-left outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800 data-[highlighted]:text-[#7b68ee] data-[disabled]:cursor-default data-[disabled]:opacity-100 transition-colors',
                  item.disabled
                    ? 'text-gray-400 dark:text-gray-500'
                    : 'cursor-pointer text-gray-900 dark:text-gray-200',
                  item.tone === 'danger' ? 'text-red-600 dark:text-red-500 data-[highlighted]:text-red-700 data-[highlighted]:bg-red-50 dark:data-[highlighted]:bg-red-500/10' : null,
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
