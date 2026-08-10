import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearCatalog,
  exportInvoicesXlsx,
  extractInvoices,
  fetchCatalogInfo,
  fetchCorrections,
  saveCorrections,
} from '../api/meal-invoice-ocr-api';
import { MealInvoiceOcrView } from './MealInvoiceOcrView';

const workspaceState = vi.hoisted(() => ({ slug: 'workspace-a' }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count === undefined ? key : `${key}:${options.count}`,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: null }),
}));

vi.mock('@/src/platform/workspaces/workspace-bootstrap-context', () => ({
  useWorkspaceBootstrapContext: () => ({
    data: { workspace: { slug: workspaceState.slug } },
  }),
}));

vi.mock('@/src/platform/browser/browser-download', () => ({
  downloadBlobAsFile: vi.fn(),
}));

vi.mock('../api/meal-invoice-ocr-api', () => ({
  clearCatalog: vi.fn(),
  clearCorrections: vi.fn(),
  deleteCorrection: vi.fn(),
  exportInvoicesXlsx: vi.fn(),
  extractInvoices: vi.fn(),
  fetchCatalogInfo: vi.fn(),
  fetchCorrectionImage: vi.fn(),
  fetchCorrections: vi.fn(),
  saveCorrections: vi.fn(),
  uploadCatalog: vi.fn(),
}));

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('MealInvoiceOcrView workspace lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.slug = 'workspace-a';
  });

  it('clears A documents and ignores delayed A metadata after switching to B', async () => {
    const catalogA = deferred<{ items: number }>();
    const correctionsA = deferred<{ items: unknown[] }>();

    vi.mocked(fetchCatalogInfo).mockImplementation(({ workspaceSlug }) =>
      workspaceSlug === 'workspace-a'
        ? catalogA.promise
        : Promise.resolve({ items: 2 }),
    );
    vi.mocked(fetchCorrections).mockImplementation(({ workspaceSlug }) =>
      workspaceSlug === 'workspace-a'
        ? correctionsA.promise
        : Promise.resolve({ items: [] }),
    );
    vi.mocked(extractInvoices).mockResolvedValue({
      warnings: [],
      documents: [
        {
          원본파일: 'workspace-a.pdf',
          페이지: 1,
          거래처: 'A vendor',
          거래일: '',
          합계금액: '',
          공급가액: '',
          페이지이미지: '',
          품목: [
            {
              품명: 'A-only-item',
              규격: '',
              수량: '1 ea',
              단가: '',
              금액: '',
              원산지: '국내산',
              신선도: 'O',
              불량여부: '-',
              반품여부: '-',
              비고: '',
            },
          ],
        },
      ],
    });

    const rendered = render(<MealInvoiceOcrView />);
    const fileInput = document.querySelector<HTMLInputElement>(
      'input[type="file"][accept*=".pdf"]',
    );
    if (!fileInput) throw new Error('invoice file input not found');
    fireEvent.change(fileInput, {
      target: {
        files: [new File(['invoice'], 'a.pdf', { type: 'application/pdf' })],
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.extract',
      }),
    );

    expect(await screen.findByDisplayValue('A-only-item')).not.toBeNull();
    fireEvent.click(
      screen.getByRole('button', { name: 'apps:mealInvoiceOcr.manage.open' }),
    );
    await waitFor(() =>
      expect(fetchCorrections).toHaveBeenCalledWith({
        token: 'token',
        workspaceSlug: 'workspace-a',
      }),
    );

    workspaceState.slug = 'workspace-b';
    rendered.rerender(<MealInvoiceOcrView />);

    await waitFor(() => {
      expect(screen.queryByDisplayValue('A-only-item')).toBeNull();
      expect(
        (
          screen.getByRole('button', {
            name: 'apps:mealInvoiceOcr.actions.export',
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
      expect(
        (
          screen.getByRole('button', {
            name: 'apps:mealInvoiceOcr.actions.save:0',
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true);
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'apps:mealInvoiceOcr.manage.open' }),
    );
    expect(
      await screen.findByText('apps:mealInvoiceOcr.catalog.count:2'),
    ).not.toBeNull();

    await act(async () => {
      catalogA.resolve({ items: 99 });
      correctionsA.resolve({
        items: [{ id: 'a-record', 교정: { 품명: 'A-correction' } }],
      });
      await Promise.resolve();
    });

    expect(
      screen.getByText('apps:mealInvoiceOcr.catalog.count:2'),
    ).not.toBeNull();
    expect(
      screen.queryByText('apps:mealInvoiceOcr.catalog.count:99'),
    ).toBeNull();
    expect(screen.queryByText('A-correction')).toBeNull();
  });

  it('ignores a delayed A catalog clear after B metadata is loaded', async () => {
    const clearA = deferred<void>();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(fetchCatalogInfo).mockImplementation(({ workspaceSlug }) =>
      Promise.resolve({ items: workspaceSlug === 'workspace-a' ? 5 : 2 }),
    );
    vi.mocked(fetchCorrections).mockResolvedValue({ items: [] });
    vi.mocked(clearCatalog).mockImplementation(() => clearA.promise);

    const rendered = render(<MealInvoiceOcrView />);
    fireEvent.click(
      screen.getByRole('button', { name: 'apps:mealInvoiceOcr.manage.open' }),
    );
    expect(
      await screen.findByText('apps:mealInvoiceOcr.catalog.count:5'),
    ).not.toBeNull();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.manage.clearAll',
      }),
    );
    await waitFor(() =>
      expect(clearCatalog).toHaveBeenCalledWith({
        token: 'token',
        workspaceSlug: 'workspace-a',
      }),
    );

    workspaceState.slug = 'workspace-b';
    rendered.rerender(<MealInvoiceOcrView />);
    fireEvent.click(
      screen.getByRole('button', { name: 'apps:mealInvoiceOcr.manage.open' }),
    );
    expect(
      await screen.findByText('apps:mealInvoiceOcr.catalog.count:2'),
    ).not.toBeNull();

    await act(async () => {
      clearA.resolve();
      await Promise.resolve();
    });

    expect(
      screen.getByText('apps:mealInvoiceOcr.catalog.count:2'),
    ).not.toBeNull();
    expect(screen.queryByText('apps:mealInvoiceOcr.catalog.none')).toBeNull();
    confirm.mockRestore();
  });

  it('keeps the OCR supply amount authoritative when rows are edited or deleted', async () => {
    vi.mocked(fetchCatalogInfo).mockResolvedValue({ items: 0 });
    vi.mocked(exportInvoicesXlsx).mockResolvedValue(new Blob());
    vi.mocked(extractInvoices).mockResolvedValue({
      warnings: [],
      documents: [
        {
          원본파일: 'invoice.pdf',
          페이지: 1,
          거래처: 'Vendor',
          거래일: '',
          합계금액: '100',
          공급가액: '100',
          페이지이미지: '',
          품목: [
            {
              품명: 'Existing item',
              규격: '',
              수량: '1 ea',
              단가: '80',
              금액: '80',
              원산지: '국내산',
              신선도: 'O',
              불량여부: '-',
              반품여부: '-',
              비고: '',
            },
          ],
        },
      ],
    });

    render(<MealInvoiceOcrView />);
    const fileInput = document.querySelector<HTMLInputElement>(
      'input[type="file"][accept*=".pdf"]',
    );
    if (!fileInput) throw new Error('invoice file input not found');
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(['invoice'], 'invoice.pdf', { type: 'application/pdf' }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.extract',
      }),
    );

    expect(await screen.findByDisplayValue('Existing item')).not.toBeNull();
    const supplyInput = screen.getByLabelText(
      'apps:mealInvoiceOcr.table.supply',
    ) as HTMLInputElement;
    expect(
      (
        screen.getByLabelText(
          'apps:mealInvoiceOcr.supplyOriginalLabel',
        ) as HTMLInputElement
      ).value,
    ).toBe('100');
    fireEvent.change(
      screen.getByLabelText('apps:mealInvoiceOcr.supplyOriginalLabel'),
      { target: { value: '90' } },
    );
    expect(supplyInput.value).toBe('100');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.addRow',
      }),
    );
    const amountInputs = screen.getAllByLabelText(
      'apps:mealInvoiceOcr.table.amount',
    );
    const addedAmountInput = amountInputs.at(-1);
    if (!addedAmountInput) throw new Error('added amount input not found');
    fireEvent.change(addedAmountInput, { target: { value: '20' } });

    expect(supplyInput.value).toBe('100');
    // 합계금액 입력은 화면에서 제거됨(값은 데이터로만 유지). 공급가액(100)과 품목 합(80+20=100)이 일치.
    expect(screen.getByText('apps:mealInvoiceOcr.supplyMatch')).not.toBeNull();

    const addedRowRemoveButton = screen
      .getAllByTitle('apps:mealInvoiceOcr.actions.removeRow')
      .at(-1);
    if (!addedRowRemoveButton) throw new Error('added row remove button not found');
    fireEvent.click(addedRowRemoveButton);

    expect(supplyInput.value).toBe('100');

    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.export',
      }),
    );
    await waitFor(() => expect(exportInvoicesXlsx).toHaveBeenCalled());
    const exportRequest = vi.mocked(exportInvoicesXlsx).mock.calls.at(-1)?.[0];
    // 합계금액 입력을 제거했으므로 OCR 원값('100')이 그대로 내보내진다(UI에서 편집 불가).
    expect(exportRequest?.documents[0]?.합계금액).toBe('100');
  });

  it('keeps distinct files that share a name and size while deduplicating a reselection', () => {
    vi.mocked(fetchCatalogInfo).mockReturnValue(new Promise(() => undefined));
    render(<MealInvoiceOcrView />);
    const fileInput = document.querySelector<HTMLInputElement>(
      'input[type="file"][accept*=".pdf"]',
    );
    if (!fileInput) throw new Error('invoice file input not found');
    const first = new File(['aa'], 'invoice.pdf', {
      type: 'application/pdf',
      lastModified: 1,
    });
    const second = new File(['bb'], 'invoice.pdf', {
      type: 'application/pdf',
      lastModified: 2,
    });

    fireEvent.change(fileInput, { target: { files: [first, second, first] } });
    expect(screen.getByText('apps:mealInvoiceOcr.files.selected:2')).not.toBeNull();

    fireEvent.change(fileInput, { target: { files: [first] } });
    expect(screen.getByText('apps:mealInvoiceOcr.files.selected:2')).not.toBeNull();
  });
});

describe('MealInvoiceOcrView correction learning key', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.slug = 'workspace-a';
  });

  it('saves the raw OCR reading as the learning key and does not flag auto-corrections as edits', async () => {
    // 서버가 학습으로 '깐감자'를 '감자'로 자동 보정해 돌려준 행. 화면에는 보정값이 보이지만,
    // 학습 저장의 원본은 OCR 원문이어야 한다. 보정값('감자')을 키로 쌓으면 실재 품목이 오독 키로
    // 굳어 다음번에 제대로 읽은 감자를 망가뜨린다.
    vi.mocked(fetchCatalogInfo).mockResolvedValue({ items: 0 });
    vi.mocked(saveCorrections).mockResolvedValue({ saved: 1, total_stored: 1 });
    vi.mocked(extractInvoices).mockResolvedValue({
      warnings: [],
      documents: [
        {
          원본파일: 'invoice.pdf',
          페이지: 1,
          거래처: '성진유통',
          거래일: '2026-06-01',
          합계금액: '120000',
          공급가액: '120000',
          페이지이미지: '',
          품목: [
            {
              품명: '감자',
              규격: '',
              수량: '25 k',
              단가: '4800',
              금액: '120000',
              원산지: '중국산',
              신선도: 'O',
              불량여부: '-',
              반품여부: '-',
              비고: '',
              원문: { 품명: '깐감자', 수량: '25 박스', 원산지: '국내산' },
            },
          ],
        },
      ],
    });

    render(<MealInvoiceOcrView />);
    const fileInput = document.querySelector<HTMLInputElement>(
      'input[type="file"][accept*=".pdf"]',
    );
    if (!fileInput) throw new Error('invoice file input not found');
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(['invoice'], 'invoice.pdf', { type: 'application/pdf' }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.extract',
      }),
    );

    const nameInput = (await screen.findByDisplayValue(
      '감자',
    )) as HTMLInputElement;
    // 자동 보정은 사용자 수정이 아니므로 강조(수정됨) 스타일이 붙지 않는다.
    expect(nameInput.className).not.toContain('amber');
    // 원문('깐감자')도 화면에 노출하지 않는다.
    expect(screen.queryByText('깐감자')).toBeNull();

    fireEvent.click(
      screen.getByTitle('apps:mealInvoiceOcr.table.confirm'),
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: /apps:mealInvoiceOcr\.actions\.save/,
      }),
    );

    await waitFor(() => expect(saveCorrections).toHaveBeenCalled());
    const payload = vi.mocked(saveCorrections).mock.calls[0][0] as {
      items: { 원본: Record<string, string>; 교정: Record<string, string> }[];
    };
    expect(payload.items).toHaveLength(1);
    expect(payload.items[0].원본.품명).toBe('깐감자');
    expect(payload.items[0].원본.수량).toBe('25 박스');
    expect(payload.items[0].원본.원산지).toBe('국내산');
    expect(payload.items[0].교정.품명).toBe('감자');
  });

  it('does not record phantom unit corrections but keeps the auto-applied origin as a correction', async () => {
    // 손대지 않은 행을 '확인'만 했을 때:
    //  - 허용 목록 밖 단위('봉')를 빈칸으로 만드는 건 클라이언트 자동 정책이라 교정이 아니다.
    //    원본에도 같은 강제를 걸지 않으면 '봉→(빈칸)' 유령 교정이 쌓여, 서버의 '바뀐 게 없으면
    //    낡은 별칭을 폐기한다' 규칙이 영영 발동하지 않는다.
    //  - 반대로 OCR 이 못 읽은 원산지를 서버가 학습으로 채운 건 그대로 원본('')→교정('국내산')
    //    으로 실어야 그 별칭이 유지된다(필드별 폴백을 쓰면 원본==교정이 되어 별칭이 지워진다).
    vi.mocked(fetchCatalogInfo).mockResolvedValue({ items: 0 });
    vi.mocked(saveCorrections).mockResolvedValue({ saved: 1, total_stored: 1 });
    vi.mocked(extractInvoices).mockResolvedValue({
      warnings: [],
      documents: [
        {
          원본파일: 'invoice.pdf',
          페이지: 1,
          거래처: '성진유통',
          거래일: '2026-06-01',
          합계금액: '120000',
          공급가액: '120000',
          페이지이미지: '',
          품목: [
            {
              품명: '감자',
              규격: '',
              수량: '25 봉',
              단가: '4800',
              금액: '120000',
              원산지: '국내산',
              신선도: 'O',
              불량여부: '-',
              반품여부: '-',
              비고: '',
              원문: { 품명: '감자', 수량: '25 봉', 원산지: '' },
            },
          ],
        },
      ],
    });

    render(<MealInvoiceOcrView />);
    const fileInput = document.querySelector<HTMLInputElement>(
      'input[type="file"][accept*=".pdf"]',
    );
    if (!fileInput) throw new Error('invoice file input not found');
    fireEvent.change(fileInput, {
      target: {
        files: [
          new File(['invoice'], 'invoice.pdf', { type: 'application/pdf' }),
        ],
      },
    });
    fireEvent.click(
      screen.getByRole('button', {
        name: 'apps:mealInvoiceOcr.actions.extract',
      }),
    );

    await screen.findByDisplayValue('감자');
    fireEvent.click(screen.getByTitle('apps:mealInvoiceOcr.table.confirm'));
    fireEvent.click(
      screen.getByRole('button', {
        name: /apps:mealInvoiceOcr\.actions\.save/,
      }),
    );

    await waitFor(() => expect(saveCorrections).toHaveBeenCalled());
    const payload = vi.mocked(saveCorrections).mock.calls[0][0] as {
      items: { 원본: Record<string, string>; 교정: Record<string, string> }[];
    };
    expect(payload.items[0].원본.수량).toBe('25');
    expect(payload.items[0].교정.수량).toBe('25');
    expect(payload.items[0].원본.원산지).toBe('');
    expect(payload.items[0].교정.원산지).toBe('국내산');
  });
});
