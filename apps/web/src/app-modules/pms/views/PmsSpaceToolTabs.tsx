import {
  Activity,
  Calendar,
  FileText,
  Grid,
  Layout,
  List as ListIcon,
  Table,
  type LucideIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import {
  buildPmsSpaceDocsToolPath,
  buildPmsSpaceTaskToolPath,
  buildPmsSpaceToolPath,
  type PmsTaskListToolTab,
} from './pms-view-route';

export type PmsSpaceToolTab = 'overview' | 'docs' | PmsTaskListToolTab;

type SpaceToolTabItem = {
  icon: LucideIcon;
  labelKey: string;
  tab: PmsSpaceToolTab;
};

const SPACE_TOOL_TABS: readonly SpaceToolTabItem[] = [
  { icon: Layout, labelKey: 'pms.spaceOverview.overview', tab: 'overview' },
  { icon: FileText, labelKey: 'pms.spaceOverview.teamDocs', tab: 'docs' },
  { icon: ListIcon, labelKey: 'pms.viewTabs.list', tab: 'list' },
  { icon: Grid, labelKey: 'pms.viewTabs.board', tab: 'board' },
  { icon: Calendar, labelKey: 'pms.viewTabs.calendar', tab: 'calendar' },
  { icon: Activity, labelKey: 'pms.viewTabs.gantt', tab: 'gantt' },
  { icon: Table, labelKey: 'pms.viewTabs.table', tab: 'table' },
];

export function PmsSpaceToolTabs({
  activeTab,
  className,
  spaceId,
}: {
  activeTab: PmsSpaceToolTab;
  className?: string;
  spaceId: string;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation('apps');

  const buildPath = (tab: PmsSpaceToolTab): string => {
    if (tab === 'overview') {
      return buildPmsSpaceToolPath(spaceId, {});
    }
    if (tab === 'docs') {
      return buildPmsSpaceDocsToolPath({ spaceId });
    }
    return buildPmsSpaceTaskToolPath({ spaceId, tab });
  };

  return (
    <nav className={cn('flex items-center gap-1 overflow-x-auto', className)}>
      {SPACE_TOOL_TABS.map((item) => {
        const active = item.tab === activeTab;
        return (
          <button
            key={item.tab}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'app-text-control-sm inline-flex h-8 shrink-0 items-center gap-1 border-b-2 px-2 transition-colors',
              active
                ? 'border-app-ink font-semibold text-app-ink'
                : 'border-transparent text-app-ink/60 hover:text-app-ink',
            )}
            onClick={() => navigate(buildPath(item.tab))}
            type="button"
          >
            <item.icon aria-hidden="true" size={13} />
            {t(item.labelKey)}
          </button>
        );
      })}
    </nav>
  );
}
