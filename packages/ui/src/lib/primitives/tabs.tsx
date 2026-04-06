import * as TabsPrimitive from '@radix-ui/react-tabs';
import type { ComponentPropsWithoutRef, ElementRef } from 'react';
import { forwardRef } from 'react';

import { cn } from '../utils/cn';

export const Tabs = TabsPrimitive.Root;

export const TabsList = forwardRef<
  ElementRef<typeof TabsPrimitive.List>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      'inline-flex flex-wrap items-center gap-1 rounded-[calc(var(--ui-radius-md)-2px)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-subtle)] p-1',
      className,
    )}
    {...props}
  />
));

TabsList.displayName = TabsPrimitive.List.displayName;

export const TabsTrigger = forwardRef<
  ElementRef<typeof TabsPrimitive.Trigger>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'inline-flex h-[calc(var(--ui-density-dense)-2px)] items-center rounded-[calc(var(--ui-radius-md)-3px)] border border-transparent bg-transparent px-3 text-[0.82rem] font-semibold leading-none text-[var(--ui-color-ink-muted)] transition-colors duration-[var(--ui-motion-fast)] data-[state=active]:border-[var(--ui-color-border)] data-[state=active]:bg-white data-[state=active]:text-[var(--ui-color-ink)]',
      className,
    )}
    {...props}
  />
));

TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

export const TabsContent = forwardRef<
  ElementRef<typeof TabsPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn('mt-3', className)} {...props} />
));

TabsContent.displayName = TabsPrimitive.Content.displayName;
