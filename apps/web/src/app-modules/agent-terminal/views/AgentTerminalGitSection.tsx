import { ChevronDown, ChevronRight } from 'lucide-react';
import { type ReactNode, useId, useState } from 'react';

export function AgentTerminalGitSection({
  children,
  count,
  defaultOpen = true,
  hidden = false,
  title,
}: {
  children: ReactNode;
  count?: number;
  defaultOpen?: boolean;
  hidden?: boolean;
  title: string;
}) {
  const contentId = useId();
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section
      className="border-b border-app-border last:border-b-0"
      hidden={hidden}
    >
      <button
        aria-controls={contentId}
        aria-expanded={open}
        className="flex w-full items-center gap-2 bg-app-surface px-3 py-2 text-left transition-colors hover:bg-app-surface-hover"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        {open ? (
          <ChevronDown aria-hidden="true" className="size-3.5 shrink-0" />
        ) : (
          <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
        )}
        <span className="min-w-0 flex-1 truncate app-text-caption font-semibold text-app-ink/70">
          {title}
        </span>
        {count === undefined ? null : (
          <span className="app-text-caption tabular-nums text-app-ink/45">
            {count}
          </span>
        )}
      </button>
      {open ? <div id={contentId}>{children}</div> : null}
    </section>
  );
}
