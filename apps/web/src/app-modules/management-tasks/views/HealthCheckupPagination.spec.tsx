import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';
import { HealthCheckupPagination } from './HealthCheckupPagination';

describe('HealthCheckupPagination', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('ko-KR');
  });

  it('interpolates the calculated page count in the summary', () => {
    render(
      <HealthCheckupPagination
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
        page={1}
        pageSize={25}
        total={51}
      />,
    );

    expect(screen.getByText('전체 51건 · 1 / 3 페이지')).toBeTruthy();
  });
});
