import { cn } from '../utils/cn';

export interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-[var(--ui-radius-md)] bg-ui-surface-subtle',
        className,
      )}
    />
  );
}
