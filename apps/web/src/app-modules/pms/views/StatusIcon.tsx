import type { ComponentType } from 'react';
import {
  CheckCircle2,
  Circle,
  CircleDot,
  CircleSlash,
  XCircle,
} from 'lucide-react';
import { Tooltip } from '@open-alm/ui';
import { cn } from '@/src/lib/utils';
import type { PmsTaskListStatus } from '../api/pms-api';

type StatusVisual = {
  Icon: ComponentType<{
    size?: number;
    className?: string;
    style?: React.CSSProperties;
  }>;
  className: string;
  style?: React.CSSProperties;
};

function getStatusVisual(
  slug: string,
  _label: string,
  taskListStatuses?: PmsTaskListStatus[],
): StatusVisual {
  const status = taskListStatuses?.find((item) => item.slug === slug);
  const category =
    status?.category ??
    (slug === 'todo'
      ? 'not_started'
      : slug === 'done'
        ? 'done'
        : slug === 'canceled' || slug === 'complete'
          ? 'closed'
          : 'active');
  const color = status?.color;
  const customStyle = color
    ? {
        backgroundColor: `${color}1A`,
        borderColor: `${color}66`,
        color,
      }
    : undefined;

  if (category === 'not_started') {
    return {
      Icon: Circle,
      className: color
        ? 'border-current'
        : 'border-app-border bg-app-ink/10 text-app-ink/55',
      style: customStyle,
    };
  }
  if (category === 'active') {
    return {
      Icon: CircleDot,
      className: color
        ? 'border-current'
        : 'border-blue-300 bg-app-info/10 text-blue-500',
      style: customStyle,
    };
  }
  if (category === 'done') {
    return {
      Icon: CheckCircle2,
      className: color
        ? 'border-current'
        : 'border-app-success/30 bg-app-success/10 text-app-success',
      style: customStyle,
    };
  }
  if (category === 'closed') {
    return {
      Icon: CircleSlash,
      className: color
        ? 'border-current'
        : 'border-app-success/30 bg-app-success/10 text-app-success',
      style: customStyle,
    };
  }

  if (slug === 'todo') {
    return {
      Icon: Circle,
      className: 'border-app-border bg-app-ink/10 text-app-ink/55',
    };
  }
  if (slug === 'in_progress') {
    return {
      Icon: CircleDot,
      className: 'border-blue-300 bg-app-info/10 text-blue-500',
    };
  }
  if (slug === 'done') {
    return {
      Icon: CheckCircle2,
      className: 'border-app-success/30 bg-app-success/10 text-app-success',
    };
  }
  if (slug === 'canceled') {
    return {
      Icon: XCircle,
      className: 'border-app-danger-border bg-app-danger/10 text-app-danger',
    };
  }
  return {
    Icon: CircleDot,
    className: 'border-app-border-strong bg-app-ink/10 text-app-ink/70',
  };
}

export function StatusIconGlyph({
  className,
  label,
  size = 16,
  status,
  taskListStatuses,
}: {
  className?: string;
  label: string;
  size?: number;
  status: string;
  taskListStatuses?: PmsTaskListStatus[];
}) {
  const visual = getStatusVisual(status, label, taskListStatuses);
  const Icon = visual.Icon;
  return (
    <Icon
      size={size}
      className={cn('shrink-0', className)}
      style={visual.style}
    />
  );
}

export function StatusIconButton({
  className,
  label,
  onClick,
  status,
  taskListStatuses,
}: {
  className?: string;
  label: string;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  status: string;
  taskListStatuses?: PmsTaskListStatus[];
}) {
  const visual = getStatusVisual(status, label, taskListStatuses);
  const Icon = visual.Icon;
  const content = (
    <button
      aria-label={label}
      className={cn(
        'inline-flex h-7 w-7 items-center justify-center rounded-md border transition-colors hover:bg-app-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/40',
        visual.className,
        className,
      )}
      onClick={onClick}
      style={visual.style}
      type="button"
    >
      <Icon size={17} />
    </button>
  );

  return <Tooltip content={label}>{content}</Tooltip>;
}
