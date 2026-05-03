import { useState } from 'react';
import { Briefcase, Calendar, FileText, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  MeetingPickerModal,
  TaskPickerModal,
} from '@/src/app-modules/recording/public-api';
import type { ContextRef, DetailsPayload } from '../../../api/image-wizard-api';
import { DocPickerModal } from '../DocPickerModal';

interface ContextStepProps {
  workspaceSlug: string;
  details: DetailsPayload;
  contextRefs: ContextRef[];
  disabled?: boolean;
  onChangeDetails: (next: DetailsPayload) => void;
  onChangeContextRefs: (next: ContextRef[]) => void;
}

export function ContextStep({
  workspaceSlug,
  details,
  contextRefs,
  disabled = false,
  onChangeDetails,
  onChangeContextRefs,
}: ContextStepProps) {
  const { t } = useTranslation('apps');
  const [openModal, setOpenModal] = useState<'meeting' | 'task' | 'doc' | null>(null);

  function attach(next: ContextRef) {
    if (contextRefs.some((ref) => ref.kind === next.kind && ref.id === next.id)) return;
    onChangeContextRefs([...contextRefs, next]);
  }

  function detach(kind: string, id: string) {
    onChangeContextRefs(contextRefs.filter((ref) => !(ref.kind === kind && ref.id === id)));
  }

  const meetingRefs = contextRefs.filter((ref) => ref.kind === 'meeting');
  const taskRefs = contextRefs.filter((ref) => ref.kind === 'task');
  const docRefs = contextRefs.filter((ref) => ref.kind === 'doc');

  return (
    <div className="space-y-4">
      <p className="app-text-caption text-app-ink/60">
        {t('ai.imageWizard.steps.context.description')}
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ContextBucket
          icon={<Calendar size={14} />}
          label={t('ai.imageWizard.context.meetings')}
          count={meetingRefs.length}
          disabled={disabled}
          onAdd={() => {
            if (!disabled) setOpenModal('meeting');
          }}
        >
          {meetingRefs.map((ref) => (
            <ContextChip
              key={`${ref.kind}:${ref.id}`}
              label={ref.snapshot?.title || ref.id}
              disabled={disabled}
              onRemove={() => detach(ref.kind, ref.id)}
            />
          ))}
        </ContextBucket>
        <ContextBucket
          icon={<Briefcase size={14} />}
          label={t('ai.imageWizard.context.tasks')}
          count={taskRefs.length}
          disabled={disabled}
          onAdd={() => {
            if (!disabled) setOpenModal('task');
          }}
        >
          {taskRefs.map((ref) => (
            <ContextChip
              key={`${ref.kind}:${ref.id}`}
              label={ref.snapshot?.title || ref.id}
              disabled={disabled}
              onRemove={() => detach(ref.kind, ref.id)}
            />
          ))}
        </ContextBucket>
        <ContextBucket
          icon={<FileText size={14} />}
          label={t('ai.imageWizard.context.docs')}
          count={docRefs.length}
          disabled={disabled}
          onAdd={() => {
            if (!disabled) setOpenModal('doc');
          }}
        >
          {docRefs.map((ref) => (
            <ContextChip
              key={`${ref.kind}:${ref.id}`}
              label={ref.snapshot?.title || ref.id}
              disabled={disabled}
              onRemove={() => detach(ref.kind, ref.id)}
            />
          ))}
        </ContextBucket>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.context.audienceLabel')}
          </label>
          <input
            type="text"
            value={details.audience}
            maxLength={200}
            disabled={disabled}
            onChange={(event) => onChangeDetails({ ...details, audience: event.target.value })}
            placeholder={t('ai.imageWizard.context.audiencePlaceholder')}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>
        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('ai.imageWizard.context.notesLabel')}
          </label>
          <textarea
            value={details.notes}
            maxLength={2000}
            rows={2}
            disabled={disabled}
            onChange={(event) => onChangeDetails({ ...details, notes: event.target.value })}
            placeholder={t('ai.imageWizard.context.notesPlaceholder')}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>
      </div>

      <MeetingPickerModal
        isOpen={!disabled && openModal === 'meeting'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeMeetingIds={meetingRefs.map((ref) => ref.id)}
        onPick={(meeting) =>
          attach({
            kind: 'meeting',
            id: meeting.id,
            snapshot: { title: meeting.title },
          })
        }
      />
      <TaskPickerModal
        isOpen={!disabled && openModal === 'task'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeIssueIds={taskRefs.map((ref) => ref.id)}
        onPick={(issue) =>
          attach({
            kind: 'task',
            id: issue.id,
            snapshot: { title: issue.title },
          })
        }
      />
      <DocPickerModal
        isOpen={!disabled && openModal === 'doc'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeDocIds={docRefs.map((ref) => ref.id)}
        onPick={(doc) =>
          attach({
            kind: 'doc',
            id: doc.id,
            snapshot: { title: doc.title },
          })
        }
      />
    </div>
  );
}

interface ContextBucketProps {
  icon: React.ReactNode;
  label: string;
  count: number;
  children: React.ReactNode;
  disabled?: boolean;
  onAdd: () => void;
}

function ContextBucket({
  icon,
  label,
  count,
  children,
  disabled = false,
  onAdd,
}: ContextBucketProps) {
  const { t } = useTranslation('apps');
  return (
    <div className="space-y-2 rounded-md border border-app-border bg-app-surface-sidebar p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-app-ink">
          {icon}
          <span className="app-text-control-sm">{label}</span>
          <span className="app-text-caption text-app-ink/40">({count})</span>
        </div>
        <button
          type="button"
          onClick={onAdd}
          disabled={disabled}
          className="app-text-control-sm text-app-accent hover:underline disabled:cursor-not-allowed disabled:opacity-60"
        >
          {t('common:actions.add')}
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

interface ContextChipProps {
  label: string;
  disabled?: boolean;
  onRemove: () => void;
}

function ContextChip({ label, disabled = false, onRemove }: ContextChipProps) {
  const { t } = useTranslation('apps');
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-hover px-2 py-1 app-text-caption text-app-ink">
      <span className="max-w-[12rem] truncate" title={label}>
        {label}
      </span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        className="text-app-ink/40 hover:text-app-ink disabled:cursor-not-allowed disabled:opacity-60"
        aria-label={t('ai.imageWizard.context.removeLabel', { label })}
      >
        <X size={10} />
      </button>
    </span>
  );
}

export default ContextStep;
