import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, FileSpreadsheet, Loader2, Paperclip } from 'lucide-react';
import { Dialog } from '@ai-do/ui';

import type { LegacyIssueExcelExportJobWorkflow } from './useLegacyIssueExcelExportJob';
import { LegacyIssueToolbarButton } from './LegacyIssuePageParts';

export function LegacyIssueExcelExportControls({
  disabled,
  exportLabel,
  workflow,
}: {
  disabled?: boolean;
  exportLabel: string;
  workflow: LegacyIssueExcelExportJobWorkflow;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const [selectionOpen, setSelectionOpen] = useState(false);
  const [requestedIncludeAttachments, setRequestedIncludeAttachments] =
    useState(false);
  const activeExportIncludesAttachments =
    workflow.job?.include_attachments ?? requestedIncludeAttachments;

  async function startExport(includeAttachments: boolean) {
    setRequestedIncludeAttachments(includeAttachments);
    setSelectionOpen(false);
    await workflow.start(includeAttachments);
  }

  return (
    <>
      <LegacyIssueToolbarButton
        disabled={workflow.busy || disabled}
        icon={
          workflow.busy ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Download size={15} />
          )
        }
        label={
          workflow.busy
            ? t(
                activeExportIncludesAttachments
                  ? 'coreBusiness.excelExport.actions.preparingWithAttachments'
                  : 'coreBusiness.excelExport.actions.preparing',
              )
            : exportLabel
        }
        onClick={() => setSelectionOpen(true)}
      />
      <Dialog
        closeLabel={t('common:actions.close')}
        description={t('coreBusiness.excelExport.modal.description')}
        maxWidth="max-w-xl"
        open={selectionOpen}
        title={exportLabel}
        onOpenChange={setSelectionOpen}
      >
        <div className="grid gap-3">
          <button
            className="group flex w-full items-start gap-3 rounded-lg border border-app-border bg-app-bg p-4 text-left transition-colors hover:border-app-accent/50 hover:bg-app-surface-hover"
            type="button"
            onClick={() => void startExport(false)}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-app-accent/10 text-app-accent">
              <FileSpreadsheet aria-hidden="true" size={20} />
            </span>
            <span className="min-w-0">
              <span className="block app-text-body-sm font-semibold text-app-ink">
                {t('coreBusiness.excelExport.modal.dataOnly.title')}
              </span>
              <span className="mt-1 block app-text-caption leading-relaxed text-app-ink/60">
                {t('coreBusiness.excelExport.modal.dataOnly.description')}
              </span>
            </span>
          </button>
          <button
            className="group flex w-full items-start gap-3 rounded-lg border border-app-border bg-app-bg p-4 text-left transition-colors hover:border-app-accent/50 hover:bg-app-surface-hover"
            type="button"
            onClick={() => void startExport(true)}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-app-accent/10 text-app-accent">
              <Paperclip aria-hidden="true" size={20} />
            </span>
            <span className="min-w-0">
              <span className="block app-text-body-sm font-semibold text-app-ink">
                {t('coreBusiness.excelExport.modal.withAttachments.title')}
              </span>
              <span className="mt-1 block app-text-caption leading-relaxed text-app-ink/60">
                {t(
                  'coreBusiness.excelExport.modal.withAttachments.description',
                )}
              </span>
            </span>
          </button>
        </div>
      </Dialog>
      {workflow.busy && activeExportIncludesAttachments ? (
        <span
          className="max-w-64 app-text-caption text-app-ink/60"
          role="status"
        >
          {t('coreBusiness.excelExport.status.processingAttachments')}
        </span>
      ) : null}
    </>
  );
}
