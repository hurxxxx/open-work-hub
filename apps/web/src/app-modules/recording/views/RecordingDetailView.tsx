import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ArrowLeft,
  CalendarDays,
  CheckSquare,
  Database,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Send,
} from 'lucide-react';
import { Button, useConfirm } from '@open-work-hub/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { DocsViewerModal } from '@/src/app-modules/docs/public-api';
import {
  formatDateTime as formatZonedDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  isWorkspaceBootstrapAppEnabled,
  useWorkspaceBootstrapContext,
} from '@/src/platform/workspaces/workspace-bootstrap-context';
import { MeetingPickerModal } from './MeetingPickerModal';
import { DocLink, LinkedSubsection } from './RecordingDetailLinkedItems';
import { RecordingStageRail } from './RecordingStageRail';
import { TaskPickerModal } from './TaskPickerModal';
import { useRecordingDetailController } from './useRecordingDetailController';

function formatDateTime(
  value: string,
  timeZone: string,
  locale: string,
): string {
  return formatZonedDateTime(value, {
    dateStyle: 'medium',
    fallback: value,
    locale,
    timeStyle: 'short',
    timeZone,
  });
}

function useRecordingDetailElement() {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const { workspaceSlug, recordingId } = useParams();
  const navigate = useNavigate();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const docsEnabled = isWorkspaceBootstrapAppEnabled(
    workspaceBootstrap.data,
    'docs',
  );
  const timeZone = normalizeTimeZone(user?.time_zone);
  const { confirm, confirmDialog } = useConfirm();

  const messages = useMemo(
    () => ({
      loadFailed: t('apps:recording.errors.loadDetailFailed'),
      updateFailed: t('apps:recording.errors.updateFailed'),
      playbackFailed: t('apps:recording.errors.playbackFailed'),
      retryFailed: t('apps:recording.errors.retryFailed'),
      publishFailed: t('apps:recording.errors.publishFailed'),
      detachFailed: t('apps:recording.errors.detachFailed'),
      detachConfirmTitle: t('apps:recording.detail.detachConfirmTitle'),
      detachConfirmDescription: t(
        'apps:recording.detail.detachConfirmDescription',
      ),
      detachConfirmLabel: t('apps:recording.detail.detach'),
      detachCancelLabel: t('common:actions.cancel'),
    }),
    [t],
  );
  const controller = useRecordingDetailController({
    token,
    workspaceSlug,
    recordingId,
    messages,
    confirm,
  });
  const {
    recording,
    titleDraft,
    playbackUrl,
    loading,
    busy,
    error,
    titleStatus,
    meetingPickerOpen,
    taskPickerOpen,
    docPreview,
  } = controller.state;
  const { meetingTargets, taskTargets, otherTargets, retryable } =
    controller.derived;

  if (!workspaceSlug) return null;

  return (
    <div className="flex h-full flex-col bg-app-bg">
      <header className="flex items-center justify-between border-b border-app-border bg-app-surface px-6 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() =>
              navigate(buildWorkspaceAppPath(workspaceSlug, 'recording'))
            }
            className="inline-flex size-8 items-center justify-center rounded border border-app-border bg-app-surface-raised text-app-ink hover:bg-app-surface-subtle"
            aria-label={t('apps:recording.detail.back')}
          >
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0">
            <h1 className="app-text-title-md truncate text-app-ink">
              {recording?.title?.trim() || t('apps:recording.untitled')}
            </h1>
            {recording ? (
              <p className="app-text-caption text-app-ink/60">
                {formatDateTime(recording.started_at, timeZone, i18n.language)}
              </p>
            ) : null}
          </div>
        </div>
        <Button
          variant="secondary"
          onClick={() => void controller.actions.refresh()}
          disabled={loading}
        >
          <RefreshCw
            size={14}
            className={loading ? 'mr-1 animate-spin' : 'mr-1'}
          />
          {t('common:actions.reload')}
        </Button>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto p-6">
        <div className="mx-auto w-full max-w-3xl space-y-5">
          {error ? (
            <div className="flex items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
              <AlertCircle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          {!recording && loading ? (
            <div className="flex h-64 items-center justify-center text-app-ink/50">
              <Loader2 size={22} className="animate-spin" />
            </div>
          ) : null}

          {recording ? (
            <>
              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <label className="block">
                  <span className="app-text-caption mb-1 flex items-center justify-between text-app-ink/60">
                    <span>{t('apps:recording.detail.titleLabel')}</span>
                    {titleStatus === 'saving' ? (
                      <span className="inline-flex items-center gap-1 text-app-ink/45">
                        <Loader2 size={11} className="animate-spin" />
                        {t('common:actions.saving')}
                      </span>
                    ) : titleStatus === 'saved' ? (
                      <span className="text-app-success-text dark:text-app-success-text">
                        {t('apps:recording.detail.titleSaved')}
                      </span>
                    ) : null}
                  </span>
                  <input
                    value={titleDraft}
                    onChange={(event) => {
                      controller.actions.setTitleDraft(event.target.value);
                    }}
                    onBlur={() => void controller.actions.saveTitle()}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        (event.currentTarget as HTMLInputElement).blur();
                      }
                    }}
                    className="w-full rounded-md border border-app-border bg-app-surface-raised px-3 py-2 text-sm text-app-ink outline-none transition-colors focus:border-app-accent"
                  />
                </label>

                <div className="mt-4">
                  <RecordingStageRail
                    recording={recording}
                    onRetry={
                      retryable
                        ? () => void controller.actions.retry()
                        : undefined
                    }
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => void controller.actions.play()}
                    disabled={busy === 'playback' || Boolean(playbackUrl)}
                  >
                    {busy === 'playback' ? (
                      <Loader2 size={14} className="mr-1 animate-spin" />
                    ) : (
                      <Play size={14} className="mr-1" />
                    )}
                    {t('apps:recording.actions.play')}
                  </Button>
                  {retryable ? (
                    <Button
                      variant="secondary"
                      onClick={() => void controller.actions.retry()}
                      disabled={busy === 'retry'}
                    >
                      {busy === 'retry' ? (
                        <Loader2 size={14} className="mr-1 animate-spin" />
                      ) : (
                        <RefreshCw size={14} className="mr-1" />
                      )}
                      {t('apps:recording.actions.retry')}
                    </Button>
                  ) : null}
                </div>

                {playbackUrl ? (
                  <audio
                    controls
                    src={playbackUrl}
                    className="mt-4 w-full"
                    aria-label={t('apps:recording.actions.play')}
                  >
                    <track
                      kind="captions"
                      label={t('apps:recording.detail.rawTranscriptDoc')}
                    />
                  </audio>
                ) : null}
                {recording.failure_reason ? (
                  <p className="app-text-caption mt-3 text-[var(--ui-color-danger)]">
                    {recording.failure_reason}
                  </p>
                ) : null}
              </section>

              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="app-text-title-sm text-app-ink">
                      {t('apps:recording.detail.resultsTitle')}
                    </h2>
                    <p className="app-text-caption mt-1 text-app-ink/55">
                      {recording.result
                        ? t('apps:recording.detail.resultVersion', {
                            version: recording.result.version,
                          })
                        : t('apps:recording.detail.resultPending')}
                    </p>
                  </div>
                  {docsEnabled ? (
                    <Button
                      variant="secondary"
                      onClick={() => void controller.actions.publish()}
                      disabled={
                        busy !== null ||
                        recording.summary_status !== 'done' ||
                        !recording.result?.summary_text
                      }
                    >
                      {busy === 'publish' ? (
                        <Loader2 size={14} className="mr-1 animate-spin" />
                      ) : (
                        <Send size={14} className="mr-1" />
                      )}
                      {busy === 'publish'
                        ? t('apps:recording.detail.publishing')
                        : t('apps:recording.detail.publishToDocs')}
                    </Button>
                  ) : null}
                </div>

                {recording.result ? (
                  <div className="mt-4 space-y-4">
                    <article>
                      <h3 className="app-text-body font-semibold text-app-ink">
                        {t('apps:recording.detail.transcriptTitle')}
                      </h3>
                      <div className="app-text-body mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border border-app-border bg-app-surface-raised p-3 text-app-ink/80">
                        {recording.result.transcript_text}
                      </div>
                    </article>
                    <article>
                      <h3 className="app-text-body font-semibold text-app-ink">
                        {t('apps:recording.detail.summaryTitle')}
                      </h3>
                      <div className="app-text-body mt-2 whitespace-pre-wrap rounded-md border border-app-border bg-app-surface-raised p-3 text-app-ink/80">
                        {recording.result.summary_text ??
                          t('apps:recording.detail.resultPending')}
                      </div>
                    </article>
                    {recording.result.verifier_note ? (
                      <p className="app-text-caption text-app-ink/55">
                        {t('apps:recording.detail.verifierNote', {
                          note: recording.result.verifier_note,
                        })}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-5 border-t border-app-border pt-4">
                  <h3 className="app-text-body inline-flex items-center gap-1.5 font-semibold text-app-ink">
                    <FileText size={14} />
                    {t('apps:recording.detail.publicationsTitle')}
                  </h3>
                  <div className="mt-2 grid gap-2">
                    {(recording.publications ?? []).length > 0 ? (
                      (recording.publications ?? []).map((publication) => (
                        <DocLink
                          key={publication.id}
                          docId={publication.target_resource_id}
                          label={
                            publication.target_title ??
                            t('apps:recording.detail.publishedDocument', {
                              version: publication.result_version,
                            })
                          }
                          notReadyLabel={t('apps:recording.detail.notReady')}
                          onOpen={(docId, label) => {
                            controller.actions.setDocPreview({ docId, label });
                          }}
                        />
                      ))
                    ) : (
                      <p className="app-text-caption text-app-ink/45">
                        {t('apps:recording.detail.noPublications')}
                      </p>
                    )}
                  </div>
                </div>
              </section>

              <section className="rounded-md border border-app-border bg-app-surface p-4">
                <h2 className="app-text-title-sm text-app-ink">
                  {t('apps:recording.detail.linkedItems')}
                </h2>

                <div className="mt-4 space-y-5">
                  <LinkedSubsection
                    icon={<CalendarDays size={14} />}
                    title={t('apps:recording.detail.linkedMeetings')}
                    count={meetingTargets.length}
                    onAdd={() => controller.actions.setMeetingPickerOpen(true)}
                    addLabel={t('apps:recording.detail.addMeeting')}
                    emptyLabel={t('apps:recording.detail.noLinkedMeetings')}
                    items={meetingTargets}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={controller.actions.detachTarget}
                    detachLabel={t('apps:recording.detail.detach')}
                  />

                  <LinkedSubsection
                    icon={<CheckSquare size={14} />}
                    title={t('apps:recording.detail.linkedTasks')}
                    count={taskTargets.length}
                    onAdd={() => controller.actions.setTaskPickerOpen(true)}
                    addLabel={t('apps:recording.detail.addTask')}
                    emptyLabel={t('apps:recording.detail.noLinkedTasks')}
                    items={taskTargets}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={controller.actions.detachTarget}
                    detachLabel={t('apps:recording.detail.detach')}
                  />

                  <LinkedSubsection
                    icon={<Database size={14} />}
                    title={t('apps:recording.detail.otherConnections')}
                    count={otherTargets.length}
                    emptyLabel={t('apps:recording.detail.noOtherConnections')}
                    items={otherTargets}
                    busyId={busy}
                    workspaceSlug={workspaceSlug}
                    onDetach={controller.actions.detachTarget}
                    detachLabel={t('apps:recording.detail.detach')}
                  />
                </div>
              </section>
            </>
          ) : null}
        </div>
      </main>

      {recording ? (
        <>
          <MeetingPickerModal
            isOpen={meetingPickerOpen}
            onClose={() => controller.actions.setMeetingPickerOpen(false)}
            workspaceSlug={workspaceSlug}
            excludeMeetingIds={meetingTargets.map((target) => target.target_id)}
            onPick={(meeting) =>
              void controller.actions.attachMeeting(meeting.id)
            }
          />
          <TaskPickerModal
            isOpen={taskPickerOpen}
            onClose={() => controller.actions.setTaskPickerOpen(false)}
            workspaceSlug={workspaceSlug}
            excludeTaskIds={taskTargets.map((target) => target.target_id)}
            onPick={(task) => void controller.actions.attachTask(task.id)}
          />
          <DocsViewerModal
            open={docPreview !== null}
            itemId={docPreview?.docId}
            fallbackTitle={docPreview?.label}
            workspaceSlug={workspaceSlug}
            onOpenChange={(nextOpen) => {
              if (!nextOpen) controller.actions.setDocPreview(null);
            }}
          />
        </>
      ) : null}

      {confirmDialog}
    </div>
  );
}

export function RecordingDetailView() {
  return useRecordingDetailElement();
}
