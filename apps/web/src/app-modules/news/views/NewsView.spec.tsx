import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteNewsScrap,
  fetchAiProfile,
  fetchAiRecommended,
  fetchNewsChannel,
  fetchNewsFilterSettings,
  fetchNewsScraps,
  fetchRecommendedNews,
  recommendNews,
  scrapNews,
  saveAiProfile,
  saveNewsFilterSettings,
  searchNews,
  triggerCurate,
} from '../api/news-api';
import { NewsView } from './NewsView';

let adminAccess = true;

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    hasPermission: () => adminAccess,
    token: 'token',
  }),
}));

vi.mock('../api/news-api', () => ({
  deleteNewsScrap: vi.fn(),
  deleteRecommendedNews: vi.fn(),
  fetchAiProfile: vi.fn(),
  fetchAiRecommended: vi.fn(),
  fetchNewsArticle: vi.fn(),
  fetchNewsChannel: vi.fn(),
  fetchNewsFilterSettings: vi.fn(),
  fetchNewsScraps: vi.fn(),
  fetchRecommendedNews: vi.fn(),
  recommendNews: vi.fn(),
  saveAiProfile: vi.fn(),
  saveNewsFilterSettings: vi.fn(),
  searchNews: vi.fn(),
  scrapNews: vi.fn(),
  triggerCurate: vi.fn(),
}));

const keywordArticle = {
  date: '2026-07-01',
  keyword: '전기차',
  original_url: 'https://example.test/keyword',
  source: '조선일보',
  summary: '요약',
  title: 'Keyword article',
};

function renderNewsView(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/news" element={<NewsView />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('NewsView', () => {
  beforeEach(() => {
    adminAccess = true;
    vi.clearAllMocks();
    vi.mocked(fetchNewsChannel).mockResolvedValue({
      articles: [keywordArticle],
      channel: 'keyword',
      collected_at: '2026-07-01 09:00',
      has_next: false,
      page: 1,
      page_size: 50,
      status: 'success',
      total: 1,
      total_pages: 1,
    });
    vi.mocked(fetchRecommendedNews).mockResolvedValue({
      articles: [],
      status: 'success',
    });
    vi.mocked(fetchNewsScraps).mockResolvedValue({
      articles: [],
      status: 'success',
    });
    vi.mocked(fetchNewsFilterSettings).mockResolvedValue({
      car_filter: [],
      keyword_filter: [],
      keyword_ui_filters: [],
    });
    vi.mocked(searchNews).mockResolvedValue({
      articles: [],
      query: '',
      status: 'success',
    });
    vi.mocked(fetchAiRecommended).mockResolvedValue({
      articles: [],
      status: 'success',
    });
    vi.mocked(fetchAiProfile).mockResolvedValue({
      ai_curate_enabled: true,
      ai_curated_at: null,
      ai_profile: '',
      ai_profile_is_default: true,
    });
    vi.mocked(triggerCurate).mockResolvedValue({
      by_reason: {},
      error: null,
      evaluated: 0,
      saved: 0,
      status: 'success',
    });
    vi.mocked(saveAiProfile).mockResolvedValue({
      ai_curate_enabled: true,
      ai_curated_at: null,
      ai_profile: '',
      ai_profile_is_default: true,
    });
    vi.mocked(saveNewsFilterSettings).mockResolvedValue({
      car_filter: [],
      keyword_filter: [],
      keyword_ui_filters: [],
    });
    vi.mocked(scrapNews).mockResolvedValue({
      ...keywordArticle,
      id: 'scrap-1',
    });
    vi.mocked(recommendNews).mockResolvedValue({
      ...keywordArticle,
      id: 'recommended-1',
      channel: 'keyword',
      origin: 'manual',
      reason: '',
      reason_detail: '',
    });
    vi.mocked(deleteNewsScrap).mockResolvedValue({ status: 'deleted' });
  });

  it('restores personal scrap and admin recommend actions on keyword news', async () => {
    renderNewsView('/news?channel=keyword');

    await screen.findByText('Keyword article');

    fireEvent.click(screen.getByTitle('내 스크랩'));
    fireEvent.click(screen.getByTitle('추천'));

    await waitFor(() => {
      expect(scrapNews).toHaveBeenCalledWith(
        'token',
        keywordArticle,
        'keyword',
      );
      expect(recommendNews).toHaveBeenCalledWith(
        'token',
        keywordArticle,
        'keyword',
      );
    });
  });

  it('restores delete action on the personal news scraps tab', async () => {
    vi.mocked(fetchNewsScraps).mockResolvedValue({
      articles: [{ ...keywordArticle, id: 'scrap-1' }],
      status: 'success',
    });

    renderNewsView('/news?channel=scraps');

    await screen.findByText('Keyword article');
    fireEvent.click(screen.getByTitle('스크랩 해제'));

    await waitFor(() => {
      expect(deleteNewsScrap).toHaveBeenCalledWith('token', 'scrap-1');
    });
  });
});
