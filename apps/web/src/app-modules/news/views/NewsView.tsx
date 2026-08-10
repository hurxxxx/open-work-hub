import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import {
  Home,
  Newspaper,
  Search,
  RefreshCw,
  Plus,
  Settings2,
  X,
  Bookmark,
  Trash2,
  Sparkles,
  Star,
} from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  deleteNewsScrap,
  deleteRecommendedNews,
  fetchAiProfile,
  fetchAiRecommended,
  fetchNewsChannel,
  fetchNewsFilterSettings,
  fetchNewsScraps,
  fetchNewsStatus,
  fetchRecommendedNews,
  recommendNews,
  scrapNews,
  saveAiProfile,
  saveNewsFilterSettings,
  searchNews,
  triggerCurate,
  triggerNewsFetch,
  type NewsArticle,
  type NewsChannel,
  type NewsRecommendedArticle,
  type NewsScrapArticle,
} from '../api/news-api';
import { NewsArticleModal } from './NewsArticleModal';

// UI 채널 — 홈/실제 수집 채널 + 관리자/AI 추천(별도 엔드포인트)
type UiChannel = 'home' | NewsChannel | 'recommended' | 'ai' | 'scraps';
const UI_CHANNELS: UiChannel[] = [
  'home',
  'recommended',
  'keyword',
  'car',
  'front',
  'ai',
  'scraps',
];
const ARTICLE_SEARCH_CHANNELS: UiChannel[] = ['keyword', 'car', 'front'];
const DEFAULT_CHANNEL: UiChannel = 'home';
const HOME_SECTION_CHANNELS: NewsChannel[] = ['keyword', 'car', 'front'];

// AI 추천 사유 배지 스타일(사유 텍스트는 백엔드 데이터를 그대로 표시).
const REASON_BADGE_STYLE =
  'border-app-accent/40 bg-app-accent/10 text-app-accent';
type NewsDisplayArticle =
  | NewsArticle
  | NewsRecommendedArticle
  | NewsScrapArticle;

function resolveNewsChannel(value: string | null): UiChannel {
  return UI_CHANNELS.includes(value as UiChannel)
    ? (value as UiChannel)
    : DEFAULT_CHANNEL;
}

function getArticleChannel(
  article: NewsDisplayArticle,
  fallback: UiChannel,
): string {
  if ('channel' in article && article.channel) return article.channel;
  if (
    fallback === 'home' ||
    fallback === 'recommended' ||
    fallback === 'ai' ||
    fallback === 'scraps'
  ) {
    return '';
  }
  return fallback;
}

function resolveStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

export function NewsView() {
  const { t } = useTranslation('apps');
  const { token, hasPermission } = useAuth();
  const [searchParams] = useSearchParams();
  const isAdmin = hasPermission('admin.access');
  const channel = resolveNewsChannel(searchParams.get('channel'));
  const isHome = channel === 'home';
  const isRecommended = channel === 'recommended';
  const isAi = channel === 'ai';
  const isScraps = channel === 'scraps';
  const isSnapshotList = isHome || isRecommended || isAi || isScraps;
  const isArticleSearchable = ARTICLE_SEARCH_CHANNELS.includes(channel);

  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [recommendedArticles, setRecommendedArticles] = useState<
    NewsRecommendedArticle[]
  >([]);
  const [scrapArticles, setScrapArticles] = useState<NewsScrapArticle[]>([]);
  const [recommendedByUrl, setRecommendedByUrl] = useState<Map<string, string>>(
    () => new Map(),
  );
  const [scrapByUrl, setScrapByUrl] = useState<Map<string, string>>(
    () => new Map(),
  );
  const [savingUrl, setSavingUrl] = useState<string | null>(null);
  const [recommendingUrl, setRecommendingUrl] = useState<string | null>(null);
  const [collectedAt, setCollectedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState(false);

  const [keywordFilters, setKeywordFilters] = useState<string[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [newKeyword, setNewKeyword] = useState('');
  const [fetching, setFetching] = useState(false);

  // AI 추천 뉴스 — 큐레이션/프로필 편집 상태
  const [curating, setCurating] = useState(false);
  const [curateNote, setCurateNote] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileText, setProfileText] = useState('');
  const [profileEnabled, setProfileEnabled] = useState(true);
  const [curatedAt, setCuratedAt] = useState<string | null>(null);

  const [selected, setSelected] = useState<NewsArticle | null>(null);
  const loadRequestIdRef = useRef(0);
  const activeNewsViewRef = useRef({ channel });
  activeNewsViewRef.current = { channel };
  const frontFilters = useMemo(
    () => resolveStringArray(t('news.filters.front', { returnObjects: true })),
    [t],
  );
  const carFilters = useMemo(
    () => resolveStringArray(t('news.filters.car', { returnObjects: true })),
    [t],
  );

  const filterChips = useMemo(() => {
    if (channel === 'keyword') return keywordFilters;
    if (channel === 'front') return frontFilters;
    if (channel === 'car') return carFilters;
    return [];
  }, [carFilters, channel, frontFilters, keywordFilters]);

  const refreshRecommendations = useCallback(async () => {
    try {
      const data = await fetchRecommendedNews(token);
      setRecommendedByUrl(
        new Map(
          data.articles.map((article) => [article.original_url, article.id]),
        ),
      );
      return data.articles;
    } catch {
      return [] as NewsRecommendedArticle[];
    }
  }, [token]);

  const refreshScraps = useCallback(async () => {
    try {
      const data = await fetchNewsScraps(token);
      setScrapByUrl(
        new Map(
          data.articles.map((article) => [article.original_url, article.id]),
        ),
      );
      return data.articles;
    } catch {
      return [] as NewsScrapArticle[];
    }
  }, [token]);

  const loadChannel = useCallback(
    async (ch: UiChannel) => {
      const requestId = loadRequestIdRef.current + 1;
      loadRequestIdRef.current = requestId;
      setLoading(true);
      setError(null);
      setSearchMode(false);
      try {
        if (ch === 'home' || ch === 'recommended') {
          const data = await fetchRecommendedNews(token);
          if (requestId !== loadRequestIdRef.current) return;
          setRecommendedArticles(data.articles);
          setRecommendedByUrl(
            new Map(
              data.articles.map((article) => [
                article.original_url,
                article.id,
              ]),
            ),
          );
          setCollectedAt(null);
        } else if (ch === 'ai') {
          const data = await fetchAiRecommended(token);
          if (requestId !== loadRequestIdRef.current) return;
          setRecommendedArticles(data.articles);
          setCollectedAt(null);
        } else if (ch === 'scraps') {
          const data = await fetchNewsScraps(token);
          if (requestId !== loadRequestIdRef.current) return;
          setScrapArticles(data.articles);
          setScrapByUrl(
            new Map(
              data.articles.map((article) => [
                article.original_url,
                article.id,
              ]),
            ),
          );
          setCollectedAt(null);
        } else {
          const data = await fetchNewsChannel(token, ch);
          if (requestId !== loadRequestIdRef.current) return;
          setArticles(data.articles);
          setCollectedAt(data.collected_at);
        }
      } catch {
        if (requestId === loadRequestIdRef.current) {
          setError(t('news.errors.loadFailed'));
          setArticles([]);
        }
      } finally {
        if (requestId === loadRequestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [token, t],
  );
  const loadChannelRef = useRef(loadChannel);
  loadChannelRef.current = loadChannel;

  useEffect(() => {
    void loadChannel(channel);
  }, [channel, loadChannel]);

  // 채널 보기에서 추천/스크랩 여부를 표시하기 위한 URL 집합.
  useEffect(() => {
    void refreshRecommendations();
    void refreshScraps();
  }, [refreshRecommendations, refreshScraps]);

  useEffect(() => {
    fetchNewsFilterSettings(token)
      .then((settings) => setKeywordFilters(settings.keyword_ui_filters ?? []))
      .catch(() => undefined);
  }, [token]);

  // AI 탭 진입 시 프로필/마지막 분석 시각 로드.
  useEffect(() => {
    if (!isAi) return;
    fetchAiProfile(token)
      .then((p) => {
        setProfileText(p.ai_profile);
        setProfileEnabled(p.ai_curate_enabled);
        setCuratedAt(p.ai_curated_at);
      })
      .catch(() => undefined);
  }, [isAi, token]);

  useEffect(() => {
    setActiveFilter(null);
    setEditorOpen(false);
    setProfileOpen(false);
    setCurateNote(null);
    setSelected(null);
  }, [channel]);

  const handleSearch = async () => {
    const query = searchQuery.trim();
    if (!query) return;
    setLoading(true);
    setError(null);
    setActiveFilter(null);
    try {
      const data = await searchNews(token, query);
      setArticles(data.articles);
      setSearchMode(true);
    } catch {
      setError(t('news.errors.searchFailed'));
      setArticles([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFetch = async () => {
    setFetching(true);
    try {
      const before =
        (await fetchNewsStatus(token).catch(() => null))?.collected_at ?? null;
      await triggerNewsFetch(token);
      // 수집은 워커에서 비동기로 도므로, 완료(collected_at 갱신)될 때까지 폴링 후 자동 새로고침.
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const status = await fetchNewsStatus(token).catch(() => null);
        if (status?.collected_at && status.collected_at !== before) break;
      }
    } catch {
      // best-effort; collection runs in the background worker
    } finally {
      const activeView = activeNewsViewRef.current;
      await loadChannelRef.current(activeView.channel);
      await refreshRecommendations();
      await refreshScraps();
      setFetching(false);
    }
  };

  const handleCurate = async () => {
    setCurating(true);
    setCurateNote(null);
    try {
      const result = await triggerCurate(token);
      if (result.error) {
        setCurateNote(t('news.ai.analyzeFailed', { error: result.error }));
      } else {
        setCurateNote(
          t('news.ai.result', {
            evaluated: result.evaluated,
            saved: result.saved,
          }),
        );
      }
      const data = await fetchAiRecommended(token);
      setRecommendedArticles(data.articles);
      const p = await fetchAiProfile(token);
      setCuratedAt(p.ai_curated_at);
    } catch {
      setCurateNote(t('news.ai.requestFailed'));
    } finally {
      setCurating(false);
    }
  };

  const handleSaveProfile = async () => {
    try {
      const p = await saveAiProfile(token, {
        ai_profile: profileText,
        ai_curate_enabled: profileEnabled,
      });
      setProfileText(p.ai_profile);
      setProfileEnabled(p.ai_curate_enabled);
      setProfileOpen(false);
    } catch {
      setError(t('news.errors.saveFailed'));
    }
  };

  const handleRecommend = async (article: NewsArticle) => {
    setRecommendingUrl(article.original_url);
    try {
      const saved = await recommendNews(
        token,
        article,
        getArticleChannel(article, channel),
      );
      setRecommendedByUrl((prev) => {
        const next = new Map(prev);
        next.set(saved.original_url, saved.id);
        return next;
      });
    } catch {
      setError(t('news.errors.saveFailed'));
    } finally {
      setRecommendingUrl(null);
    }
  };

  const handleScrap = async (article: NewsDisplayArticle) => {
    setSavingUrl(article.original_url);
    try {
      const saved = await scrapNews(
        token,
        article,
        getArticleChannel(article, channel),
      );
      setScrapByUrl((prev) => {
        const next = new Map(prev);
        next.set(saved.original_url, saved.id);
        return next;
      });
    } catch {
      setError(t('news.errors.saveFailed'));
    } finally {
      setSavingUrl(null);
    }
  };

  const handleDeleteRecommended = async (id: string, url: string) => {
    try {
      await deleteRecommendedNews(token, id);
      setRecommendedArticles((prev) => prev.filter((a) => a.id !== id));
      setRecommendedByUrl((prev) => {
        const next = new Map(prev);
        next.delete(url);
        return next;
      });
    } catch {
      setError(t('news.errors.saveFailed'));
    }
  };

  const handleDeleteScrap = async (id: string, url: string) => {
    try {
      await deleteNewsScrap(token, id);
      setScrapArticles((prev) => prev.filter((a) => a.id !== id));
      setScrapByUrl((prev) => {
        const next = new Map(prev);
        next.delete(url);
        return next;
      });
    } catch {
      setError(t('news.errors.saveFailed'));
    }
  };

  const handleAddKeyword = () => {
    const value = newKeyword.trim();
    if (!value || keywordFilters.includes(value)) {
      setNewKeyword('');
      return;
    }
    setKeywordFilters((prev) => [...prev, value]);
    setNewKeyword('');
  };

  const handleRemoveKeyword = (index: number) => {
    setKeywordFilters((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveKeywords = async () => {
    try {
      await saveNewsFilterSettings(token, {
        keyword_ui_filters: keywordFilters,
      });
      setEditorOpen(false);
    } catch {
      setError(t('news.errors.saveFailed'));
    }
  };

  const handleOpenArticle = (article: NewsDisplayArticle) => {
    setSelected(article);
  };

  const getRecommendedChannelLabel = useCallback(
    (newsChannel: string) => {
      if (newsChannel === 'keyword') return t('news.tabs.keyword');
      if (newsChannel === 'car') return t('news.tabs.car');
      if (newsChannel === 'front') return t('news.tabs.front');
      return newsChannel;
    },
    [t],
  );

  const homeLeadArticle = recommendedArticles[0];
  const homeSecondaryArticles = recommendedArticles.slice(1, 4);
  const homeSections = useMemo(
    () =>
      HOME_SECTION_CHANNELS.map((sectionChannel) => ({
        channel: sectionChannel,
        title: getRecommendedChannelLabel(sectionChannel),
        articles: recommendedArticles
          .filter((article) => article.channel === sectionChannel)
          .slice(0, 5),
      })).filter((section) => section.articles.length > 0),
    [getRecommendedChannelLabel, recommendedArticles],
  );

  const visibleArticles = useMemo<NewsDisplayArticle[]>(() => {
    const base: NewsDisplayArticle[] = isScraps
      ? scrapArticles
      : isHome || isRecommended || isAi
        ? recommendedArticles
        : searchMode
          ? articles
          : articles.slice(0, 50);
    if (!activeFilter) return base;
    return base.filter(
      (article) =>
        article.title.includes(activeFilter) ||
        article.source.includes(activeFilter) ||
        article.keyword.includes(activeFilter),
    );
  }, [
    activeFilter,
    articles,
    isHome,
    isRecommended,
    isAi,
    isScraps,
    recommendedArticles,
    scrapArticles,
    searchMode,
  ]);

  const channelLabel = t(`news.tabs.${channel}`);

  const subtitle = isHome
    ? t('news.home.subtitle')
    : isRecommended
      ? t('news.recommended.subtitle')
      : isAi
        ? t('news.ai.subtitle')
        : isScraps
          ? t('news.scraps.subtitle')
          : t('news.subtitle');

  return (
    <div className="mx-auto flex h-full w-full max-w-5xl flex-col gap-4 p-6 lg:p-8">
      <header className="flex flex-col gap-1">
        <div className="flex items-center gap-2 text-app-ink/60">
          {isHome ? (
            <Home size={18} />
          ) : isRecommended ? (
            <Star size={18} />
          ) : isScraps ? (
            <Bookmark size={18} />
          ) : isAi ? (
            <Sparkles size={18} />
          ) : (
            <Newspaper size={18} />
          )}
          <span className="app-text-overline">{channelLabel}</span>
          {!isSnapshotList && !searchMode && collectedAt && (
            <span className="app-text-caption text-app-ink/45">
              · {t('news.lastUpdated', { at: collectedAt })}
            </span>
          )}
          {isAi && curatedAt && (
            <span className="app-text-caption text-app-ink/45">
              · {t('news.ai.lastAnalyzed', { at: curatedAt })}
            </span>
          )}
        </div>
        <p className="app-text-body-sm text-app-ink/70">{subtitle}</p>
      </header>

      {/* Filter chips + admin keyword editor toggle */}
      {filterChips.length > 0 || (isAdmin && channel === 'keyword') ? (
        <div className="flex flex-wrap items-center gap-2">
          {filterChips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() =>
                setActiveFilter((current) => (current === chip ? null : chip))
              }
              className={`rounded-full border px-3 py-1 app-text-caption transition-colors ${
                activeFilter === chip
                  ? 'border-app-accent bg-app-accent/10 text-app-accent'
                  : 'border-app-border bg-app-surface text-app-ink/80 hover:border-app-accent'
              }`}
            >
              {chip}
            </button>
          ))}
          {isAdmin && channel === 'keyword' && (
            <button
              type="button"
              onClick={() => setEditorOpen((open) => !open)}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-app-border px-3 py-1 app-text-caption text-app-ink/60 hover:border-app-accent"
            >
              <Settings2 size={12} />
              {t('news.admin.manageKeywords')}
            </button>
          )}
        </div>
      ) : null}

      {/* Admin keyword editor */}
      {isAdmin && editorOpen && channel === 'keyword' && (
        <div className="rounded-lg border border-app-border bg-app-surface p-3">
          <div className="mb-2 app-text-caption font-semibold text-app-ink">
            {t('news.admin.keywordPanelTitle')}
          </div>
          <div className="mb-2 flex flex-wrap gap-2">
            {keywordFilters.map((keyword, index) => (
              <span
                key={keyword}
                className="inline-flex items-center gap-1 rounded-full border border-app-border bg-app-surface-muted px-3 py-1 app-text-caption text-app-ink"
              >
                {keyword}
                <button
                  type="button"
                  onClick={() => handleRemoveKeyword(index)}
                  aria-label={t('news.admin.remove')}
                >
                  <X size={12} className="text-app-ink/50 hover:text-app-ink" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              value={newKeyword}
              onChange={(event) => setNewKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') handleAddKeyword();
              }}
              placeholder={t('news.admin.newKeywordPlaceholder')}
              className="flex-1 rounded-md border border-app-border bg-app-surface px-3 py-1.5 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
            />
            <button
              type="button"
              onClick={handleAddKeyword}
              className="flex items-center gap-1 rounded-md bg-app-accent px-3 py-1.5 app-text-control text-app-accent-fg"
            >
              <Plus size={14} />
              {t('news.admin.add')}
            </button>
            <button
              type="button"
              onClick={handleSaveKeywords}
              className="rounded-md border border-app-border px-3 py-1.5 app-text-control text-app-ink hover:border-app-accent"
            >
              {t('news.admin.save')}
            </button>
          </div>
        </div>
      )}

      {/* AI 추천 뉴스 — 관리자 컨트롤(수동 분석 + 프로필 편집) */}
      {isAi && isAdmin && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleCurate()}
              disabled={curating}
              className="flex items-center gap-1 rounded-md bg-app-accent px-3 py-2 app-text-control text-app-accent-fg disabled:opacity-60"
            >
              <Sparkles size={14} className={curating ? 'animate-pulse' : ''} />
              {curating ? t('news.ai.curating') : t('news.ai.curateNow')}
            </button>
            <button
              type="button"
              onClick={() => setProfileOpen((open) => !open)}
              className="inline-flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control text-app-ink/70 hover:border-app-accent"
            >
              <Settings2 size={14} />
              {t('news.ai.editProfile')}
            </button>
            {curateNote && (
              <span className="app-text-caption text-app-ink/55">
                {curateNote}
              </span>
            )}
          </div>
          {profileOpen && (
            <div className="rounded-lg border border-app-border bg-app-surface p-3">
              <label className="mb-1 flex items-center gap-2 app-text-caption text-app-ink/70">
                <input
                  type="checkbox"
                  checked={profileEnabled}
                  onChange={(e) => setProfileEnabled(e.target.checked)}
                />
                {t('news.ai.autoEnabled')}
              </label>
              <textarea
                value={profileText}
                onChange={(e) => setProfileText(e.target.value)}
                rows={10}
                className="mt-1 w-full rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => void handleSaveProfile()}
                  className="rounded-md bg-app-accent px-3 py-1.5 app-text-control text-app-accent-fg"
                >
                  {t('news.ai.saveProfile')}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Search + admin fetch (snapshot tabs hide search) */}
      {!isSnapshotList && (
        <div className="flex flex-wrap items-center gap-2">
          {isArticleSearchable ? (
            <div className="flex flex-1 gap-2">
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void handleSearch();
                }}
                placeholder={t('news.searchPlaceholder')}
                className="flex-1 rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent"
              />
              <button
                type="button"
                onClick={() => void handleSearch()}
                className="flex items-center gap-1 rounded-md bg-app-accent px-4 py-2 app-text-control text-app-accent-fg"
              >
                <Search size={14} />
                {t('news.search')}
              </button>
            </div>
          ) : (
            <div className="flex-1" />
          )}
          {isAdmin && (
            <button
              type="button"
              onClick={() => void handleFetch()}
              disabled={fetching}
              className="flex items-center gap-1 rounded-md border border-app-border px-3 py-2 app-text-control text-app-ink/70 hover:border-app-accent disabled:opacity-60"
            >
              <RefreshCw size={14} className={fetching ? 'animate-spin' : ''} />
              {fetching ? t('news.admin.fetching') : t('news.admin.fetch')}
            </button>
          )}
        </div>
      )}

      {/* Article list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="py-16 text-center app-text-body-sm text-app-ink/50">
            {t('news.loading')}
          </div>
        ) : error ? (
          <div className="py-16 text-center app-text-body-sm text-app-ink/50">
            {error}
          </div>
        ) : isHome ? (
          recommendedArticles.length === 0 ? (
            <div className="py-16 text-center app-text-body-sm text-app-ink/50">
              {t('news.empty.home')}
            </div>
          ) : (
            <div className="space-y-8 pb-8">
              {homeLeadArticle ? (
                <section className="grid gap-4 border-y border-app-border py-4 lg:grid-cols-[minmax(0,1.45fr)_minmax(260px,0.85fr)]">
                  <button
                    type="button"
                    onClick={() => handleOpenArticle(homeLeadArticle)}
                    className="min-w-0 rounded-md border border-app-border bg-app-surface p-5 text-left transition-colors hover:border-app-accent"
                  >
                    <span className="app-text-overline text-app-accent">
                      {t('news.home.topStories')}
                    </span>
                    <span className="mt-3 block app-text-heading-md text-app-ink line-clamp-3">
                      {homeLeadArticle.title}
                    </span>
                    {homeLeadArticle.summary ? (
                      <span className="mt-3 block app-text-body-sm text-app-ink/65 line-clamp-3">
                        {homeLeadArticle.summary}
                      </span>
                    ) : null}
                    <span className="mt-4 flex flex-wrap gap-2 app-text-caption text-app-ink/50">
                      <span>
                        {getRecommendedChannelLabel(homeLeadArticle.channel)}
                      </span>
                      {homeLeadArticle.source ? (
                        <span>{homeLeadArticle.source}</span>
                      ) : null}
                      {homeLeadArticle.date ? (
                        <span>{homeLeadArticle.date}</span>
                      ) : null}
                    </span>
                  </button>

                  <div className="min-w-0 border-t border-app-border pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
                    <div className="mb-2 app-text-overline text-app-ink/55">
                      {t('news.home.sideHeader')}
                    </div>
                    <div className="flex flex-col">
                      {homeSecondaryArticles.map((article) => (
                        <button
                          key={article.id}
                          type="button"
                          onClick={() => handleOpenArticle(article)}
                          className="border-t border-app-border py-3 text-left first:border-t-0"
                        >
                          <span className="app-text-caption text-app-ink/45">
                            {getRecommendedChannelLabel(article.channel)}
                          </span>
                          <span className="mt-1 block app-text-body-sm font-medium text-app-ink line-clamp-2">
                            {article.title}
                          </span>
                          <span className="mt-1 block app-text-caption text-app-ink/50 line-clamp-1">
                            {article.source}
                            {article.date ? ` · ${article.date}` : ''}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>
              ) : null}

              {homeSections.length > 0 ? (
                <section>
                  <div className="mb-3 flex items-center justify-between border-b border-app-border pb-2">
                    <h2 className="app-text-heading-sm text-app-ink">
                      {t('news.home.sectionsTitle')}
                    </h2>
                  </div>
                  <div className="grid gap-x-6 gap-y-8 md:grid-cols-2">
                    {homeSections.map((section) => (
                      <section key={section.channel} className="min-w-0">
                        <div className="mb-2 flex items-center justify-between border-b border-app-border pb-2">
                          <h3 className="app-text-overline text-app-ink/65">
                            {section.title}
                          </h3>
                          <span className="app-text-caption text-app-ink/40">
                            {section.articles.length}
                          </span>
                        </div>
                        <div className="flex flex-col">
                          {section.articles.map((article, index) => (
                            <button
                              key={article.id}
                              type="button"
                              onClick={() => handleOpenArticle(article)}
                              className="border-b border-app-border py-3 text-left last:border-b-0"
                            >
                              <span
                                className={
                                  index === 0
                                    ? 'app-text-body-sm font-semibold text-app-ink line-clamp-2'
                                    : 'app-text-body-sm text-app-ink line-clamp-2'
                                }
                              >
                                {article.title}
                              </span>
                              <span className="mt-1 flex flex-wrap gap-2 app-text-caption text-app-ink/50">
                                {article.source ? (
                                  <span>{article.source}</span>
                                ) : null}
                                {article.date ? (
                                  <span>{article.date}</span>
                                ) : null}
                              </span>
                            </button>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                </section>
              ) : null}
            </div>
          )
        ) : visibleArticles.length === 0 ? (
          <div className="py-16 text-center app-text-body-sm text-app-ink/50">
            {isRecommended
              ? t('news.empty.recommended')
              : isAi
                ? t('news.empty.ai')
                : isScraps
                  ? t('news.empty.scraps')
                  : searchMode
                    ? t('news.empty.search')
                    : t('news.empty.list')}
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {visibleArticles.map((article) => {
              const recommendedRow =
                isRecommended || isAi
                  ? (article as NewsRecommendedArticle)
                  : undefined;
              const recommendedId =
                recommendedByUrl.get(article.original_url) ??
                recommendedRow?.id;
              const recommended = Boolean(recommendedId);
              const scrapRow = isScraps
                ? (article as NewsScrapArticle)
                : undefined;
              const scrapId =
                scrapByUrl.get(article.original_url) ?? scrapRow?.id;
              const scrapped = Boolean(scrapId);
              return (
                <li
                  key={article.original_url || article.title}
                  className="flex items-stretch gap-2 rounded-md border border-app-border bg-app-surface transition-colors hover:border-app-accent"
                >
                  <button
                    type="button"
                    onClick={() => handleOpenArticle(article)}
                    className="flex min-w-0 flex-1 flex-col gap-1 p-3 text-left"
                  >
                    <span className="flex items-center gap-2">
                      {isAi && recommendedRow?.reason && (
                        <span
                          className={`shrink-0 rounded-full border px-2 py-0.5 app-text-caption ${REASON_BADGE_STYLE}`}
                        >
                          {recommendedRow.reason}
                        </span>
                      )}
                      <span className="app-text-body-sm font-medium text-app-ink line-clamp-1">
                        {article.title}
                      </span>
                    </span>
                    {isAi && recommendedRow?.reason_detail && (
                      <span className="app-text-caption text-app-ink/55 line-clamp-1">
                        {recommendedRow.reason_detail}
                      </span>
                    )}
                    <span className="flex gap-2 app-text-caption text-app-ink/50">
                      {article.source ? <span>{article.source}</span> : null}
                      {article.date ? <span>{article.date}</span> : null}
                    </span>
                  </button>
                  <div className="flex shrink-0 items-center gap-1 pr-2">
                    {isScraps ? (
                      <button
                        type="button"
                        onClick={() =>
                          scrapId &&
                          void handleDeleteScrap(scrapId, article.original_url)
                        }
                        title={t('news.actions.removeScrap')}
                        aria-label={t('news.actions.removeScrap')}
                        className="rounded-md p-2 text-app-ink/40 transition-colors hover:bg-ui-danger/10 hover:text-ui-danger"
                      >
                        <Trash2 size={16} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => !scrapped && void handleScrap(article)}
                        disabled={
                          scrapped || savingUrl === article.original_url
                        }
                        title={
                          scrapped
                            ? t('news.actions.scrapped')
                            : t('news.actions.scrap')
                        }
                        aria-label={
                          scrapped
                            ? t('news.actions.scrapped')
                            : t('news.actions.scrap')
                        }
                        className={`rounded-md p-2 transition-colors ${
                          scrapped
                            ? 'text-app-accent'
                            : 'text-app-ink/40 hover:bg-app-accent/10 hover:text-app-accent'
                        }`}
                      >
                        <Bookmark
                          size={16}
                          fill={scrapped ? 'currentColor' : 'none'}
                        />
                      </button>
                    )}
                    {isAdmin ? (
                      recommendedRow ? (
                        <button
                          type="button"
                          onClick={() =>
                            recommendedRow &&
                            void handleDeleteRecommended(
                              recommendedRow.id,
                              article.original_url,
                            )
                          }
                          title={t('news.actions.removeRecommended')}
                          aria-label={t('news.actions.removeRecommended')}
                          className="rounded-md p-2 text-app-ink/40 transition-colors hover:bg-ui-danger/10 hover:text-ui-danger"
                        >
                          <Trash2 size={16} />
                        </button>
                      ) : !isScraps ? (
                        <button
                          type="button"
                          onClick={() =>
                            !recommended && void handleRecommend(article)
                          }
                          disabled={
                            recommended ||
                            recommendingUrl === article.original_url
                          }
                          title={
                            recommended
                              ? t('news.actions.recommended')
                              : t('news.actions.recommend')
                          }
                          aria-label={
                            recommended
                              ? t('news.actions.recommended')
                              : t('news.actions.recommend')
                          }
                          className={`rounded-md p-2 transition-colors ${
                            recommended
                              ? 'text-app-warning'
                              : 'text-app-ink/40 hover:bg-app-warning/10 hover:text-app-warning'
                          }`}
                        >
                          <Star
                            size={16}
                            fill={recommended ? 'currentColor' : 'none'}
                          />
                        </button>
                      ) : null
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {selected && (
        <NewsArticleModal
          token={token}
          article={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
