import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import type { ReactNode } from 'react';

export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
}

export function Tooltip({ content, children }: TooltipProps) {
  return (
    <TooltipPrimitive.Provider delayDuration={150}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            className="z-[var(--ui-z-toast)] max-w-[min(22rem,calc(100vw-2rem))] rounded-[var(--ui-radius-sm)] border border-white/10 bg-[var(--ui-color-bg-strong)] px-2.5 py-1.5 text-[length:var(--ui-text-caption)] leading-snug text-white shadow-[var(--ui-shadow-lg)]"
            sideOffset={6}
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
