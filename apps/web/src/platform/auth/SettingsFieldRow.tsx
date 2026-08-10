import type { ReactNode } from 'react';

export function SettingsFieldRow({
  label,
  children,
  description,
}: {
  label: string;
  children: ReactNode;
  description?: string;
}) {
  return (
    <div className="grid grid-cols-[180px_1fr] items-start gap-6 border-b border-app-border py-4 last:border-b-0 max-[720px]:grid-cols-1 max-[720px]:gap-2">
      <div>
        <label className="app-text-control text-app-ink">{label}</label>
        {description ? (
          <p className="app-text-caption mt-0.5 text-app-ink/55">{description}</p>
        ) : null}
      </div>
      <div className="max-w-md">{children}</div>
    </div>
  );
}
