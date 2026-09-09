import { FileText } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import {
  DocsEmbeddedViewer,
  listDocsHub,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { buildPmsSpaceDocsToolPath } from './pms-view-route';
import {
  PmsCenteredLoadingState,
  PmsCenteredStateBlock,
} from './PmsCenteredStateBlock';
import { PmsSpaceToolTabs } from './PmsSpaceToolTabs';

export const SpaceDocsView = ({
  spaceId,
  spaceName,
  docId,
}: {
  spaceId: string;
  spaceName?: string | null;
  docId?: string | null;
}) => {
  if (docId) {
    return (
      <div className="flex h-full min-w-0 flex-col bg-app-bg">
        <div className="border-b border-app-border bg-app-bg px-4 pt-3 lg:px-5">
          <PmsSpaceToolTabs activeTab="docs" spaceId={spaceId} />
        </div>
        <DocsEmbeddedViewer itemId={docId} className="min-h-0 flex-1" />
      </div>
    );
  }

  return <SpaceDocsIndex spaceId={spaceId} spaceName={spaceName} />;
};

function SpaceDocsIndex({
  spaceId,
  spaceName,
}: {
  spaceId: string;
  spaceName?: string | null;
}) {
  const { t } = useTranslation('apps');
  const navigate = useNavigate();
  const { token } = useAuth();
  const [docs, setDocs] = useState<DocsHubItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setDocs([]);
      setLoading(false);
      setError(null);
      return undefined;
    }

    setLoading(true);
    setError(null);
    listDocsHub(token, {
      view: 'all',
      space_id: spaceId,
      page_size: 200,
      sort_by: 'target_sort_order',
      sort_dir: 'asc',
    })
      .then((response) => {
        if (cancelled) return;
        setDocs(response.items);
      })
      .catch(() => {
        if (!cancelled) {
          setError(t('docs.viewer.loadFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [spaceId, t, token]);

  const title = spaceName
    ? `${spaceName} · ${t('pms.spaceOverview.docs')}`
    : t('pms.spaceOverview.docs');

  return (
    <div className="flex h-full min-w-0 flex-col bg-app-bg">
      <header className="border-b border-app-border bg-app-bg px-4 pt-3 lg:px-5">
        <div className="min-w-0">
          <h1 className="app-text-title-sm truncate text-app-ink">{title}</h1>
          <p className="app-text-caption text-app-ink/45">
            {t('docs.documentCount', { count: docs.length })}
          </p>
        </div>
        <PmsSpaceToolTabs activeTab="docs" className="mt-3" spaceId={spaceId} />
      </header>

      {loading ? (
        <PmsCenteredLoadingState minHeightClassName="h-full" />
      ) : error ? (
        <PmsCenteredStateBlock minHeightClassName="h-full" tone="danger">
          {error}
        </PmsCenteredStateBlock>
      ) : docs.length === 0 ? (
        <PmsCenteredStateBlock minHeightClassName="h-full">
          {t('pms.spaceOverview.noDocCollections')}
        </PmsCenteredStateBlock>
      ) : (
        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-4">
          <div className="mx-auto grid w-full max-w-4xl gap-1">
            {docs.map((doc) => (
              <button
                key={doc.id}
                type="button"
                onClick={() =>
                  navigate(
                    buildPmsSpaceDocsToolPath({
                      docId: doc.id,
                      spaceId,
                    }),
                  )
                }
                className="flex min-w-0 items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-app-surface-hover"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded bg-app-surface-sidebar text-sky-500">
                  <FileText size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="app-text-body-sm block truncate text-app-ink">
                    {doc.title || t('docs.untitled')}
                  </span>
                  <span className="app-text-caption block truncate text-app-ink/45">
                    {doc.location_label}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
