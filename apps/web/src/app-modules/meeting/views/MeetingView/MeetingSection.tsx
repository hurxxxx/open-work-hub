import type { ReactNode } from 'react';
import { Plus } from 'lucide-react';

export function Section({
  icon,
  title,
  count,
  onAdd,
  addLabel,
  headerAction,
  children,
}: {
  icon: ReactNode;
  title: string;
  count: number;
  onAdd?: () => void;
  addLabel?: string;
  headerAction?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="app-text-overline inline-flex items-center gap-1.5 text-app-ink/60 dark:text-app-ink/70">
          <span className="text-app-ink/60 dark:text-app-ink/70">{icon}</span>
          {title}
          <span className="text-app-ink/40 dark:text-app-ink/50">({count})</span>
        </h3>
        {headerAction ?? (onAdd ? (
          <button
            type="button"
            onClick={onAdd}
            className="app-text-caption inline-flex items-center gap-1 text-app-accent hover:underline"
          >
            <Plus size={12} />
            {addLabel}
          </button>
        ) : null)}
      </div>
      {children}
    </section>
  );
}

export function EmptyRow({ text }: { text: string }) {
  return (
    <p className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-3 text-center text-app-ink/50 dark:text-app-ink/60">
      {text}
    </p>
  );
}
