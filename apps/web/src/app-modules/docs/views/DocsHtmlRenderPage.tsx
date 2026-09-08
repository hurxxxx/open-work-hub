import { AlertCircle, Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import {
  REALTIME_TOPIC_EVENT_TYPES,
  createDocsPagesRealtimeSubscriptionMessage,
} from '@open-work-hub/contracts/realtime';
import {
  useRealtimeEvent,
  useRealtimeSubscription,
  type RealtimeEvent,
} from '@/src/platform/realtime/realtime-provider';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { getDocsItem, listDocPages, resolveSharedLink } from '../api/docs-api';
import { DocsHtmlFrame } from './docs-html-renderers';
import {
  INITIAL_DOCS_HTML_RENDER_STATE,
  buildDocsHtmlRenderProjection,
  docsHtmlRenderReducer,
} from './docs-view-model';

export function DocsHtmlRenderPage() {
  const { token } = useAuth();
  const { docId, pageId, shareToken } = useParams();
  const [accessRevision, setAccessRevision] = useState(0);
  const invalidateAccess = useCallback(
    () => setAccessRevision((revision) => revision + 1),
    [],
  );
  return (
    <DocsHtmlRenderContent
      key={JSON.stringify([token, docId, pageId, shareToken, accessRevision])}
      invalidateAccess={invalidateAccess}
    />
  );
}

function DocsHtmlRenderContent({
  invalidateAccess,
}: {
  invalidateAccess: () => void;
}) {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { docId, pageId, shareToken } = useParams();
  const [{ doc, pages, loading, error }, dispatchRenderState] = useReducer(
    docsHtmlRenderReducer,
    INITIAL_DOCS_HTML_RENDER_STATE,
  );

  useEffect(() => {
    if (!token || (!docId && !shareToken)) return;
    let cancelled = false;
    dispatchRenderState({ type: 'loading' });
    const load = async () => {
      const itemId = shareToken
        ? (await resolveSharedLink(token, shareToken)).item.id
        : docId;
      if (!itemId) {
        throw new Error('DOC_ID_MISSING');
      }
      return Promise.all([
        getDocsItem(token, itemId, shareToken),
        listDocPages(token, itemId, shareToken),
      ]);
    };
    void load()
      .then(([nextDoc, pageList]) => {
        if (cancelled) return;
        dispatchRenderState({
          type: 'success',
          doc: nextDoc,
          pages: pageList.items,
        });
      })
      .catch(() => {
        if (!cancelled) {
          dispatchRenderState({
            type: 'failure',
            error: t('apps:docs.viewer.loadFailed'),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [docId, shareToken, t, token]);

  const activeDocId = doc?.id ?? docId;
  useRealtimeSubscription(
    doc?.id && token
      ? createDocsPagesRealtimeSubscriptionMessage({
          key: doc.id,
          shareToken,
        })
      : null,
  );
  useRealtimeEvent(
    REALTIME_TOPIC_EVENT_TYPES.docsAccessChanged,
    useCallback(
      (event: RealtimeEvent) => {
        const payload = event.data as { doc_id?: unknown } | undefined;
        if (activeDocId && payload?.doc_id === activeDocId) invalidateAccess();
      },
      [activeDocId, invalidateAccess],
    ),
  );

  const renderProjection = useMemo(
    () =>
      buildDocsHtmlRenderProjection({
        doc,
        pages,
        pageId,
        fallbackTitle: t('apps:docs.html.renderTitle'),
      }),
    [doc, pageId, pages, t],
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-app-bg text-app-ink/50">
        <Loader2 size={24} className="animate-spin" />
      </div>
    );
  }

  if (error || !renderProjection.canRender) {
    return (
      <div className="flex h-full items-center justify-center bg-app-bg px-5">
        <div className="flex max-w-md items-start gap-2 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/5 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{error ?? t('apps:docs.html.renderUnavailable')}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-hidden bg-white">
      <DocsHtmlFrame
        title={renderProjection.title}
        content={renderProjection.content}
      />
    </div>
  );
}
