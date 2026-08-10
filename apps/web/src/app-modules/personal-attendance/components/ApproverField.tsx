import { UserCheck, UserCog } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ApprovalLine } from '../api/personal-attendance-api';
import { useAttendanceLabels } from '../lib/attendance-labels';

/**
 * 결재자 표시 — 야근·휴가·특근·유연근무 4종 공통.
 * 사용자가 선택하는 항목이 아니라 인사 정보로 자동 결정되므로 읽기 전용이다.
 * 부서장 부재 기간이면 代부서장이 결재자가 되고, 원 부서장을 함께 밝힌다.
 */
export function ApproverField({ line }: { line: ApprovalLine | null }) {
  const { t } = useTranslation(['apps', 'common']);
  const labels = useAttendanceLabels();

  if (!line) {
    return (
      <div>
        <span className="mb-1 block text-xs font-medium text-app-ink-muted">
          {t('apps:personalAttendance.approver.label')}
        </span>
        <div className="h-[3.25rem] animate-pulse rounded-lg bg-app-surface-subtle" />
      </div>
    );
  }

  const { approver, deptHead, delegation } = line;
  const acting = approver.role === 'ACTING_DEPT_HEAD';

  return (
    <div>
      <span className="mb-1 block text-xs font-medium text-app-ink-muted">
        {t('apps:personalAttendance.approver.labelAuto')}
      </span>
      <div className="rounded-lg border border-app-border bg-app-surface-subtle px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span
            className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
              acting ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400' : 'bg-app-accent-weak text-app-accent'
            }`}
          >
            {acting ? <UserCog className="size-4" /> : <UserCheck className="size-4" />}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold text-app-ink">{approver.name}</span>
              <span className="text-xs text-app-ink-muted">
                {approver.position} · {approver.department}
              </span>
            </div>
            <div className="text-[11px] text-app-ink-muted">
              {acting
                ? t('apps:personalAttendance.approver.actingDeptHead')
                : t('apps:personalAttendance.approver.deptHead')}
            </div>
          </div>
        </div>

        {acting && delegation ? (
          <p className="mt-1.5 border-t border-app-border pt-1.5 text-[11px] text-amber-700 dark:text-amber-400">
            {t('apps:personalAttendance.approver.delegationNotice', {
              name: deptHead.name,
              position: deptHead.position,
              reason: delegation.reason,
              from: labels.date(delegation.from),
              to: labels.date(delegation.to),
            })}
          </p>
        ) : null}
      </div>
    </div>
  );
}
