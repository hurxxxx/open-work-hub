import { FileCode2, FileText } from 'lucide-react';

import { cn } from '@/src/lib/utils';
import type { DocsContentFormat, DocsHubContentFormat } from '../api/docs-api';

export function DocsContentFormatBadge({
  format,
  label,
  compact = false,
}: {
  format: DocsContentFormat | DocsHubContentFormat;
  label: string;
  compact?: boolean;
}) {
  const Icon = format === 'html' ? FileCode2 : FileText;
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded border border-app-border bg-app-bg text-app-ink/55',
        compact ? 'app-text-micro px-1.5 py-0.5' : 'app-text-caption px-2 py-1',
      )}
    >
      <Icon size={compact ? 11 : 12} />
      <span>{label}</span>
    </span>
  );
}
