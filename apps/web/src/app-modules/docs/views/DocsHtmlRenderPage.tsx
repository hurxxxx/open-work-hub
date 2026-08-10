import { useEffect, useMemo, useReducer } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AlertCircle, Loader2 } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getDocsItem,
  listDocPages,
  resolveSharedLink,
} from '../api/docs-api';
import { DocsHtmlFrame } from './docs-html-renderers';
import {
  INITIAL_DOCS_HTML_RENDER_STATE,
  buildDocsHtmlRenderProjection,
  docsHtmlRenderReducer,
} from './docs-view-model';

export function DocsHtmlRenderPage() {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const { docId, pageId, shareToken, workspaceSlug } = useParams();
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
        getDocsItem(token, itemId, shareToken, workspaceSlug),
        listDocPages(token, itemId, shareToken, workspaceSlug),
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
  }, [docId, shareToken, t, token, workspaceSlug]);

  const renderProjection = useMemo(
    () => buildDocsHtmlRenderProjection({
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
      <DocsHtmlFrame title={renderProjection.title} content={renderProjection.content} />
    </div>
  );
}
