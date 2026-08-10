import { Button, Dialog } from '@open-alm/ui';
import { Check, Loader2, ShieldAlert, X } from 'lucide-react';
import { useEffect, useMemo, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { getAiApprovalStatus } from '../../api/chatbot-api';
import type { PendingApproval } from '../../api/agent-events';
import {
  INITIAL_APPROVAL_MODAL_STATE,
  approvalModalReducer,
  approvalToolLabelKey,
  formatApprovalArgumentsJson,
} from './approval-modal-model';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

export interface ApprovalModalProps {
  approval: PendingApproval;
  isSubmitting?: boolean;
  errorMessage?: string | null;
  onResolve: (
    decision: 'approved' | 'rejected',
    reason?: string,
  ) => Promise<void> | void;
  onClose: () => Promise<void> | void;
}

export function ApprovalModal({
  approval,
  isSubmitting = false,
  errorMessage = null,
  onResolve,
  onClose,
}: ApprovalModalProps) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation(['apps', 'auth', 'common']);
  const [{ details, detailsError, loadingDetails, rejectReason }, dispatch] =
    useReducer(approvalModalReducer, INITIAL_APPROVAL_MODAL_STATE);

  useEffect(() => {
    dispatch({ type: 'load-details' });
    if (!token) {
      dispatch({
        type: 'details-failed',
        message: t('auth:errors.noActiveSession'),
      });
      return;
    }

    let cancelled = false;
    getAiApprovalStatus(token, approval.approval_id)
      .then((response) => {
        if (!cancelled) {
          dispatch({
            type: 'details-loaded',
            details: response,
          });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          dispatch({
            type: 'details-failed',
            message:
              error instanceof Error
                ? error.message
                : t('ai.approval.loadDetailsFailed'),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [approval.approval_id, t, token]);

  const expiresLabel = useMemo(
    () =>
      formatDateTime(approval.expires_at_ms, {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        locale: i18n.language,
        timeZone: normalizeTimeZone(user?.time_zone),
      }),
    [approval.expires_at_ms, i18n.language, user?.time_zone],
  );

  const argumentsJson = useMemo(
    () => formatApprovalArgumentsJson(details?.arguments_json),
    [details?.arguments_json],
  );

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open
      onOpenChange={() => undefined}
      title={t('ai.approval.title')}
      description={t('ai.approval.description')}
      maxWidth="max-w-2xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
          <Button
            variant="secondary"
            onClick={() => {
              void onClose();
            }}
            disabled={isSubmitting}
          >
            {isSubmitting
              ? t('common:actions.saving')
              : t('ai.approval.cancelRequest')}
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                void onResolve('rejected', rejectReason);
              }}
              disabled={isSubmitting}
            >
              <X size={14} />
              {isSubmitting
                ? t('ai.approval.rejecting')
                : t('ai.approval.reject')}
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                void onResolve('approved');
              }}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Check size={14} />
              )}
              {isSubmitting
                ? t('ai.approval.approving')
                : t('ai.approval.approve')}
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        <div className="rounded-md border border-app-border bg-app-surface-sidebar px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-app-accent/10 p-2 text-app-accent">
              <ShieldAlert size={16} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="app-text-overline text-app-ink/60">
                {t(approvalToolLabelKey(approval.tool))}
              </p>
              <p className="app-text-body font-medium text-app-ink">
                {approval.tool}
              </p>
              <p className="app-text-caption mt-1 text-app-ink/60">
                {t('ai.approval.expires', { date: expiresLabel })}
              </p>
            </div>
          </div>
        </div>

        {approval.resource_preview ? (
          <div className="space-y-2">
            <p className="app-text-overline text-app-ink/60">
              {t('ai.approval.preview')}
            </p>
            <div className="rounded-md border border-app-border bg-app-surface p-3">
              <p className="app-text-body-sm whitespace-pre-wrap break-words text-app-ink">
                {approval.resource_preview}
              </p>
            </div>
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="app-text-overline text-app-ink/60">
              {t('ai.approval.args')}
            </p>
            {loadingDetails ? (
              <span className="app-text-caption text-app-ink/50">
                {t('ai.approval.detailsLoading')}
              </span>
            ) : null}
          </div>
          <details
            className="rounded-md border border-app-border bg-app-surface p-3"
            open
          >
            <summary className="app-text-body-sm cursor-pointer font-medium text-app-ink">
              {t('ai.approval.showJson')}
            </summary>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-app-bg p-3 text-xs leading-6 text-app-ink">
              {argumentsJson}
            </pre>
          </details>
          {detailsError ? (
            <p className="app-text-caption text-[var(--ui-color-danger)]">
              {detailsError}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <label
              htmlFor={`approval-reason-${approval.approval_id}`}
              className="app-text-overline text-app-ink/60"
            >
              {t('ai.approval.reason')}
            </label>
            <span className="app-text-caption text-app-ink/50">
              {rejectReason.length}/140
            </span>
          </div>
          <textarea
            id={`approval-reason-${approval.approval_id}`}
            aria-label={t('ai.approval.reason')}
            value={rejectReason}
            onChange={(event) =>
              dispatch({
                type: 'reject-reason',
                value: event.target.value,
              })
            }
            placeholder={t('ai.approval.reasonPlaceholder')}
            disabled={isSubmitting}
            rows={3}
            className="app-text-body-sm w-full resize-none rounded-md border border-app-border bg-app-surface px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>

        {errorMessage ? (
          <div
            role="alert"
            className="app-text-body-sm rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {errorMessage}
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
