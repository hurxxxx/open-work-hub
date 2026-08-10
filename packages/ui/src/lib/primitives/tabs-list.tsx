import * as TabsPrimitive from '@radix-ui/react-tabs';
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  Ref,
} from 'react';

import { cn } from '../utils/cn';

export type TabsListProps = ComponentPropsWithoutRef<typeof TabsPrimitive.List> & {
  ref?: Ref<ElementRef<typeof TabsPrimitive.List>>;
};

export function TabsList({ className, ref, ...props }: TabsListProps) {
  return (
    <TabsPrimitive.List
      ref={ref}
      className={cn(
        'inline-flex flex-wrap items-center gap-1 rounded-[calc(var(--ui-radius-md)-2px)] border border-[var(--ui-color-border)] bg-ui-surface-subtle p-1',
        className,
      )}
      {...props}
    />
  );
}
