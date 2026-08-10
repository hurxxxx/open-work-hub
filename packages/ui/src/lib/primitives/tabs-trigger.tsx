import * as TabsPrimitive from '@radix-ui/react-tabs';
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  Ref,
} from 'react';

import { cn } from '../utils/cn';

export type TabsTriggerProps = ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger> & {
  ref?: Ref<ElementRef<typeof TabsPrimitive.Trigger>>;
};

export function TabsTrigger({ className, ref, ...props }: TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      ref={ref}
      className={cn(
        'ui-primitive-control inline-flex h-[calc(var(--ui-density-dense)-2px)] items-center rounded-[calc(var(--ui-radius-md)-3px)] border border-transparent bg-transparent px-3 text-[length:var(--ui-text-caption)] font-semibold leading-none text-[var(--ui-color-ink-muted)] transition-colors duration-[var(--ui-motion-fast)] hover:text-[var(--ui-color-ink)] data-[state=active]:border-[var(--ui-color-accent)] data-[state=active]:bg-[color-mix(in_oklab,var(--ui-color-accent)_12%,transparent)] data-[state=active]:text-[var(--ui-color-accent)]',
        className,
      )}
      {...props}
    />
  );
}
