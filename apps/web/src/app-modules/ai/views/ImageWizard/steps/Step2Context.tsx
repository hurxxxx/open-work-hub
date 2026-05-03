import { useId, useState } from 'react';
import { Briefcase, Calendar, FileText, Lightbulb, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  MeetingPickerModal,
  TaskPickerModal,
} from '@/src/app-modules/recording/public-api';
import type { ContextRef, DetailsPayload } from '../../../api/image-wizard-api';
import { DocPickerModal } from '../pickers/DocPickerModal';

interface Step2ContextProps {
  workspaceSlug: string;
  details: DetailsPayload;
  contextRefs: ContextRef[];
  onChangeDetails: (next: DetailsPayload) => void;
  onChangeContextRefs: (next: ContextRef[]) => void;
}

export function Step2Context({
  workspaceSlug,
  details,
  contextRefs,
  onChangeDetails,
  onChangeContextRefs,
}: Step2ContextProps) {
  const { t } = useTranslation('apps');
  const audienceId = useId();
  const notesId = useId();
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
    <div className="space-y-5">
      <header className="space-y-1">
        <h2 className="app-text-heading-2 text-app-ink">
          {t('ai.imageWizard.steps.step2.heading')}
        </h2>
        <p className="app-text-body text-app-ink/60">
          {t('ai.imageWizard.steps.step2.description')}
        </p>
      </header>

      <section className="space-y-2">
        <label htmlFor={audienceId} className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.context.audienceLabel')}
        </label>
        <input
          id={audienceId}
          type="text"
          value={details.audience}
          maxLength={200}
          onChange={(event) => onChangeDetails({ ...details, audience: event.target.value })}
          placeholder={t('ai.imageWizard.context.audiencePlaceholder')}
          className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
        />
      </section>

      <section className="space-y-2">
        <label htmlFor={notesId} className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.context.notesLabel')}
        </label>
        <textarea
          id={notesId}
          value={details.notes}
          maxLength={2000}
          rows={4}
          onChange={(event) => onChangeDetails({ ...details, notes: event.target.value })}
          placeholder={t('ai.imageWizard.context.notesPlaceholder')}
          className="app-text-body w-full resize-y rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
        />
      </section>

      <section className="space-y-2">
        <label className="app-text-control-sm text-app-ink/70">
          {t('ai.imageWizard.context.attachLabel')}
        </label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <ContextBucket
            icon={<Calendar size={14} />}
            label={t('ai.imageWizard.context.meetings')}
            count={meetingRefs.length}
            onAdd={() => setOpenModal('meeting')}
          >
            {meetingRefs.map((ref) => (
              <ContextChip
                key={`${ref.kind}:${ref.id}`}
                label={ref.snapshot?.title || ref.id}
                onRemove={() => detach(ref.kind, ref.id)}
              />
            ))}
          </ContextBucket>
          <ContextBucket
            icon={<Briefcase size={14} />}
            label={t('ai.imageWizard.context.tasks')}
            count={taskRefs.length}
            onAdd={() => setOpenModal('task')}
          >
            {taskRefs.map((ref) => (
              <ContextChip
                key={`${ref.kind}:${ref.id}`}
                label={ref.snapshot?.title || ref.id}
                onRemove={() => detach(ref.kind, ref.id)}
              />
            ))}
          </ContextBucket>
          <ContextBucket
            icon={<FileText size={14} />}
            label={t('ai.imageWizard.context.docs')}
            count={docRefs.length}
            onAdd={() => setOpenModal('doc')}
          >
            {docRefs.map((ref) => (
              <ContextChip
                key={`${ref.kind}:${ref.id}`}
                label={ref.snapshot?.title || ref.id}
                onRemove={() => detach(ref.kind, ref.id)}
              />
            ))}
          </ContextBucket>
        </div>
      </section>

      <p className="flex items-start gap-2 rounded-md bg-app-accent/10 px-3 py-2 app-text-caption text-app-ink/70">
        <Lightbulb size={13} className="mt-0.5 shrink-0 text-app-accent" />
        <span>{t('ai.imageWizard.context.encourageTip')}</span>
      </p>

      <MeetingPickerModal
        isOpen={openModal === 'meeting'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeMeetingIds={meetingRefs.map((ref) => ref.id)}
        onPick={(meeting) =>
          attach({ kind: 'meeting', id: meeting.id, snapshot: { title: meeting.title } })
        }
      />
      <TaskPickerModal
        isOpen={openModal === 'task'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeIssueIds={taskRefs.map((ref) => ref.id)}
        onPick={(issue) =>
          attach({ kind: 'task', id: issue.id, snapshot: { title: issue.title } })
        }
      />
      <DocPickerModal
        isOpen={openModal === 'doc'}
        onClose={() => setOpenModal(null)}
        workspaceSlug={workspaceSlug}
        excludeDocIds={docRefs.map((ref) => ref.id)}
        onPick={(doc) =>
          attach({ kind: 'doc', id: doc.id, snapshot: { title: doc.title } })
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
  onAdd: () => void;
}

function ContextBucket({ icon, label, count, children, onAdd }: ContextBucketProps) {
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
          className="app-text-control-sm text-app-accent hover:underline"
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
  onRemove: () => void;
}

function ContextChip({ label, onRemove }: ContextChipProps) {
  const { t } = useTranslation('apps');
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-hover px-2 py-1 app-text-caption text-app-ink">
      <span className="max-w-[10rem] truncate" title={label}>
        {label}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="text-app-ink/40 hover:text-app-ink"
        aria-label={t('ai.imageWizard.context.removeReference')}
      >
        <X size={10} />
      </button>
    </span>
  );
}

export default Step2Context;
