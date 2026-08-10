import * as TabsPrimitive from '@radix-ui/react-tabs';
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  Ref,
} from 'react';

import { cn } from '../utils/cn';

export type TabsContentProps = ComponentPropsWithoutRef<typeof TabsPrimitive.Content> & {
  ref?: Ref<ElementRef<typeof TabsPrimitive.Content>>;
};

export function TabsContent({ className, ref, ...props }: TabsContentProps) {
  return (
    <TabsPrimitive.Content
      ref={ref}
      className={cn('mt-3', className)}
      {...props}
    />
  );
}
