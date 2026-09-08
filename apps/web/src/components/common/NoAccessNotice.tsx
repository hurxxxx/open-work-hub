import { Lock } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface NoAccessNoticeProps {
  /** User-facing workspace label, usually already localized by the caller. */
  appLabel: string;
  /** User-facing action phrase, usually already localized by the caller. */
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
  appLabel,
  action,
  helpText,
}: NoAccessNoticeProps) {
  const { t } = useTranslation('common');
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-4 py-8 text-center"
    >
      <Lock size={22} className="text-app-ink/40" />
      <p className="app-text-body text-app-ink">
        {t('accessNotice.blockedAction', { app: appLabel, action })}
      </p>
      <p className="app-text-caption text-app-ink/60 dark:text-app-ink/70">
        {helpText ?? t('accessNotice.requestHelp', { app: appLabel })}
      </p>
    </div>
  );
}
