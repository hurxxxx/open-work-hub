import { render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { resources } from '@/src/platform/i18n/resources';
import { RetrievalSearchView } from './RetrievalSearchView';

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-session', logout: vi.fn() }),
}));

vi.mock('@/src/platform/retrieval/retrieval-api', () => ({
  listRetrievalSources: vi.fn().mockResolvedValue({ sources: [] }),
  queryRetrieval: vi.fn(),
}));

describe('RetrievalSearchView company context', () => {
  it.each([
    ['ko-KR', '회사 콘텐츠를 현재 접근 권한에 따라 검색합니다.'],
    ['en-US', 'Search Company content allowed by your current access.'],
  ])(
    'renders the complete %s subtitle with the real catalog',
    async (locale, subtitle) => {
      const i18n = createInstance();
      await i18n.init({
        lng: locale,
        resources,
        defaultNS: 'common',
        interpolation: { escapeValue: false },
      });

      render(
        <I18nextProvider i18n={i18n}>
          <MemoryRouter>
            <RetrievalSearchView />
          </MemoryRouter>
        </I18nextProvider>,
      );

      expect(await screen.findByText(subtitle)).toBeTruthy();
      expect(screen.queryByText(/\{\{/)).toBeNull();
    },
  );
});
