import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, ExternalLink } from 'lucide-react';

import { fetchNewsArticle, type NewsArticle, type NewsArticleDetail } from '../api/news-api';

interface NewsArticleModalProps {
  token: string | null;
  article: NewsArticle;
  onClose: () => void;
}

export function NewsArticleModal({ token, article, onClose }: NewsArticleModalProps) {
  const { t } = useTranslation('apps');
  const [detail, setDetail] = useState<NewsArticleDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    setDetail(null);
    fetchNewsArticle(token, article.original_url)
      .then((data) => {
        if (active) setDetail(data);
      })
      .catch(() => {
        if (active) setFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, article.original_url]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const hasBody = !!detail?.full_text;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-app-border bg-app-surface">
        <header className="flex items-center justify-between gap-3 border-b border-app-border px-5 py-3">
          <h2 className="app-text-title line-clamp-1 text-app-ink">{article.title}</h2>
          <div className="flex shrink-0 items-center gap-2">
            {article.original_url && (
              <a
                href={article.original_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 rounded-md border border-app-accent px-2.5 py-1 app-text-caption text-app-accent"
              >
                <ExternalLink size={12} />
                {t('news.article.viewOriginal')}
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-app-border p-1 text-app-ink/60 hover:text-app-ink"
              aria-label={t('news.article.close')}
            >
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="py-8 text-center app-text-body-sm text-app-ink/50">
              {t('news.article.loading')}
            </div>
          ) : hasBody ? (
            <article className="flex flex-col gap-4">
              <p className="app-text-body whitespace-pre-wrap leading-relaxed text-app-ink">
                {detail?.full_text}
              </p>
              {detail?.images && detail.images.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {detail.images.map((image) => (
                    <img
                      key={image.url}
                      src={image.url}
                      alt={image.caption || ''}
                      className="max-w-[300px] rounded-md border border-app-border"
                      onError={(event) => event.currentTarget.remove()}
                    />
                  ))}
                </div>
              )}
            </article>
          ) : (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <p className="app-text-body-sm text-app-ink/60">{t('news.article.bodyUnavailable')}</p>
              {article.original_url && (
                <a
                  href={article.original_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-md bg-app-accent px-4 py-2 app-text-control text-app-accent-fg"
                >
                  {t('news.article.openOriginal')} ↗
                </a>
              )}
              {failed ? null : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
