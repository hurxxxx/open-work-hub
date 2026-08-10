import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LibraryBig } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';

import { fetchReportStatus } from '../api/industry-report-api';
import { NewsView } from './NewsView';
import { IndustryReportView, type ReportTab, REPORT_TABS } from './IndustryReportView';

/**
 * Route component for the "뉴스·리포트" app. The left app sidebar drives which
 * section is shown via the `?view`/`?tab` query (see the news manifest nav
 * items); this component reads that query and renders the matching surface.
 */
export function NewsHubView() {
  const [params] = useSearchParams();
  const view = params.get('view') === 'report' ? 'report' : 'news';
  const tabParam = params.get('tab') ?? '';
  const tab: ReportTab = (REPORT_TABS as readonly string[]).includes(tabParam)
    ? (tabParam as ReportTab)
    : 'trend';

  if (view === 'news') {
    return <NewsView />;
  }

  return (
    <div className="flex h-full w-full flex-col">
      <ReportContextHeader tab={tab} />
      <div className="min-h-0 flex-1 px-6 pb-6 lg:px-8">
        <IndustryReportView tab={tab} />
      </div>
    </div>
  );
}

function ReportContextHeader({ tab }: { tab: ReportTab }) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [collectedAt, setCollectedAt] = useState<string | null>(null);

  useEffect(() => {
    fetchReportStatus(token)
      .then((status) => setCollectedAt(status.collected_at))
      .catch(() => undefined);
  }, [token]);

  return (
    <header className="flex items-center gap-3 border-b border-app-border px-6 py-3 lg:px-8">
      <LibraryBig size={18} className="text-app-ink/50" />
      <div className="min-w-0">
        <div className="app-text-body-sm font-semibold text-app-ink">
          {t(`industryReport.tabs.${tab}`)}
        </div>
        <div className="app-text-caption text-app-ink/45">
          {collectedAt ? t('news.lastUpdated', { at: collectedAt }) : t('industryReport.subtitle')}
        </div>
      </div>
    </header>
  );
}
