import { m } from 'motion/react';
import type { ReactNode } from 'react';

import { cn } from '@/src/lib/utils';

type TaskDetailModalProps = {
  children: ReactNode;
  className?: string;
  closeLabel: string;
  onClose: () => void;
};

export function TaskDetailModal({
  children,
  className,
  closeLabel,
  onClose,
}: TaskDetailModalProps) {
  return (
    <m.div
      key="task-detail-modal"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className={cn('fixed inset-0 z-50 flex items-stretch', className)}
    >
      <button
        type="button"
        aria-label={closeLabel}
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <m.div
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 30, opacity: 0 }}
        transition={{ type: 'spring', damping: 28, stiffness: 350 }}
        className="relative z-10 flex h-full w-full flex-col overflow-hidden border-app-border bg-app-bg shadow-2xl lg:my-6 lg:mx-auto lg:h-auto lg:w-[80%] lg:rounded-xl lg:border"
      >
        {children}
      </m.div>
    </m.div>
  );
}
