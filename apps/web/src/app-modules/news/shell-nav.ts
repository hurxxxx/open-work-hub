import type { AppShellNavResolver } from '@/src/app/shell/navigation-types';
import { getShellSearchParams } from '@/src/app-shell-navigation-model';

export const newsShellNavResolver: AppShellNavResolver = ({
  manifest,
  path,
}) => {
  const params = getShellSearchParams(path);
  if (params.get('view') === 'report') {
    const tab = params.get('tab') || 'trend';
    if (tab === 'autojournal') return 'industry-report-autojournal';
    if (tab === 'kdi') return 'industry-report-kdi';
    if (tab === 'recommended') return 'industry-report-recommended';
    if (tab === 'ai') return 'industry-report-ai';
    if (tab === 'scraps') return 'industry-report-scraps';
    return 'industry-report-trend';
  }
  const channel = params.get('channel') || 'home';
  if (channel === 'home') return 'news-home';
  if (channel === 'recommended') return 'news-recommended';
  if (channel === 'keyword') return 'news-keyword';
  if (channel === 'car') return 'news-car';
  if (channel === 'front') return 'news-front';
  if (channel === 'ai') return 'news-ai';
  if (channel === 'scraps') return 'news-scraps';
  return manifest.defaultActiveNavItemId;
};
