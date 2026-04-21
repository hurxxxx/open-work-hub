import { Button, Dialog } from '@aidoo/ui';
import { Check, Loader2, ShieldAlert, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  getAiApprovalStatus,
  type AiApprovalStatusResponse,
} from '@/src/domains/ai/ai-api';
import type { PendingApproval } from '@/src/domains/ai/agent-events';
import { useAuth } from '@/src/domains/auth/auth-provider';

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

function approvalToolLabel(toolName: string): string {
  if (toolName.startsWith('pms.')) {
    return 'PMS 변경';
  }
  if (toolName.startsWith('planner.')) {
    return '일정 변경';
  }
  if (toolName.startsWith('docs.')) {
    return '문서 변경';
  }
  if (toolName.startsWith('meeting.')) {
    return '회의 변경';
  }
  return '승인 필요 작업';
}

function prettifyArgumentsJson(raw: string | null | undefined): string {
  if (!raw) {
    return '{}';
  }
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export function ApprovalModal({
  approval,
  isSubmitting = false,
  errorMessage = null,
  onResolve,
  onClose,
}: ApprovalModalProps) {
  const { token } = useAuth();
  const [rejectReason, setRejectReason] = useState('');
  const [details, setDetails] = useState<AiApprovalStatusResponse | null>(null);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    if (!token) {
      setDetails(null);
      setDetailsError('로그인이 필요합니다.');
      return;
    }

    let cancelled = false;
    setLoadingDetails(true);
    setDetailsError(null);
    getAiApprovalStatus(token, approval.approval_id)
      .then((response) => {
        if (!cancelled) {
          setDetails(response);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetails(null);
          setDetailsError(
            error instanceof Error
              ? error.message
              : '승인 상세를 불러오지 못했습니다.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingDetails(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [approval.approval_id, token]);

  useEffect(() => {
    setRejectReason('');
  }, [approval.approval_id]);

  const expiresLabel = useMemo(
    () =>
      new Date(approval.expires_at_ms).toLocaleString('ko-KR', {
        month: 'numeric',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
    [approval.expires_at_ms],
  );

  const argumentsJson = useMemo(
    () => prettifyArgumentsJson(details?.arguments_json),
    [details?.arguments_json],
  );

  return (
    <Dialog
      open
      onOpenChange={() => undefined}
      title="작업 승인 필요"
      description="이 변경은 실제 워크스페이스 데이터를 수정합니다. 내용을 확인한 뒤 승인하거나 취소하세요."
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
            {isSubmitting ? '처리 중...' : '요청 취소'}
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
              {isSubmitting ? '거절 중...' : '거절'}
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
              {isSubmitting ? '승인 중...' : '승인'}
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
                {approvalToolLabel(approval.tool)}
              </p>
              <p className="app-text-body font-medium text-app-ink">
                {approval.tool}
              </p>
              <p className="app-text-caption mt-1 text-app-ink/60">
                만료 예정: {expiresLabel}
              </p>
            </div>
          </div>
        </div>

        {approval.resource_preview ? (
          <div className="space-y-2">
            <p className="app-text-overline text-app-ink/60">대상 미리보기</p>
            <div className="rounded-md border border-app-border bg-app-surface px-3 py-3">
              <p className="app-text-body-sm whitespace-pre-wrap break-words text-app-ink">
                {approval.resource_preview}
              </p>
            </div>
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="app-text-overline text-app-ink/60">전달 인자</p>
            {loadingDetails ? (
              <span className="app-text-caption text-app-ink/50">
                상세 불러오는 중...
              </span>
            ) : null}
          </div>
          <details className="rounded-md border border-app-border bg-app-surface px-3 py-3" open>
            <summary className="app-text-body-sm cursor-pointer font-medium text-app-ink">
              JSON 보기
            </summary>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-app-bg px-3 py-3 text-xs leading-6 text-app-ink">
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
              거절 사유
            </label>
            <span className="app-text-caption text-app-ink/50">
              {rejectReason.length}/140
            </span>
          </div>
          <textarea
            id={`approval-reason-${approval.approval_id}`}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value.slice(0, 140))}
            placeholder="필요하면 거절 사유를 남기세요. 비워도 됩니다."
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
