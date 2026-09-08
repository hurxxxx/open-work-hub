import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import { REALTIME_TOPIC_EVENT_TYPES } from '@open-work-hub/contracts/realtime';
import { ChevronDown, ChevronRight, FileText } from 'lucide-react';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
import type { ReactNode } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  useRealtime,
  useRealtimeEvent,
} from '@/src/platform/realtime/realtime-provider';
import {
  listFavoriteDocs,
  listRecentPages,
  type FavoriteDocItem,
  type RecentPageItem,
} from './api/docs-api';
import { appendDocPageQuery } from './api/docs-url-state';
import {
  getInitialDocsSidebarExpandedSections,
  isDocsSidebarSectionExpanded,
  toggleDocsSidebarSection,
  type DocsSidebarSectionId,
} from './docs-sidebar-model';

type DocsSidebarExtrasProps = Record<string, never>;

interface DocsSidebarData {
  favorites: FavoriteDocItem[];
  recentPages: RecentPageItem[];
}

function DocsSidebarSection({
  children,
  expanded,
  id,
  title,
  onToggle,
}: {
  children: ReactNode;
  expanded: boolean;
  id: DocsSidebarSectionId;
  title: string;
  onToggle: (id: DocsSidebarSectionId) => void;
}) {
  const contentId = `docs-sidebar-section-${id}`;

  return (
    <div className="space-y-1 border-t border-app-border pt-2">
      <button
        type="button"
        aria-controls={contentId}
        aria-expanded={expanded}
        onClick={() => onToggle(id)}
        className="sidebar-section-label sidebar-section-header group/section flex w-full items-center gap-1 px-3 py-1"
      >
        {expanded ? (
          <ChevronDown
            size={11}
            className="text-app-ink/55 dark:text-app-ink/65 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
          />
        ) : (
          <ChevronRight
            size={11}
            className="text-app-ink/55 dark:text-app-ink/65 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
          />
        )}
        <span>{title}</span>
      </button>

      <LazyMotion features={domAnimation}>
        <AnimatePresence initial={false}>
          {expanded ? (
            <m.div
              id={contentId}
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              {children}
            </m.div>
          ) : null}
        </AnimatePresence>
      </LazyMotion>
    </div>
  );
}

export function DocsSidebarExtras(_context: DocsSidebarExtrasProps) {
  const { token } = useAuth();
  const { reconnectSeq } = useRealtime();
  const [accessRevision, setAccessRevision] = useState(0);
  useRealtimeEvent(REALTIME_TOPIC_EVENT_TYPES.docsAccessChanged, (event) => {
    const data = event.data as { doc_id?: unknown } | undefined;
    if (typeof data?.doc_id === 'string')
      setAccessRevision((revision) => revision + 1);
  });
  return (
    <DocsSidebarContent
      key={JSON.stringify([token, reconnectSeq, accessRevision])}
    />
  );
}

function DocsSidebarContent() {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const location = useLocation();
  const [sidebarData, setSidebarData] = useState<DocsSidebarData>({
    favorites: [],
    recentPages: [],
  });
  const [expandedSections, setExpandedSections] = useState<
    DocsSidebarSectionId[]
  >(getInitialDocsSidebarExpandedSections);
  const { favorites, recentPages } = sidebarData;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    Promise.all([
      listFavoriteDocs(token).catch(() => []),
      listRecentPages(token, 5).catch(() => []),
    ]).then(([nextFavorites, nextRecentPages]) => {
      if (cancelled) return;
      setSidebarData({
        favorites: nextFavorites,
        recentPages: nextRecentPages,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const toggleSection = useCallback((sectionId: DocsSidebarSectionId) => {
    setExpandedSections((current) =>
      toggleDocsSidebarSection(current, sectionId),
    );
  }, []);

  return (
    <div className="space-y-2">
      <DocsSidebarSection
        id="favorites"
        title={t('docs.sidebar.favorites')}
        expanded={isDocsSidebarSectionExpanded(expandedSections, 'favorites')}
        onToggle={toggleSection}
      >
        {favorites.length > 0 ? (
          favorites.map((favorite) => {
            const docPath = buildAppHref({
              routeId: 'docs.document',
              pathParams: { docId: favorite.id },
            });
            return (
              <Link
                key={favorite.id}
                to={docPath}
                className={cn(
                  'sidebar-submenu-item ml-1',
                  location.pathname === docPath &&
                    'sidebar-submenu-item-active',
                )}
              >
                <FileText size={14} className="text-yellow-500" />
                <span className="sidebar-submenu-label truncate">
                  {favorite.title}
                </span>
              </Link>
            );
          })
        ) : (
          <div className="px-3 py-2 text-center">
            <span className="app-text-micro text-app-ink/70">
              {t('docs.sidebar.noFavorites')}
            </span>
          </div>
        )}
      </DocsSidebarSection>

      <DocsSidebarSection
        id="recentPages"
        title={t('docs.sidebar.recentPages')}
        expanded={isDocsSidebarSectionExpanded(expandedSections, 'recentPages')}
        onToggle={toggleSection}
      >
        {recentPages.length > 0 ? (
          recentPages.map((recentPage) => {
            const docPathWithoutPage = buildAppHref({
              routeId: 'docs.document',
              pathParams: { docId: recentPage.doc_id },
            });
            const docPath = appendDocPageQuery(
              docPathWithoutPage,
              recentPage.page_id,
            );
            return (
              <Link
                key={recentPage.page_id}
                to={docPath}
                className="sidebar-submenu-item ml-1"
              >
                <FileText size={14} className="text-app-ink/55" />
                <span className="sidebar-submenu-label truncate">
                  {recentPage.page_title}
                </span>
              </Link>
            );
          })
        ) : (
          <div className="px-3 py-2 text-center">
            <span className="app-text-micro text-app-ink/70">
              {t('docs.sidebar.noRecentPages')}
            </span>
          </div>
        )}
      </DocsSidebarSection>
    </div>
  );
}
