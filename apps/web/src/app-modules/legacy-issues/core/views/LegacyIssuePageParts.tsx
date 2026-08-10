import type { FormEvent, ReactNode } from 'react';
import { Search } from 'lucide-react';

export function LegacyIssuePageHeader({
  actions,
  eyebrow,
  title,
}: {
  actions: ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <header className="border-b border-app-border bg-app-bg px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="app-text-caption font-semibold text-app-ink/50">
            {eyebrow}
          </p>
          <h1 className="truncate app-text-title font-semibold">{title}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      </div>
    </header>
  );
}

export function LegacyIssueSearchToolbar({
  inputId,
  onSearchChange,
  onSubmit,
  searchLabel,
  searchPlaceholder,
  searchValue,
  trailing,
}: {
  inputId: string;
  onSearchChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  searchLabel: string;
  searchPlaceholder: string;
  searchValue: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="border-b border-app-border bg-app-surface-sidebar px-4 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <form
          className="flex min-w-[18rem] flex-1 items-center gap-2"
          onSubmit={onSubmit}
        >
          <label className="sr-only" htmlFor={inputId}>
            {searchLabel}
          </label>
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1">
            <Search size={15} className="shrink-0 text-app-ink/45" />
            <input
              id={inputId}
              className="min-w-0 flex-1 bg-transparent py-1 app-text-body-sm outline-none"
              placeholder={searchPlaceholder}
              value={searchValue}
              onChange={(event) => onSearchChange(event.target.value)}
            />
          </div>
          <LegacyIssueToolbarButton
            icon={<Search size={16} />}
            label={searchLabel}
            type="submit"
          />
        </form>
        {trailing ? (
          <div className="flex flex-wrap items-center gap-2">{trailing}</div>
        ) : null}
      </div>
    </div>
  );
}

export function LegacyIssueGridToolbarSearch({
  inputId,
  onSearchChange,
  onSubmit,
  searchLabel,
  searchPlaceholder,
  searchValue,
  summary,
}: {
  inputId: string;
  onSearchChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  searchLabel: string;
  searchPlaceholder: string;
  searchValue: string;
  summary: ReactNode;
}) {
  return (
    <>
      <span className="shrink-0 px-1 app-text-caption text-app-ink/55">
        {summary}
      </span>
      <form
        className="flex h-7 w-[min(20rem,45vw)] shrink-0 items-center rounded-md border border-app-border bg-app-bg"
        onSubmit={onSubmit}
      >
        <label className="sr-only" htmlFor={inputId}>
          {searchLabel}
        </label>
        <Search size={14} className="ml-2 shrink-0 text-app-ink/45" />
        <input
          id={inputId}
          className="min-w-0 flex-1 bg-transparent px-2 app-text-caption outline-none"
          placeholder={searchPlaceholder}
          value={searchValue}
          onChange={(event) => onSearchChange(event.target.value)}
        />
        <button
          className="inline-flex h-full shrink-0 items-center border-l border-app-border px-2 app-text-caption font-medium text-app-ink/70 hover:bg-app-surface-hover"
          title={searchLabel}
          type="submit"
        >
          <Search size={14} />
          <span className="sr-only">{searchLabel}</span>
        </button>
      </form>
    </>
  );
}

export function LegacyIssueToolbarButton({
  disabled,
  icon,
  label,
  onClick,
  type = 'button',
}: {
  disabled?: boolean;
  icon: ReactNode;
  label: string;
  onClick?: () => void;
  type?: 'button' | 'submit';
}) {
  return (
    <button
      className="app-control h-9 px-3"
      disabled={disabled}
      type={type}
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
}

export function LegacyIssueTotalBar({ children }: { children: ReactNode }) {
  return (
    <div className="border-b border-app-border px-4 py-2 app-text-caption text-app-ink/50">
      {children}
    </div>
  );
}
