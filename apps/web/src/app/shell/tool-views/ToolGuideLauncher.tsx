import { useState, type ReactNode } from 'react';
import { BookOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { HelpGuideModal } from '@/src/app/shell/HelpCenterPage';
import {
  type FeatureGuideToolIds,
  getAiFeatureGuideSrc,
  hasAiFeatureGuide,
} from '@/src/app/shell/ai-feature-guides';

/**
 * Wraps a tool view and adds a floating "사용 가이드" button that opens the
 * matching per-feature guide. Rendered for every tool that has a guide, so a
 * single mount point covers all tools served through the tool route.
 */
export function ToolGuideLauncher({
  children,
  featureGuideToolIds,
  toolId,
}: {
  children: ReactNode;
  featureGuideToolIds: FeatureGuideToolIds;
  toolId: string;
}) {
  const { t } = useTranslation(['shell', 'common']);
  const [open, setOpen] = useState(false);
  const title = t(`shell:nav.${toolId}`, { defaultValue: toolId });
  const label = t('shell:helpCenter.featureGuideButton');

  if (!hasAiFeatureGuide(toolId, featureGuideToolIds)) {
    return children;
  }

  return (
    <>
      {children}
      <button
        className="fixed bottom-24 right-6 z-40 flex items-center gap-2 rounded-full border border-app-border bg-app-surface px-4 py-2.5 text-sm font-semibold text-app-ink shadow-lg transition-colors hover:border-app-accent/50 hover:bg-app-surface-hover"
        onClick={() => setOpen(true)}
        title={label}
        type="button"
      >
        <BookOpen size={16} className="text-app-accent" />
        <span>{label}</span>
      </button>
      {open ? (
        <HelpGuideModal
          closeLabel={t('common:actions.close')}
          onClose={() => setOpen(false)}
          src={getAiFeatureGuideSrc(toolId)}
          title={title}
        />
      ) : null}
    </>
  );
}
