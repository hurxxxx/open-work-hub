import { FileText, Loader2, Plus, Trash2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { RecordingTarget } from '../api/recording-api';
import { recordingTargetHref } from './recording-detail-model';

interface LinkedSubsectionProps {
  icon: ReactNode;
  title: string;
  count: number;
  onAdd?: () => void;
  addLabel?: string;
  emptyLabel: string;
  items: RecordingTarget[];
  busyId: string | null;

  onDetach: (target: RecordingTarget) => void;
  detachLabel: string;
}

export function LinkedSubsection({
  icon,
  title,
  count,
  onAdd,
  addLabel,
  emptyLabel,
  items,
  busyId,
  onDetach,
  detachLabel,
}: LinkedSubsectionProps) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-app-ink">
          <span className="text-app-ink/50">{icon}</span>
          <span className="app-text-body font-medium">{title}</span>
          <span className="app-text-caption text-app-ink/45">{count}</span>
        </div>
        {onAdd && addLabel ? (
          <button
            type="button"
            onClick={onAdd}
            className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface-raised px-2 py-1 text-app-ink hover:bg-app-surface-subtle"
          >
            <Plus size={12} />
            {addLabel}
          </button>
        ) : null}
      </div>
      {items.length === 0 ? (
        <p className="app-text-caption text-app-ink/50">{emptyLabel}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((target) => (
            <TargetRow
              key={target.id}
              busy={busyId === target.id}
              target={target}
              href={recordingTargetHref(target)}
              onDetach={() => onDetach(target)}
              detachLabel={detachLabel}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface DocLinkProps {
  docId: string | null | undefined;
  label: string;
  notReadyLabel: string;
  onOpen: (docId: string, label: string) => void;
}

export function DocLink({ docId, label, notReadyLabel, onOpen }: DocLinkProps) {
  if (!docId) {
    return (
      <div className="flex w-full items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink/55">
        <FileText size={14} />
        <span>{label}</span>
        <span className="ml-auto app-text-caption">{notReadyLabel}</span>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(docId, label)}
      aria-haspopup="dialog"
      className="flex w-full items-center gap-2 rounded border border-app-border bg-app-surface-raised px-3 py-2 text-left text-sm text-app-ink hover:bg-app-surface-subtle"
    >
      <FileText size={14} />
      <span>{label}</span>
    </button>
  );
}

interface TargetRowProps {
  busy: boolean;
  target: RecordingTarget;
  href: string | null;
  onDetach: () => void;
  detachLabel: string;
}

function TargetRow({
  busy,
  target,
  href,
  onDetach,
  detachLabel,
}: TargetRowProps) {
  const { t } = useTranslation('apps');
  const appLabel = t(`recording.detail.targetApps.${target.target_app}`, {
    defaultValue: target.target_app,
  });
  const typeLabel = t(`recording.detail.targetTypes.${target.target_type}`, {
    defaultValue: target.target_type,
  });
  const shortId =
    target.target_id.length > 12
      ? `${target.target_id.slice(0, 8)}...${target.target_id.slice(-4)}`
      : target.target_id;
  const displayTitle =
    target.target_title?.trim() || `${appLabel} · ${shortId}`;
  const detachAriaLabel = t('recording.detail.detachItemLabel', {
    item: displayTitle,
  });
  const content = (
    <div className="min-w-0">
      <p
        className="app-text-body line-clamp-1 text-app-ink"
        title={target.target_id}
      >
        {displayTitle}
      </p>
      <p className="app-text-caption line-clamp-1 text-app-ink/45">
        {typeLabel}
      </p>
    </div>
  );
  return (
    <li className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-raised px-3 py-2">
      {href ? (
        <Link
          to={href}
          className="flex min-w-0 flex-1 items-center gap-2 hover:underline"
        >
          {content}
        </Link>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-2">{content}</div>
      )}
      <button
        type="button"
        onClick={onDetach}
        disabled={busy}
        className="ml-2 shrink-0 rounded p-1 text-app-ink/40 hover:text-[var(--ui-color-danger)] disabled:opacity-40"
        aria-label={detachAriaLabel || detachLabel}
      >
        {busy ? (
          <Loader2 size={14} className="animate-spin" />
        ) : (
          <Trash2 size={14} />
        )}
      </button>
    </li>
  );
}
