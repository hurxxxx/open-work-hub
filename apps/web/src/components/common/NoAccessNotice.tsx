import { Lock } from 'lucide-react';
import type { ReactNode } from 'react';

interface NoAccessNoticeProps {
  /** e.g. "PMS 워크스페이스" or "Docs 워크스페이스" */
  workspaceLabel: string;
  /** What the user was trying to do, e.g. "태스크를 첨부" */
  action: string;
  /** Optional override for the second-line help text. */
  helpText?: ReactNode;
}

/**
 * Standardized notice rendered when the current user lacks the workspace
 * feature required for an action. Used inside picker modals and any other
 * surface that surfaces a feature the user can see but can't use.
 *
 * Pair with ``useAuth().hasFeature(...)`` to gate the data-fetching effects
 * upstream so the API call that would 403 is never even fired.
 */
export function NoAccessNotice({
  workspaceLabel,
  action,
  helpText,
}: NoAccessNoticeProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-4 py-8 text-center"
    >
      <Lock size={22} className="text-app-ink/40" />
      <p className="app-text-body text-app-ink">
        {workspaceLabel} 접근 권한이 없어 {action}할 수 없습니다.
      </p>
      <p className="app-text-caption text-app-ink/60 dark:text-app-ink/70">
        {helpText ?? (
          <>
            관리자에게 {workspaceLabel} 권한을 요청하시거나, 권한이 있는 회의 주최자/참석자에게 요청해주세요.
          </>
        )}
      </p>
    </div>
  );
}
