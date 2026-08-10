import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  Database,
  Download,
  FileText,
  GraduationCap,
  GripVertical,
  ImageIcon,
  Loader2,
  Plus,
  ScanLine,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';

import {
  clearCatalog,
  clearCorrections,
  type CorrectionItem,
  type CorrectionRecord,
  deleteCorrection,
  exportInvoicesXlsx,
  extractInvoices,
  fetchCatalogInfo,
  fetchCorrectionImage,
  fetchCorrections,
  saveCorrections,
  uploadCatalog,
  type InvoiceDocument,
  type InvoiceExportDocument,
  type InvoiceRow,
} from '../api/meal-invoice-ocr-api';
import { InvoiceImageViewer } from '../components/InvoiceImageViewer';
import {
  canonicalUnit,
  enforceUnit,
  joinQty,
  normalizeQtyNumber,
  normUnit,
  parseNumber,
  parseQtyNumber,
  splitQty,
  UNIT_OPTIONS,
} from './meal-invoice-ocr-quantity';

const CROP_FIELDS: FieldKey[] = ['품명', '수량', '단가', '금액'];

// OCR 로 채워지고 원본↔교정 비교·사전매칭 대상이 되는 필드(값 편집형).
type FieldKey = '품명' | '규격' | '수량' | '단가' | '금액';

const ROW_FIELDS: FieldKey[] = ['품명', '수량', '단가', '금액'];
const NUMERIC_FIELDS = new Set<FieldKey>(['수량', '단가', '금액']);

// 품목=품명. 단위는 수량 칸의 드롭다운(기호)이 담당하므로, 규격 컬럼은 원래 의미(규격)로 둔다.
const FIELD_LABEL: Record<FieldKey, string> = {
  품명: 'itemName',
  규격: 'spec',
  수량: 'qty',
  단가: 'unitPrice',
  금액: 'amount',
};

// 컬럼 폭(헤더와 행을 정렬). 품목은 넓게 가변, 단위/숫자는 고정.
const FIELD_WIDTH: Record<FieldKey, string> = {
  품명: 'min-w-[8rem] flex-[3]',
  규격: 'w-16 shrink-0',
  수량: 'w-28 shrink-0',
  단가: 'w-20 shrink-0',
  금액: 'w-20 shrink-0',
};

// 수량 단위 드롭다운은 정규 단위 고정 목록(UNIT_OPTIONS)만 노출한다. OCR 단위는 enforceUnit 으로 허용 10개(+별칭)로만 강제하고, 그 외는 빈칸으로 둔다.


// 검수 입력용 부가 컬럼(선택/자유입력). OCR 원본 비교 대상이 아니다.
// 수기 명세표 프로그램의 원산지 목록과 동일. 가나다순(로캘 ko)으로 정렬해 쓴다.
const ORIGIN_OPTIONS = [
  '국내산',
  '중국산',
  '미국산',
  '베트남산',
  '태국산',
  '인도산',
  '러시아산',
  '우크라이나산',
  '이탈리아산',
  '호주산',
  '일본산',
  '페루산',
  '프랑스산',
  '칠레산',
  '브라질산',
  '필리핀산',
  '폴란드산',
  '스페인산',
  '노르웨이산',
  '벨기에산',
  '영국산',
  '캐나다산',
  '터키산',
  '미얀마산',
  '수입산',
  '외국산',
].sort((a, b) => a.localeCompare(b, 'ko'));
const FRESH_OPTIONS = ['O', '-', 'X'];
const YESNO_OPTIONS = ['-', 'O'];
// 금액 뒤에 오는 선택형 부가 컬럼(신선도/불량/반품). 헤더·행이 같은 순서로 렌더된다.
const META_SELECTS: Array<{
  key: '신선도' | '불량여부' | '반품여부';
  label: string;
  opts: string[];
  width: string;
}> = [
  { key: '신선도', label: 'freshness', opts: FRESH_OPTIONS, width: 'w-14 shrink-0' },
  { key: '불량여부', label: 'defect', opts: YESNO_OPTIONS, width: 'w-16 shrink-0' },
  { key: '반품여부', label: 'returned', opts: YESNO_OPTIONS, width: 'w-16 shrink-0' },
];
// 부가 컬럼 폭(헤더/행 정렬).
const META_WIDTH = {
  no: 'w-8 shrink-0',
  원산지: 'w-24 shrink-0',
  신선도: 'w-14 shrink-0',
  불량여부: 'w-16 shrink-0',
  반품여부: 'w-16 shrink-0',
  비고: 'w-24 shrink-0',
};

// 편집용 행: 화면 스냅샷(_orig)과 안정 id(_rid)를 얹어 원본↔수정 비교와 add/remove 를 안전하게 한다.
interface EditableRow extends InvoiceRow {
  _rid: string;
  // 사용자에게 처음 보여준 값. '사용자가 이 행을 고쳤는가' 표시(강조·취소선)에만 쓴다. 사전·카탈로그·
  // 과거 교정으로 자동 보정된 결과가 여기 들어오므로, 자동 보정은 수정으로 표시되지 않는다.
  _orig: Record<FieldKey, string>;
  // OCR 원본 원산지 스냅샷. 확정 별칭 학습에 '원본→교정 원산지'를 실어 보내기 위해 별도 보관한다
  // (원산지는 FieldKey 값편집 컬럼이 아니라 검수 입력 컬럼이라 _orig 와 분리한다).
  _origOrigin: string;
  // 자동 보정 '전' OCR 원문. 학습 저장의 키로만 쓰고 화면 표시에는 쓰지 않는다. 보정된 값을 키로
  // 저장하면 실재 품목이 오독 키로 굳어 정상 판독을 망가뜨린다.
  _source: { 품명: string; 수량: string; 원산지: string };
}

interface EditableDoc extends Omit<InvoiceDocument, '품목'> {
  품목: EditableRow[];
  // OCR 가 읽은 원래 공급가액(원금) 스냅샷. 행 편집과 무관하며 사용자가 별도로 보정할 수 있다.
  _origSupply: string;
}

const ACCEPTED_EXTENSIONS = [
  '.pdf',
  '.png',
  '.jpg',
  '.jpeg',
  '.webp',
  '.bmp',
  '.tif',
  '.tiff',
];

function isAcceptedFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

function fileSelectionKey(file: File): string {
  // 이름·크기만 같아도 서로 다른 스캔 파일일 수 있다. 디렉터리 경로가 있으면 우선 쓰고,
  // 일반 파일 선택에서도 lastModified/type까지 비교해 실제 재선택만 중복으로 본다.
  return [file.webkitRelativePath || file.name, file.size, file.lastModified, file.type].join('\0');
}

// 표시 이미지를 캔버스로 실제 90° 회전(뒤집힌 스캔 대응). 회전된 결과가 교정 저장에도 그대로 쓰인다.
function rotate90DataUrl(dataUrl: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.height;
      canvas.height = img.width;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('no-2d-context'));
        return;
      }
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate(Math.PI / 2);
      ctx.drawImage(img, -img.width / 2, -img.height / 2);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = () => reject(new Error('image-load-failed'));
    img.src = dataUrl;
  });
}

// 현재 화면에 남아 있는 행들의 금액 합(행합). 행을 지우면 즉시 줄어든다. 금액이 하나도 없으면 null.
function docRowSum(doc: EditableDoc): number | null {
  const amounts = doc.품목.map((row) => parseNumber(row.금액));
  if (!amounts.some((a) => a !== null)) return null;
  return amounts.reduce<number>((acc, a) => acc + (a ?? 0), 0);
}

// 공급가액(OCR/사용자 기준값)과 품목 합계(현재 행 금액 합)의 차이.
// null: 어느 한쪽을 숫자로 못 읽어 비교 불가. 0 이면 두 값이 일치.
function docSupplyVsSumDiff(doc: EditableDoc): number | null {
  const sum = docRowSum(doc);
  const supply = parseNumber(doc.공급가액 ?? '');
  if (sum === null || supply === null) return null;
  return Math.round(supply - sum);
}

// 차액에 부호를 붙여 표시(양수 +, 음수 −, 정확히 0 은 부호 없이). 콤마 자리수 포함.
function formatSignedDelta(delta: number): string {
  if (delta === 0) return '0';
  const sign = delta > 0 ? '+' : '−';
  return `${sign}${Math.abs(delta).toLocaleString()}`;
}

export function MealInvoiceOcrView() {
  const { t } = useTranslation(['apps']);
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null) ??
    '';

  const [files, setFiles] = useState<File[]>([]);
  const [documents, setDocuments] = useState<EditableDoc[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // 원산지를 목록 대신 직접 입력 중인 행들(rid 집합).
  const [customOriginRids, setCustomOriginRids] = useState<Set<string>>(new Set());
  // 수량 단위를 직접 입력 중인 행들(rid 집합) — '직접입력' 옵션 선택 시 그 행만 입력창으로.
  const [customUnitRids, setCustomUnitRids] = useState<Set<string>>(new Set());
  const [manageOpen, setManageOpen] = useState(false);
  const [manageLoading, setManageLoading] = useState(false);
  const [storedCorrections, setStoredCorrections] = useState<CorrectionRecord[]>([]);
  // 멀티 정렬: 켠 순서가 곧 우선순위(1차·2차...). 각 항목은 오름/내림 방향을 갖는다.
  const [sorts, setSorts] = useState<
    Array<{ key: 'date' | 'vendor' | 'itemName'; dir: 'asc' | 'desc' }>
  >([{ key: 'date', dir: 'desc' }]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const catalogInputRef = useRef<HTMLInputElement | null>(null);
  const ridRef = useRef(0);
  const extractRequestRef = useRef(0);
  const workspaceRequestRef = useRef(0);
  // 기준 카탈로그(영양사 대장) 적재 품목 수. null = 아직 조회 안 함.
  const [catalogCount, setCatalogCount] = useState<number | null>(null);
  const [catalogBusy, setCatalogBusy] = useState(false);

  // 토큰 교체는 진행 중 응답만 무효화한다. 워크스페이스 전환은 A의 문서/교정/카탈로그가
  // B 화면과 write/export endpoint에 재사용되지 않도록 paint 전에 workspace 상태도 비운다.
  useEffect(() => {
    extractRequestRef.current += 1;
    workspaceRequestRef.current += 1;
    setExtracting(false);
  }, [token]);

  useLayoutEffect(() => {
    extractRequestRef.current += 1;
    workspaceRequestRef.current += 1;
    ridRef.current = 0;
    setFiles([]);
    setDocuments([]);
    setWarnings([]);
    setStoredCorrections([]);
    setCatalogCount(null);
    setCustomOriginRids(new Set());
    setCustomUnitRids(new Set());
    setManageOpen(false);
    setManageLoading(false);
    setCatalogBusy(false);
    setExtracting(false);
    setExporting(false);
    setSaving(false);
    setDragging(false);
    setError(null);
    setNotice(null);
  }, [workspaceSlug]);

  const loadStored = useCallback(async () => {
    if (!token) return;
    const requestGeneration = workspaceRequestRef.current;
    setManageLoading(true);
    try {
      const result = await fetchCorrections({ token, workspaceSlug });
      if (workspaceRequestRef.current !== requestGeneration) return;
      setStoredCorrections(result.items ?? []);
    } catch {
      if (workspaceRequestRef.current !== requestGeneration) return;
      setStoredCorrections([]);
    } finally {
      if (workspaceRequestRef.current === requestGeneration) setManageLoading(false);
    }
  }, [token, workspaceSlug]);

  const loadCatalogInfo = useCallback(async () => {
    if (!token) return;
    const requestGeneration = workspaceRequestRef.current;
    try {
      const result = await fetchCatalogInfo({ token, workspaceSlug });
      if (workspaceRequestRef.current !== requestGeneration) return;
      setCatalogCount(result.items);
    } catch {
      if (workspaceRequestRef.current !== requestGeneration) return;
      setCatalogCount(null);
    }
  }, [token, workspaceSlug]);

  const toggleManage = useCallback(() => {
    setManageOpen((open) => {
      const next = !open;
      if (next) {
        void loadStored();
        void loadCatalogInfo();
      }
      return next;
    });
  }, [loadStored, loadCatalogInfo]);

  const onPickCatalog = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = ''; // 같은 파일 재선택 허용.
      if (!file || !token) return;
      const requestGeneration = workspaceRequestRef.current;
      setCatalogBusy(true);
      setError(null);
      try {
        const result = await uploadCatalog({ token, workspaceSlug, file });
        if (workspaceRequestRef.current !== requestGeneration) return;
        setCatalogCount(result.items);
        setNotice(t('apps:mealInvoiceOcr.catalog.loaded', { count: result.items }));
      } catch {
        if (workspaceRequestRef.current !== requestGeneration) return;
        setError(t('apps:mealInvoiceOcr.catalog.failed'));
      } finally {
        if (workspaceRequestRef.current === requestGeneration) setCatalogBusy(false);
      }
    },
    [t, token, workspaceSlug],
  );

  const onClearCatalog = useCallback(async () => {
    if (!token) return;
    // 워크스페이스 공용 카탈로그를 지우는 파괴적 작업 — 실행 전 확인.
    if (!window.confirm(t('apps:mealInvoiceOcr.manage.confirmClearCatalog'))) return;
    const requestGeneration = workspaceRequestRef.current;
    try {
      await clearCatalog({ token, workspaceSlug });
      if (workspaceRequestRef.current !== requestGeneration) return;
      setCatalogCount(0);
    } catch {
      /* 무시 */
    }
  }, [token, workspaceSlug, t]);

  const removeStored = useCallback(
    async (id: string) => {
      if (!token) return;
      if (!window.confirm(t('apps:mealInvoiceOcr.manage.confirmDeleteCorrection'))) return;
      const requestGeneration = workspaceRequestRef.current;
      setError(null);
      try {
        await deleteCorrection({ token, workspaceSlug, id });
        if (workspaceRequestRef.current !== requestGeneration) return;
        setStoredCorrections((prev) => prev.filter((r) => r.id !== id));
      } catch {
        if (workspaceRequestRef.current !== requestGeneration) return;
        setError(t('apps:mealInvoiceOcr.errors.deleteCorrection'));
      }
    },
    [t, token, workspaceSlug],
  );

  const clearStored = useCallback(async () => {
    if (!token) return;
    // 워크스페이스 공용 학습 데이터를 지우는 파괴적 작업 — 실행 전 확인.
    if (!window.confirm(t('apps:mealInvoiceOcr.manage.confirmClearCorrections'))) return;
    const requestGeneration = workspaceRequestRef.current;
    try {
      await clearCorrections({ token, workspaceSlug });
      if (workspaceRequestRef.current !== requestGeneration) return;
      setStoredCorrections([]);
    } catch {
      /* 무시 */
    }
  }, [token, workspaceSlug, t]);

  // 정렬 칩 클릭: 미선택 → 오름차순 → 내림차순 → 해제 순환. 여러 개 중복 선택 가능.
  const changeSort = useCallback((key: 'date' | 'vendor' | 'itemName') => {
    setSorts((prev) => {
      const idx = prev.findIndex((s) => s.key === key);
      if (idx < 0) return [...prev, { key, dir: 'asc' }];
      if (prev[idx].dir === 'asc') {
        const next = [...prev];
        next[idx] = { key, dir: 'desc' };
        return next;
      }
      return prev.filter((s) => s.key !== key);
    });
  }, []);

  const sortedCorrections = useMemo(() => {
    const keyOf = (r: CorrectionRecord, key: 'date' | 'vendor' | 'itemName'): string => {
      if (key === 'vendor') return r.거래처 ?? '';
      if (key === 'itemName') return r.교정?.품명 || r.원본?.품명 || '';
      return r.created_at ?? '';
    };
    const arr = [...storedCorrections];
    arr.sort((a, b) => {
      // 우선순위(켠 순서)대로 비교, 먼저 0이 아닌 결과가 나오면 그걸로 결정.
      for (const s of sorts) {
        const av = keyOf(a, s.key);
        const bv = keyOf(b, s.key);
        // 날짜는 ISO 문자열 비교, 이름은 로캘(한글) 비교.
        const cmp = s.key === 'date' ? av.localeCompare(bv) : av.localeCompare(bv, 'ko');
        if (cmp !== 0) return s.dir === 'asc' ? cmp : -cmp;
      }
      return 0;
    });
    return arr;
  }, [storedCorrections, sorts]);

  // 드롭다운 단위는 '고정' 목록만 노출한다: ''(없음/—) + UNIT_OPTIONS + (직접입력은 별도 옵션). 카탈로그·
  // 사용자 입력으로 목록을 늘리거나 줄이지 않는다. OCR 이 읽은 단위는 enforceUnit 으로 허용 10개(+별칭)로만 강제하고 그 외는 빈칸으로 둔다.
  const allUnits = useMemo(() => ['', ...UNIT_OPTIONS], []);

  // 진입 시 카탈로그 단위 목록을 미리 로드(관리 패널을 안 열어도 드롭다운에 반영).
  useEffect(() => {
    void loadCatalogInfo();
  }, [loadCatalogInfo]);

  const openCorrectionImage = useCallback(
    async (id: string) => {
      if (!token) return;
      // 팝업 차단 회피: 클릭 제스처 안에서 창을 먼저 연 뒤, 이미지가 준비되면 그 창으로 이동한다.
      // (window.open 을 await 뒤에서 호출하면 사용자 활성화가 소진돼 브라우저가 창을 막는다.)
      const win = window.open('', '_blank');
      try {
        const blob = await fetchCorrectionImage({ token, workspaceSlug, id });
        const url = URL.createObjectURL(blob);
        if (win) win.location.href = url;
        else window.open(url, '_blank');
        // 새 창이 이미지를 로드할 시간을 준 뒤 objectURL 해제.
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } catch {
        win?.close();
      }
    },
    [token, workspaceSlug],
  );

  const nextRid = useCallback(() => {
    ridRef.current += 1;
    return `r${ridRef.current}`;
  }, []);

  const toEditable = useCallback(
    (docs: InvoiceDocument[]): EditableDoc[] =>
      docs.map((doc) => ({
        ...doc,
        // 원금 = OCR 가 읽은 공급가액. 공급가액이 비어 있을 때 합계금액으로 추정하면 부가세가
        // 포함된 값을 원금으로 오인할 수 있으므로 빈 값 그대로 두고 사용자가 명시적으로 보정한다.
        _origSupply: doc.공급가액 ?? '',
        품목: (doc.품목 ?? []).map((row) => {
          // 수량의 단위를 정규 단위로 통일한다(예: 'box'→'박스', '팩'→'pac'). 드롭다운이 처음부터
          // 정규 단위로 매칭되고 엑셀 내보내기도 정규 단위로 나간다. OCR 원문은 _orig에 보존해
          // 자동 정규화가 값을 바꿨을 때도 교정 학습의 출처를 잃지 않게 한다.
          const { num, unit } = splitQty(row.수량);
          // 단위는 허용 10개(+별칭)로만 강제하고, 그 외(예: 'c'·'봉')는 빈칸으로 둔다(사용자 계약).
          // 숫자부는 '8.0'→'8'처럼 불필요한 소수점을 정수로 정리한다(실제 소수는 보존).
          const 수량 = joinQty(normalizeQtyNumber(num), enforceUnit(unit));
          // 두 스냅샷을 분리한다. _orig 는 '사용자가 고쳤는가'를 보여주기 위한 화면 기준값이라
          // 자동 보정된 결과를 담고(자동 보정은 수정으로 표시되지 않는다), _source 는 학습 저장의
          // 키로 쓸 OCR 원문이다. 하나로 합치면 자동 보정이 전부 수정 표시로 뜨거나(노란 강조),
          // 보정된 값이 학습 키가 되어 실재 품목이 오독 키로 굳는다.
          // 원문은 OCR 로 만든 행이면 항상 채워진다(품명이 비면 사용자가 직접 추가한 행). 원문이
          // 있으면 필드별 `||` 폴백 없이 통째로 쓴다. 필드별로 폴백하면 OCR 이 원산지를 못 읽은
          // 흔한 경우에 보정된 값이 원본으로 들어가 '원본==교정'이 되고, 서버가 그 행을 '고칠 게
          // 없던 확인'으로 보고 이미 학습해 둔 원산지 별칭을 지운다.
          const 원문 = row.원문?.품명 ? row.원문 : undefined;
          // 단위 강제(허용 10개 외 → 빈칸)는 자동 정책이라 학습 대상이 아니다. 원문 수량에도 같은
          // 정규화를 걸어야 손대지 않은 행을 확인만 해도 '봉→(빈칸)' 같은 유령 단위 교정이 쌓이지
          // 않는다. 반대로 자동 보정이 채워 넣은 단위('' → 'k')는 원문 쪽이 비어 있으므로 그대로
          // 교정으로 남아 학습이 유지된다.
          const src수량 = splitQty(원문?.수량 ?? row.수량);
          return {
            ...row,
            수량,
            _rid: nextRid(),
            _orig: {
              품명: row.품명,
              규격: row.규격,
              // 화면에 처음 보여준 값(정규화 후)을 담는다. 정규화 전 값을 담으면 '8.0 box'→'8 박스'
              // 같은 자동 변환까지 사용자 수정으로 강조돼, 실제로 사람이 고친 행을 구분할 수 없다.
              수량,
              단가: row.단가,
              금액: row.금액,
            },
            _origOrigin: row.원산지 ?? '',
            _source: {
              품명: 원문?.품명 ?? row.품명,
              수량: joinQty(normalizeQtyNumber(src수량.num), enforceUnit(src수량.unit)),
              원산지: 원문?.원산지 ?? row.원산지 ?? '',
            },
          };
        }),
      })),
    [nextRid],
  );

  const canExport = useMemo(
    () => documents.some((doc) => doc.품목.length > 0),
    [documents],
  );

  // 여러 번에 나눠 담을 수 있게 기존 목록에 이어 붙인다.
  const appendFiles = useCallback((incoming: File[]) => {
    const accepted = incoming.filter(isAcceptedFile);
    if (accepted.length === 0) return;
    setFiles((prev) => {
      const seen = new Set(prev.map(fileSelectionKey));
      const added = accepted.filter((file) => {
        const key = fileSelectionKey(file);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      return added.length > 0 ? [...prev, ...added] : prev;
    });
    setError(null);
  }, []);

  const onPickFiles = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      appendFiles(Array.from(event.target.files ?? []));
      // 같은 파일을 다시 골라도 onChange 가 다시 걸리도록 입력값을 비운다.
      event.target.value = '';
    },
    [appendFiles],
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const onDragOver = useCallback((event: React.DragEvent) => {
    if (Array.from(event.dataTransfer.types).includes('Files')) {
      event.preventDefault();
      setDragging(true);
    }
  }, []);

  const onDragLeave = useCallback((event: React.DragEvent) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setDragging(false);
    }
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      if (extracting) return;
      // 드롭한 파일들을 기존 목록에 이어 붙인다(여러 장을 여러 번 끌어다 놓을 수 있게).
      appendFiles(Array.from(event.dataTransfer.files));
    },
    [extracting, appendFiles],
  );

  const onExtract = useCallback(async () => {
    if (!token || files.length === 0) {
      setError(t('apps:mealInvoiceOcr.errors.noFiles'));
      return;
    }
    const requestId = ++extractRequestRef.current;
    setExtracting(true);
    setError(null);
    try {
      const result = await extractInvoices({ token, workspaceSlug, files });
      if (extractRequestRef.current !== requestId) return;
      setDocuments(toEditable(result.documents ?? []));
      setWarnings(result.warnings ?? []);
    } catch {
      if (extractRequestRef.current !== requestId) return;
      setError(t('apps:mealInvoiceOcr.errors.extract'));
    } finally {
      if (extractRequestRef.current === requestId) setExtracting(false);
    }
  }, [files, t, toEditable, token, workspaceSlug]);

  const onExport = useCallback(async () => {
    if (!token) return;
    const requestGeneration = workspaceRequestRef.current;
    setExporting(true);
    setError(null);
    try {
      // 서버로 되돌릴 때 큰 크롭 이미지와 클라이언트 전용 필드는 제거하고 확인여부는 보존한다.
      const payload: InvoiceExportDocument[] = documents.map((doc) => ({
        원본파일: doc.원본파일,
        페이지: doc.페이지,
        거래처: doc.거래처,
        거래일: doc.거래일,
        합계금액: doc.합계금액,
        공급가액: doc.공급가액 ?? '',
        합계검증: doc.합계검증,
        품목: doc.품목.map((row) => ({
          품명: row.품명,
          규격: row.규격,
          수량: row.수량,
          단가: row.단가,
          금액: row.금액,
          금액검증: row.금액검증,
          확인여부: row.확인여부 ?? false,
          원산지: row.원산지 ?? '',
          신선도: row.신선도 ?? '',
          불량여부: row.불량여부 ?? '',
          반품여부: row.반품여부 ?? '',
          비고: row.비고 ?? '',
        })),
      }));
      const blob = await exportInvoicesXlsx({ token, workspaceSlug, documents: payload });
      if (workspaceRequestRef.current !== requestGeneration) return;
      downloadBlobAsFile(blob, 'meal-invoice-ocr.xlsx');
    } catch {
      if (workspaceRequestRef.current !== requestGeneration) return;
      setError(t('apps:mealInvoiceOcr.errors.export'));
    } finally {
      if (workspaceRequestRef.current === requestGeneration) setExporting(false);
    }
  }, [documents, t, token, workspaceSlug]);

  const confirmedCount = useMemo(
    () => documents.reduce((n, doc) => n + doc.품목.filter((r) => r.확인여부).length, 0),
    [documents],
  );

  const onSaveCorrections = useCallback(async () => {
    if (!token) return;
    const requestGeneration = workspaceRequestRef.current;
    // '확인'한 행만 학습 데이터로 저장(신뢰 신호). 원본↔교정 쌍을 서버에 축적한다.
    // 페이지 이미지는 행마다 반복 전송하지 않고(한 장 20~30행이면 요청 총량이 40MB 상한을 넘어
    // 정상 사용 중 저장이 실패한다), '문서이미지' 맵에 문서당 한 번만 싣고 각 교정은 문서키로 연결한다.
    const items: CorrectionItem[] = [];
    const 문서이미지: Record<string, string> = {};
    documents.forEach((doc, docIndex) => {
      const 문서키 = `${doc.원본파일}#${doc.페이지}#${docIndex}`;
      let hasConfirmed = false;
      for (const row of doc.품목) {
        if (!row.확인여부) continue;
        hasConfirmed = true;
        items.push({
          거래처: doc.거래처,
          거래일: doc.거래일,
          // 원산지도 원본→교정으로 실어 실제 변경된 필드만 안전하게 재적용할 수 있게 한다.
          // 품명·수량·원산지는 자동 보정이 값을 바꿀 수 있으므로 보정 전 OCR 원문(_source)을 키로
          // 쓴다. 규격·단가·금액은 보정 대상이 아니라 화면 스냅샷을 그대로 쓴다.
          원본: {
            ...row._orig,
            품명: row._source.품명,
            수량: row._source.수량,
            원산지: row._source.원산지,
          },
          교정: {
            품명: row.품명,
            규격: row.규격,
            수량: row.수량,
            단가: row.단가,
            금액: row.금액,
            원산지: row.원산지 ?? '',
          },
          문서키,
          크롭이미지: '',
        });
      }
      // 확인된 행이 있는 문서만 페이지 이미지를 한 번 싣는다(관리 화면 '원본 보기'용, 해시로 중복 제거).
      if (hasConfirmed && doc.페이지이미지) 문서이미지[문서키] = doc.페이지이미지;
    });
    if (items.length === 0) {
      setError(t('apps:mealInvoiceOcr.errors.noConfirmed'));
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await saveCorrections({ token, workspaceSlug, items, 문서이미지 });
      if (workspaceRequestRef.current !== requestGeneration) return;
      setNotice(
        t('apps:mealInvoiceOcr.saved', {
          saved: result.saved,
          total: result.total_stored,
        }),
      );
    } catch {
      if (workspaceRequestRef.current !== requestGeneration) return;
      setError(t('apps:mealInvoiceOcr.errors.save'));
    } finally {
      if (workspaceRequestRef.current === requestGeneration) setSaving(false);
    }
  }, [documents, t, token, workspaceSlug]);

  const updateDoc = useCallback(
    (docIndex: number, patch: Partial<EditableDoc>) => {
      setDocuments((prev) =>
        prev.map((doc, i) => (i === docIndex ? { ...doc, ...patch } : doc)),
      );
    },
    [],
  );

  // 사진 여러 장을 인식한 뒤, 결과 중 마음에 안 드는 문서(사진/페이지) 하나를 통째로 뺀다.
  const removeDocument = useCallback((docIndex: number) => {
    setDocuments((prev) => prev.filter((_, i) => i !== docIndex));
  }, []);

  const openPageImageNewWindow = useCallback((dataUrl: string) => {
    if (!dataUrl) return;
    // src 가 이미 data: URL 이라 네트워크 왕복이 필요 없다. 클릭 제스처 안에서 창을 동기적으로
    // 열고 이미지를 바로 그려 팝업 차단을 피한다(data: URL 로의 top-level 이동은 막히므로 img 로 렌더).
    const win = window.open('', '_blank');
    if (!win) return;
    win.document.write(
      `<!doctype html><title>original</title>` +
        `<body style="margin:0;background:#111">` +
        `<img src="${dataUrl}" style="max-width:100%;height:auto;display:block;margin:0 auto" alt="">`,
    );
    win.document.close();
  }, []);

  // 사진 열 폭(%). 사진↔표 사이 분할선을 드래그해 조절(lg 이상). 모든 문서 공통.
  // 기본을 좁게 잡아 항목 입력 표가 왼쪽으로 더 넓게 나오게 한다.
  const [imageWidthPct, setImageWidthPct] = useState(42);
  // 드래그 중인 분할선이 속한 flex-row 컨테이너(폭 계산 기준).
  const splitContainerRef = useRef<HTMLElement | null>(null);

  const onSplitterDown = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    splitContainerRef.current = e.currentTarget.parentElement;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const el = splitContainerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      // 사진은 왼쪽 열이므로 컨테이너 좌측~마우스 거리 = 사진 폭 비율.
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setImageWidthPct(Math.max(25, Math.min(72, pct)));
    };
    const onUp = () => {
      if (splitContainerRef.current) {
        splitContainerRef.current = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  const rotateDocImage = useCallback(
    async (docIndex: number) => {
      const target = documents[docIndex];
      const src = target?.페이지이미지 ?? '';
      if (!target || !src) return;
      const requestGeneration = workspaceRequestRef.current;
      const targetIdentity = `${target.원본파일}#${target.페이지}`;
      try {
        const rotated = await rotate90DataUrl(src);
        if (workspaceRequestRef.current !== requestGeneration) return;
        setDocuments((prev) =>
          prev.map((doc, i) =>
            i === docIndex &&
            `${doc.원본파일}#${doc.페이지}` === targetIdentity &&
            doc.페이지이미지 === src
              ? { ...doc, 페이지이미지: rotated }
              : doc,
          ),
        );
      } catch {
        /* 무시 */
      }
    },
    [documents],
  );

  const updateRow = useCallback(
    (
      docIndex: number,
      rid: string,
      field: FieldKey | '원산지' | '신선도' | '불량여부' | '반품여부' | '비고',
      value: string,
    ) => {
      setDocuments((prev) =>
        prev.map((doc, i) => {
          if (i !== docIndex) return doc;
          const 품목 = doc.품목.map((row) => {
            if (row._rid !== rid) return row;
            const updated = { ...row, [field]: value };
            // 수량·단가의 '숫자'가 실제로 바뀔 때만 금액 = 수량 × 단가 자동 계산.
            // 수량 칸의 단위만 바꿨거나(숫자 동일) 값이 그대로면 재계산하지 않아,
            // 사용자가 손수 교정한 금액(부가세 포함·kg단가×박스 등)을 덮어쓰지 않는다.
            // 수량은 "숫자 단위"(예: "2 10k") 형식이라 단위의 숫자('10k')가 수량에 섞이지 않게
            // parseQtyNumber(숫자부만 파싱)를 쓴다. 단가/금액은 단위가 없어 parseNumber 로 충분.
            if (field === '수량' || field === '단가') {
              const qty = parseQtyNumber(updated.수량);
              const price = parseNumber(updated.단가);
              const prevNumber =
                field === '수량' ? parseQtyNumber(row.수량) : parseNumber(row.단가);
              const nextNumber =
                field === '수량' ? parseQtyNumber(updated.수량) : parseNumber(updated.단가);
              if (nextNumber !== prevNumber && qty !== null && price !== null) {
                updated.금액 = String(Math.round(qty * price));
              }
            }
            return updated;
          });
          // 공급가액은 OCR reconciliation target이다. 행 교정은 기준값을 따라 움직이지 않는다.
          return { ...doc, 품목 };
        }),
      );
    },
    [],
  );

  const toggleConfirm = useCallback((docIndex: number, rid: string) => {
    setDocuments((prev) =>
      prev.map((doc, i) => {
        if (i !== docIndex) return doc;
        return {
          ...doc,
          품목: doc.품목.map((row) =>
            row._rid === rid ? { ...row, 확인여부: !row.확인여부 } : row,
          ),
        };
      }),
    );
  }, []);

  const addRow = useCallback(
    (docIndex: number) => {
      setDocuments((prev) =>
        prev.map((doc, i) =>
          i === docIndex
            ? {
                ...doc,
                품목: [
                  ...doc.품목,
                  {
                    품명: '',
                    규격: '',
                    수량: '',
                    단가: '',
                    금액: '',
                    금액검증: '',
                    원산지: '국내산',
                    신선도: 'O',
                    불량여부: '-',
                    반품여부: '-',
                    비고: '',
                    크롭이미지: '',
                    확인여부: false,
                    사전후보: '',
                    사전점수: 0,
                    단위후보: '',
                    단가후보: '',
                    단위후보목록: [],
                    _rid: nextRid(),
                    _orig: { 품명: '', 규격: '', 수량: '', 단가: '', 금액: '' },
                    _source: { 품명: '', 수량: '', 원산지: '' },
                    _origOrigin: '국내산',
                  },
                ],
              }
            : doc,
        ),
      );
    },
    [nextRid],
  );

  const removeRow = useCallback((docIndex: number, rid: string) => {
    setDocuments((prev) =>
      prev.map((doc, i) => {
        if (i !== docIndex) return doc;
        const 품목 = doc.품목.filter((row) => row._rid !== rid);
        // 삭제도 reconciliation target인 OCR 공급가액을 바꾸지 않는다.
        return { ...doc, 품목 };
      }),
    );
  }, []);

  // 키보드로 행 순서 변경(드래그의 접근성 대체 경로). 그립 핸들에서 ↑/↓ 로 호출한다.
  const moveRow = useCallback((docIndex: number, rowIndex: number, delta: number) => {
    setDocuments((prev) =>
      prev.map((doc, i) => {
        if (i !== docIndex) return doc;
        const target = rowIndex + delta;
        if (target < 0 || target >= doc.품목.length) return doc;
        const arr = [...doc.품목];
        const [moved] = arr.splice(rowIndex, 1);
        arr.splice(target, 0, moved);
        return { ...doc, 품목: arr };
      }),
    );
  }, []);

  // 행 순서 드래그(iOS 주식 앱 스타일). 배열 순서가 곧 엑셀 출력 순서다.
  // 잡은 행은 그 자리에서 들려 손가락을 따라오고, 나머지 행은 transform+transition 으로
  // 스르륵 밀려 자리를 내준다. 실제 배열 재정렬은 손을 뗄 때 한 번만 커밋한다.
  type DragState = {
    docIndex: number;
    startIndex: number; // 잡은 행의 원래 인덱스
    currentIndex: number; // 현재 놓일 인덱스
    count: number; // 그 문서의 행 수
    step: number; // 행 하나 높이(+간격) px
    deltaY: number; // 잡은 행이 따라온 세로 이동량
    settling?: boolean; // 놓은 뒤 목표 슬롯으로 안착 애니메이션 중
  };
  const [drag, setDrag] = useState<DragState | null>(null);
  // 순서 확정 프레임에서만 transition 을 꺼 잔여 점프를 없앤다(FLIP).
  const [suppressAnim, setSuppressAnim] = useState(false);
  // 커밋 시 상태 업데이터 밖에서 참조할 진실원본(StrictMode 이중 실행로 인한 이중 커밋 방지).
  const dragRef = useRef<DragState | null>(null);
  const dragStartYRef = useRef(0);

  const onGripPointerDown = useCallback(
    (e: React.PointerEvent, docIndex: number, index: number, count: number) => {
      if (e.button !== 0) return;
      const rowEl = e.currentTarget.closest('[data-row]');
      if (!(rowEl instanceof HTMLElement)) return;
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      dragStartYRef.current = e.clientY;
      // 행 높이 + 목록 간격(gap-1 = 4px)을 한 스텝으로.
      const step = rowEl.getBoundingClientRect().height + 4;
      const next: DragState = {
        docIndex,
        startIndex: index,
        currentIndex: index,
        count,
        step,
        deltaY: 0,
      };
      dragRef.current = next;
      setDrag(next);
    },
    [],
  );

  const onGripPointerMove = useCallback((e: React.PointerEvent) => {
    const prev = dragRef.current;
    if (!prev) return;
    const deltaY = e.clientY - dragStartYRef.current;
    const raw = prev.startIndex + Math.round(deltaY / prev.step);
    const currentIndex = Math.max(0, Math.min(prev.count - 1, raw));
    if (deltaY === prev.deltaY && currentIndex === prev.currentIndex) return;
    const next: DragState = { ...prev, deltaY, currentIndex };
    dragRef.current = next;
    setDrag(next);
  }, []);

  const endGripDrag = useCallback((e: React.PointerEvent) => {
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* 무시 */
    }
    const prev = dragRef.current;
    dragRef.current = null;
    if (!prev) {
      setDrag(null);
      return;
    }
    // 1) 잡은 행을 자유 위치(deltaY)에서 정확한 목표 슬롯으로 부드럽게 안착(튕김 제거).
    const snappedDeltaY = (prev.currentIndex - prev.startIndex) * prev.step;
    setDrag({ ...prev, deltaY: snappedDeltaY, settling: true });
    // 2) 안착 애니메이션이 끝나면 실제 배열 순서를 커밋하고 드래그 해제.
    //    이때 시각 위치 == 새 레이아웃 위치라 transform 을 지워도 점프가 없다.
    window.setTimeout(() => {
      // 확정 프레임: 시각 위치와 새 레이아웃이 같으므로 애니메이션을 꺼 transform 을 즉시 지운다.
      setSuppressAnim(true);
      if (prev.currentIndex !== prev.startIndex) {
        setDocuments((docs) =>
          docs.map((doc, i) => {
            if (i !== prev.docIndex) return doc;
            const arr = [...doc.품목];
            const [moved] = arr.splice(prev.startIndex, 1);
            arr.splice(prev.currentIndex, 0, moved);
            return { ...doc, 품목: arr };
          }),
        );
      }
      // 도중에 새 드래그가 시작됐으면(=dragRef 채워짐) 그 상태를 건드리지 않는다.
      setDrag((cur) => (dragRef.current ? cur : null));
      // 다음 프레임에 애니메이션 복구(그래야 이후 드래그가 다시 부드럽다).
      window.requestAnimationFrame(() =>
        window.requestAnimationFrame(() => setSuppressAnim(false)),
      );
    }, 180);
  }, []);

  // 드래그 중 각 행의 시각 오프셋: 잡은 행은 손가락 따라 이동, 사이 행들은 한 칸씩 밀림.
  const rowDragStyle = useCallback(
    (docIndex: number, rowIndex: number): { transform?: string; z: boolean; lifted: boolean } => {
      if (!drag || drag.docIndex !== docIndex) return { z: false, lifted: false };
      if (rowIndex === drag.startIndex) {
        return { transform: `translateY(${drag.deltaY}px)`, z: true, lifted: true };
      }
      const { startIndex: s, currentIndex: c, step } = drag;
      if (s < c && rowIndex > s && rowIndex <= c) {
        return { transform: `translateY(${-step}px)`, z: false, lifted: false };
      }
      if (s > c && rowIndex >= c && rowIndex < s) {
        return { transform: `translateY(${step}px)`, z: false, lifted: false };
      }
      return { z: false, lifted: false };
    },
    [drag],
  );

  return (
    <div
      className="relative flex h-full flex-col gap-4 overflow-auto p-6"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {dragging ? (
        <div className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-blue-400 bg-blue-50/80 text-sm font-medium text-blue-700">
          <span className="inline-flex items-center gap-2">
            <UploadCloud className="h-5 w-5" />
            {t('apps:mealInvoiceOcr.actions.dropHint')}
          </span>
        </div>
      ) : null}

      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold text-gray-900">
            {t('apps:mealInvoiceOcr.header.title')}
          </h1>
          <p className="text-sm text-gray-500">
            {t('apps:mealInvoiceOcr.header.subtitle')}
          </p>
        </div>
        <button
          type="button"
          onClick={toggleManage}
          className={`inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium ${
            manageOpen
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
              : 'border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          <Database className="h-4 w-4" />
          {t('apps:mealInvoiceOcr.manage.open')}
        </button>
      </header>

      {manageOpen ? (
        <section className="flex flex-col gap-2 rounded-lg border border-indigo-200 bg-indigo-50/30 p-4">
          {/* 기준 카탈로그(영양사 대장 엑셀) — 품목/단위/단가 제안의 원천. */}
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-indigo-100 bg-white px-3 py-2">
            <input
              ref={catalogInputRef}
              type="file"
              // 서버 파서(openpyxl)는 XLSX(ZIP) 컨테이너만 읽는다. 레거시 .xls(BIFF)는 지원하지
              // 않으므로 UI 도 .xlsx 만 허용해, 사용자가 고른 파일이 업로드에서 415 로 확정 실패하는
              // 클라이언트↔서버 형식 계약 불일치를 없앤다.
              accept=".xlsx"
              className="hidden"
              onChange={(e) => void onPickCatalog(e)}
            />
            <div className="flex min-w-0 flex-col">
              <span className="text-sm font-medium text-gray-800">
                {t('apps:mealInvoiceOcr.catalog.title')}
              </span>
              <span className="text-xs text-gray-500">
                {catalogCount && catalogCount > 0
                  ? t('apps:mealInvoiceOcr.catalog.count', { count: catalogCount })
                  : t('apps:mealInvoiceOcr.catalog.none')}
              </span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => catalogInputRef.current?.click()}
                disabled={catalogBusy}
                className="inline-flex items-center gap-1 rounded-md border border-indigo-300 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
              >
                {catalogBusy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <UploadCloud className="h-3.5 w-3.5" />
                )}
                {t('apps:mealInvoiceOcr.catalog.upload')}
              </button>
              {catalogCount && catalogCount > 0 ? (
                <button
                  type="button"
                  onClick={() => void onClearCatalog()}
                  className="text-xs text-red-600 hover:text-red-800"
                >
                  {t('apps:mealInvoiceOcr.manage.clearAll')}
                </button>
              ) : null}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">
              {t('apps:mealInvoiceOcr.manage.title', {
                count: storedCorrections.length,
              })}
            </h2>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void loadStored()}
                className="text-xs text-indigo-600 hover:text-indigo-800"
              >
                {t('apps:mealInvoiceOcr.manage.refresh')}
              </button>
              {storedCorrections.length > 0 ? (
                <button
                  type="button"
                  onClick={() => void clearStored()}
                  className="text-xs text-red-600 hover:text-red-800"
                >
                  {t('apps:mealInvoiceOcr.manage.clearAll')}
                </button>
              ) : null}
            </div>
          </div>
          {storedCorrections.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-gray-500">
                {t('apps:mealInvoiceOcr.manage.sortBy')}
              </span>
              {(
                [
                  ['date', 'date'],
                  ['vendor', 'vendor'],
                  ['itemName', 'itemName'],
                ] as const
              ).map(([key, labelKey]) => {
                const idx = sorts.findIndex((s) => s.key === key);
                const active = idx >= 0;
                const dir = active ? sorts[idx].dir : null;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => changeSort(key)}
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${
                      active
                        ? 'border-indigo-300 bg-indigo-100 text-indigo-700'
                        : 'border-gray-200 bg-white text-gray-500 hover:bg-gray-50'
                    }`}
                  >
                    {/* 여러 기준을 켜면 우선순위 번호 표시(1차·2차...). */}
                    {active && sorts.length > 1 ? (
                      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-indigo-500 text-[9px] font-bold text-white">
                        {idx + 1}
                      </span>
                    ) : null}
                    {t(`apps:mealInvoiceOcr.table.${labelKey}`)}
                    {dir === 'asc' ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : dir === 'desc' ? (
                      <ArrowDown className="h-3 w-3" />
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-40" />
                    )}
                  </button>
                );
              })}
            </div>
          ) : null}
          {manageLoading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('apps:mealInvoiceOcr.manage.loading')}
            </div>
          ) : storedCorrections.length === 0 ? (
            <div className="py-4 text-center text-sm text-gray-400">
              {t('apps:mealInvoiceOcr.manage.empty')}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {sortedCorrections.map((record) => {
                const orig = record.원본 ?? {};
                const fixed = record.교정 ?? {};
                return (
                  <div
                    key={record.id}
                    className="flex items-center gap-3 rounded-md border border-indigo-100 bg-white px-2 py-1"
                  >
                    <span className="w-40 shrink-0 truncate text-[11px] text-gray-400">
                      {record.거래처 || '-'} · {(record.created_at || '').slice(0, 10)}
                    </span>
                    <div className="flex min-w-0 flex-1 flex-wrap gap-x-4 gap-y-0.5 text-sm">
                      {CROP_FIELDS.map((field) => {
                        const before = orig[field] ?? '';
                        const after = fixed[field] ?? '';
                        if (!before && !after) return null;
                        const changed = before !== after;
                        return (
                          <div key={field} className="flex items-center gap-1">
                            <span className="text-[10px] uppercase tracking-wide text-gray-400">
                              {t(`apps:mealInvoiceOcr.table.${FIELD_LABEL[field]}`)}
                            </span>
                            {changed ? (
                              <>
                                <span className="text-gray-400 line-through">
                                  {before || '∅'}
                                </span>
                                <span className="text-gray-400">→</span>
                                <span className="font-semibold text-indigo-700">
                                  {after || '∅'}
                                </span>
                              </>
                            ) : (
                              <span className="text-gray-700">{after}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    {record.이미지있음 ? (
                      <button
                        type="button"
                        onClick={() => void openCorrectionImage(record.id)}
                        className="inline-flex shrink-0 items-center gap-1 rounded border border-indigo-200 px-2 py-0.5 text-xs text-indigo-600 hover:bg-indigo-50"
                      >
                        <ImageIcon className="h-3.5 w-3.5" />
                        {t('apps:mealInvoiceOcr.manage.viewImage')}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void removeStored(record.id)}
                      title={t('apps:mealInvoiceOcr.actions.removeRow')}
                      className="shrink-0 text-gray-300 hover:text-red-600"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff"
          disabled={extracting}
          className="hidden"
          onChange={onPickFiles}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={extracting}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          <UploadCloud className="h-4 w-4" />
          {t('apps:mealInvoiceOcr.actions.pickFiles')}
        </button>
        {files.length > 0 ? (
          <div className="flex flex-1 flex-wrap items-center gap-1.5">
            <span className="text-sm text-gray-500">
              {t('apps:mealInvoiceOcr.files.selected', { count: files.length })}
            </span>
            {files.map((file, index) => (
              <span
                key={`${file.name}-${index}`}
                className="inline-flex max-w-[16rem] items-center gap-1 rounded-full border border-gray-200 bg-gray-50 py-0.5 pl-2 pr-1 text-xs text-gray-700"
                title={file.name}
              >
                <FileText className="h-3 w-3 shrink-0 text-gray-400" />
                <span className="truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  disabled={extracting}
                  title={t('apps:mealInvoiceOcr.actions.removeRow')}
                  className="shrink-0 rounded-full p-0.5 text-gray-400 hover:bg-gray-200 hover:text-red-600"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <span className="text-sm text-gray-500">
            {t('apps:mealInvoiceOcr.files.none')}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={onExtract}
            disabled={extracting || files.length === 0}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {extracting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ScanLine className="h-4 w-4" />
            )}
            {extracting
              ? t('apps:mealInvoiceOcr.actions.extracting')
              : t('apps:mealInvoiceOcr.actions.extract')}
          </button>
          <button
            type="button"
            onClick={onSaveCorrections}
            disabled={saving || confirmedCount === 0}
            title={t('apps:mealInvoiceOcr.actions.saveHint')}
            className="inline-flex items-center gap-2 rounded-md border border-indigo-300 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GraduationCap className="h-4 w-4" />
            )}
            {t('apps:mealInvoiceOcr.actions.save', { count: confirmedCount })}
          </button>
          <button
            type="button"
            onClick={onExport}
            disabled={exporting || !canExport}
            className="inline-flex items-center gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
          >
            {exporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {t('apps:mealInvoiceOcr.actions.export')}
          </button>
        </div>
      </div>

      {notice ? (
        <div className="rounded-md border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-700">
          {notice}
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <div className="mb-1 flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {t('apps:mealInvoiceOcr.warningsTitle')}
          </div>
          <ul className="list-disc pl-5">
            {warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {documents.length === 0 ? (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={extracting}
          className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-gray-300 p-10 text-center text-sm text-gray-400 hover:border-blue-300 hover:text-blue-500"
        >
          <UploadCloud className="h-6 w-6" />
          <span>{t('apps:mealInvoiceOcr.empty')}</span>
          <span className="text-xs">{t('apps:mealInvoiceOcr.actions.dropHint')}</span>
        </button>
      ) : (
        documents.map((doc, docIndex) => {
          const rowSum = docRowSum(doc);
          // 공급가액(OCR/사용자 기준값)과 품목 합계(현재 행 금액 합)의 일치 여부.
          const supplyVsSumDiff = docSupplyVsSumDiff(doc);
          const supplyMatchesSum = supplyVsSumDiff !== null ? supplyVsSumDiff === 0 : null;
          // 원금(OCR 원래 공급가액)과 현재 공급가액의 차이(빠지거나 더해진 금액).
          const origSupply = parseNumber(doc._origSupply ?? '');
          const curSupply = parseNumber(doc.공급가액 ?? '');
          const supplyChange =
            origSupply !== null && curSupply !== null ? Math.round(curSupply - origSupply) : null;
          const docKey = `${doc.원본파일}-${doc.페이지}-${docIndex}`;
          return (
            <section
              key={docKey}
              className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4"
            >
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <span className="font-medium text-gray-900">
                  {doc.원본파일} · p{doc.페이지}
                </span>
                <label className="flex items-center gap-1 text-gray-500">
                  {t('apps:mealInvoiceOcr.table.vendor')}
                  <input
                    value={doc.거래처}
                    onChange={(e) => updateDoc(docIndex, { 거래처: e.target.value })}
                    className="rounded border border-gray-200 px-2 py-1 text-gray-900"
                  />
                </label>
                <label className="flex items-center gap-1 text-gray-500">
                  {t('apps:mealInvoiceOcr.table.date')}
                  <input
                    value={doc.거래일}
                    onChange={(e) => updateDoc(docIndex, { 거래일: e.target.value })}
                    className="rounded border border-gray-200 px-2 py-1 text-gray-900"
                  />
                </label>
                <div className="flex flex-col gap-0.5">
                  <label className="flex items-center gap-1 text-gray-500">
                    {t('apps:mealInvoiceOcr.table.supply')}
                    <input
                      value={doc.공급가액 ?? ''}
                      inputMode="numeric"
                      onChange={(e) =>
                        updateDoc(docIndex, { 공급가액: e.target.value.replace(/[^\d]/g, '') })
                      }
                      className="w-28 rounded border border-gray-200 px-2 py-1 text-right text-gray-900"
                    />
                  </label>
                  <span className="flex items-center gap-1 pl-1 text-xs text-gray-400">
                    {t('apps:mealInvoiceOcr.supplyOriginalLabel')}
                    <input
                      aria-label={t('apps:mealInvoiceOcr.supplyOriginalLabel')}
                      value={doc._origSupply ?? ''}
                      inputMode="numeric"
                      onChange={(e) =>
                        updateDoc(docIndex, {
                          _origSupply: e.target.value.replace(/[^\d]/g, ''),
                        })
                      }
                      className="w-24 rounded border border-gray-200 px-1 py-0.5 text-right text-xs text-gray-700"
                    />
                    {supplyChange !== null && supplyChange !== 0 ? (
                      <span className="font-medium text-amber-600">
                        {t('apps:mealInvoiceOcr.supplyChangeSuffix', {
                          delta: formatSignedDelta(supplyChange),
                        })}
                      </span>
                    ) : null}
                  </span>
                </div>
                {rowSum !== null ? (
                  <span className="flex items-center gap-1 text-gray-500">
                    {t('apps:mealInvoiceOcr.itemsSum')}
                    <span className="font-semibold tabular-nums text-gray-900">
                      {Math.round(rowSum).toLocaleString()}
                    </span>
                  </span>
                ) : null}
                {supplyMatchesSum !== null ? (
                  <span
                    className={`rounded px-2.5 py-1 text-sm font-semibold ${
                      supplyMatchesSum
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-red-50 text-red-700'
                    }`}
                  >
                    {supplyMatchesSum
                      ? t('apps:mealInvoiceOcr.supplyMatch')
                      : t('apps:mealInvoiceOcr.supplyMismatch', {
                          diff: formatSignedDelta(supplyVsSumDiff ?? 0),
                        })}
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={() => removeDocument(docIndex)}
                  title={t('apps:mealInvoiceOcr.actions.removeDoc')}
                  className="ml-auto flex items-center gap-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:border-red-300 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {t('apps:mealInvoiceOcr.actions.removeDoc')}
                </button>
              </div>

              <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
                <div className="min-w-0 flex-1 overflow-x-auto lg:order-3">
                {/* 컬럼 헤더(문서마다 1회). 컬럼이 많아 가로 스크롤되며 행과 같은 최소 폭을 쓴다. */}
                <div className="flex min-w-[58rem] items-center gap-2 border-b border-gray-200 px-2 pb-1 text-[10px] uppercase tracking-wide text-gray-400">
                  <span className="w-5 shrink-0" />
                  <span className="w-7 shrink-0" />
                  <span className="w-6 shrink-0" />
                  <span className={`${META_WIDTH.no} text-center`}>
                    {t('apps:mealInvoiceOcr.table.no')}
                  </span>
                  <span className={META_WIDTH.원산지}>
                    {t('apps:mealInvoiceOcr.table.origin')}
                  </span>
                  {ROW_FIELDS.map((field) => {
                    // 수량 칸은 [숫자][단위 드롭다운] 이 합쳐져 있으니 헤더도 수량/단위로 나눠 정렬한다.
                    if (field === '수량') {
                      return (
                        <div
                          key={field}
                          className={`${FIELD_WIDTH[field]} flex items-center gap-0.5`}
                        >
                          <span className="min-w-0 flex-1 text-center">
                            {t('apps:mealInvoiceOcr.table.unit')}
                          </span>
                          <span className="w-11 shrink-0 text-right">
                            {t('apps:mealInvoiceOcr.table.qty')}
                          </span>
                        </div>
                      );
                    }
                    return (
                      <span
                        key={field}
                        className={`${FIELD_WIDTH[field]} ${
                          NUMERIC_FIELDS.has(field) ? 'text-right' : ''
                        }`}
                      >
                        {t(`apps:mealInvoiceOcr.table.${FIELD_LABEL[field]}`)}
                      </span>
                    );
                  })}
                  {META_SELECTS.map((m) => (
                    <span key={m.key} className={`${m.width} text-center`}>
                      {t(`apps:mealInvoiceOcr.table.${m.label}`)}
                    </span>
                  ))}
                  <span className={META_WIDTH.비고}>
                    {t('apps:mealInvoiceOcr.table.note')}
                  </span>
                </div>

                <div className="flex min-w-[58rem] flex-col gap-1 pt-1">
                  {doc.품목.map((row, rowIndex) => {
                    const confirmed = row.확인여부 ?? false;
                    const dstyle = rowDragStyle(docIndex, rowIndex);
                    return (
                      <div
                        key={row._rid}
                        data-row
                        style={{
                          transform: dstyle.transform,
                          // 잡은 행은 손가락을 즉시 따라오도록 transition 제거(드래그 중).
                          // 놓을 때(settling)와 나머지 행은 부드럽게 이동.
                          transition:
                            suppressAnim || (dstyle.lifted && !drag?.settling)
                              ? 'none'
                              : 'transform 180ms ease',
                          zIndex: dstyle.z ? 30 : undefined,
                          position: 'relative',
                        }}
                        className={`flex items-center gap-2 rounded-md border px-2 py-1 ${
                          dstyle.lifted
                            ? 'scale-[1.01] border-blue-400 bg-white shadow-xl ring-2 ring-blue-300'
                            : confirmed
                              ? 'border-emerald-200 bg-emerald-50/40'
                              : 'border-gray-100 bg-white'
                        }`}
                      >
                        <span
                          role="button"
                          tabIndex={0}
                          aria-label={t('apps:mealInvoiceOcr.actions.reorder')}
                          onPointerDown={(e) =>
                            onGripPointerDown(e, docIndex, rowIndex, doc.품목.length)
                          }
                          onPointerMove={onGripPointerMove}
                          onPointerUp={endGripDrag}
                          onPointerCancel={endGripDrag}
                          onKeyDown={(e) => {
                            if (e.key === 'ArrowUp') {
                              e.preventDefault();
                              moveRow(docIndex, rowIndex, -1);
                            } else if (e.key === 'ArrowDown') {
                              e.preventDefault();
                              moveRow(docIndex, rowIndex, 1);
                            }
                          }}
                          title={t('apps:mealInvoiceOcr.actions.reorder')}
                          className="flex w-5 shrink-0 cursor-grab touch-none items-center justify-center self-center rounded text-gray-300 hover:bg-gray-100 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-400 active:cursor-grabbing"
                        >
                          <GripVertical className="h-4 w-4" />
                        </span>
                        <button
                          type="button"
                          onClick={() => toggleConfirm(docIndex, row._rid)}
                          title={t('apps:mealInvoiceOcr.table.confirm')}
                          className={`flex h-7 w-7 shrink-0 items-center justify-center self-center rounded border ${
                            confirmed
                              ? 'border-emerald-400 bg-emerald-500 text-white'
                              : 'border-gray-300 text-gray-300 hover:border-emerald-300 hover:text-emerald-500'
                          }`}
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => removeRow(docIndex, row._rid)}
                          title={t('apps:mealInvoiceOcr.actions.removeRow')}
                          className="flex w-6 shrink-0 items-center justify-center self-center rounded text-gray-300 hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                        <span
                          className={`${META_WIDTH.no} self-center text-center text-xs tabular-nums text-gray-400`}
                        >
                          {rowIndex + 1}
                        </span>
                        <div className={`${META_WIDTH.원산지} self-center`}>
                          {/* 목록(전체) 또는 직접 입력. 목록에 없는 값이거나 사용자가 '직접 입력'을 고르면 입력칸. */}
                          {customOriginRids.has(row._rid) ||
                          (row.원산지 && !ORIGIN_OPTIONS.includes(row.원산지)) ? (
                            <div className="flex items-center gap-0.5">
                              <input
                                autoFocus
                                aria-label={t('apps:mealInvoiceOcr.table.origin')}
                                value={row.원산지 ?? ''}
                                placeholder={t('apps:mealInvoiceOcr.table.origin')}
                                onChange={(e) =>
                                  updateRow(docIndex, row._rid, '원산지', e.target.value)
                                }
                                className="w-full rounded border border-blue-300 bg-blue-50/40 px-1.5 py-1 text-sm"
                              />
                              <button
                                type="button"
                                title={t('apps:mealInvoiceOcr.table.originFromList')}
                                onClick={() => {
                                  setCustomOriginRids((prev) => {
                                    const next = new Set(prev);
                                    next.delete(row._rid);
                                    return next;
                                  });
                                  updateRow(docIndex, row._rid, '원산지', '국내산');
                                }}
                                className="shrink-0 text-gray-300 hover:text-gray-600"
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          ) : (
                            <select
                              aria-label={t('apps:mealInvoiceOcr.table.origin')}
                              value={row.원산지 || '국내산'}
                              onChange={(e) => {
                                if (e.target.value === '__custom__') {
                                  setCustomOriginRids((prev) =>
                                    new Set(prev).add(row._rid),
                                  );
                                  updateRow(docIndex, row._rid, '원산지', '');
                                } else {
                                  updateRow(docIndex, row._rid, '원산지', e.target.value);
                                }
                              }}
                              className="app-field-input-sm px-1"
                            >
                              {ORIGIN_OPTIONS.map((opt) => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                              <option value="__custom__">
                                {t('apps:mealInvoiceOcr.table.originCustom')}
                              </option>
                            </select>
                          )}
                        </div>
                        {ROW_FIELDS.map((field) => {
                          const changed = row[field] !== row._orig[field];
                          const numeric = NUMERIC_FIELDS.has(field);
                          // 수량: 숫자 입력 + 단위 드롭다운으로 분리(값은 "30K"처럼 합쳐 저장).
                          if (field === '수량') {
                            const raw = row.수량 ?? '';
                            const { num, unit } = splitQty(raw);
                            const unitInList = allUnits.includes(unit);
                            const setQty = (n: string, u: string) =>
                              updateRow(docIndex, row._rid, '수량', joinQty(n, u));
                            // 과거 이력 단위 중 현재 OCR 단위와 다른 것 하나만 칩으로 제시한다.
                            // 목록(빈도 내림차순)의 첫 번째, 즉 이 품목에서 가장 많이 쓰인 단위다.
                            // 여러 개를 늘어놓으면 행마다 3~4줄이 붙어 표를 읽기 어렵고, 나머지 단위는
                            // 어차피 옆 드롭다운에서 고를 수 있다. 허용 목록 밖 값('단위', 'epak' 처럼
                            // 대장에 잘못 적힌 표기)은 enforceUnit 이 걸러낸다.
                            const currentUnitKey = canonicalUnit(unit).trim().toLowerCase();
                            const unitCandidates: string[] = [];
                            for (const cand of row.단위후보목록 ?? []) {
                              const allowed = enforceUnit(cand);
                              if (allowed && allowed.trim().toLowerCase() !== currentUnitKey) {
                                unitCandidates.push(allowed);
                                break;
                              }
                            }
                            return (
                              <div key={field} className={`${FIELD_WIDTH[field]} self-center`}>
                                <div className="flex items-center gap-0.5">
                                  {customUnitRids.has(row._rid) ? (
                                    <input
                                      autoFocus
                                      aria-label={t('apps:mealInvoiceOcr.table.unit')}
                                      value={unit}
                                      placeholder={t('apps:mealInvoiceOcr.table.unit')}
                                      onChange={(e) => setQty(num, normUnit(e.target.value.toLowerCase()))}
                                      onBlur={() => {
                                        setQty(num, enforceUnit(unit));
                                        // '직접입력'도 허용 10개(+별칭)만 인정하고 그 외에는 빈칸으로 둔다.
                                        setCustomUnitRids((prev) => {
                                          const next = new Set(prev);
                                          next.delete(row._rid);
                                          return next;
                                        });
                                      }}
                                      className="min-w-0 flex-1 rounded border border-blue-300 bg-blue-50/40 px-1 py-1 text-sm"
                                    />
                                  ) : (
                                    <select
                                      aria-label={t('apps:mealInvoiceOcr.table.unit')}
                                      value={unit}
                                      onChange={(e) => {
                                        const v = e.target.value;
                                        if (v === '__custom__') {
                                          setCustomUnitRids((prev) =>
                                            new Set(prev).add(row._rid),
                                          );
                                        } else {
                                          setQty(num, v);
                                        }
                                      }}
                                      className="app-field-input-sm min-w-0 flex-1 px-0.5"
                                    >
                                      {allUnits.map((u) => (
                                        <option key={u || '_none'} value={u}>
                                          {u || '—'}
                                        </option>
                                      ))}
                                      {!unitInList && unit ? (
                                        <option value={unit}>{unit}</option>
                                      ) : null}
                                      <option value="__custom__">
                                        {t('apps:mealInvoiceOcr.table.originCustom')}
                                      </option>
                                    </select>
                                  )}
                                  <input
                                    aria-label={t('apps:mealInvoiceOcr.table.qty')}
                                    value={num}
                                    inputMode="numeric"
                                    onChange={(e) =>
                                      setQty(e.target.value.replace(/[^\d.,]/g, ''), unit)
                                    }
                                    className={`w-11 shrink-0 rounded border px-1 py-1 text-right text-sm ${
                                      changed ? 'border-amber-300 bg-amber-50' : 'border-gray-200'
                                    }`}
                                  />
                                </div>
                                {changed && row._orig[field] ? (
                                  <span
                                    className="block truncate text-[10px] text-gray-400 line-through"
                                    title={row._orig[field]}
                                  >
                                    {row._orig[field]}
                                  </span>
                                ) : null}
                                {/* 과거 이력 단위(빈도순) 중 현재 OCR 단위와 다른 것만 칩으로. 클릭 시 교체. */}
                                {unitCandidates.map((u) => (
                                  <button
                                    key={u}
                                    type="button"
                                    onClick={() => setQty(num, u)}
                                    title={t('apps:mealInvoiceOcr.catalog.suggestHint')}
                                    className="mt-0.5 block max-w-full truncate rounded bg-teal-50 px-1.5 py-0.5 text-left text-[10px] text-teal-700 hover:bg-teal-100"
                                  >
                                    {t('apps:mealInvoiceOcr.catalog.unitSuggest', { unit: u })}
                                  </button>
                                ))}
                              </div>
                            );
                          }
                          return (
                            <div key={field} className={`${FIELD_WIDTH[field]} self-center`}>
                              <input
                                aria-label={t(`apps:mealInvoiceOcr.table.${FIELD_LABEL[field]}`)}
                                value={row[field]}
                                onChange={(e) =>
                                  updateRow(docIndex, row._rid, field, e.target.value)
                                }
                                className={`w-full rounded border px-2 py-1 text-sm ${
                                  numeric ? 'text-right' : ''
                                } ${
                                  changed
                                    ? 'border-amber-300 bg-amber-50'
                                    : 'border-gray-200'
                                }`}
                              />
                              {changed && row._orig[field] ? (
                                <span
                                  className="block truncate text-[10px] text-gray-400 line-through"
                                  title={row._orig[field]}
                                >
                                  {row._orig[field]}
                                </span>
                              ) : null}
                              {field === '품명' &&
                              row.사전후보 &&
                              row.사전후보 !== row.품명 ? (
                                <button
                                  type="button"
                                  onClick={() =>
                                    updateRow(docIndex, row._rid, '품명', row.사전후보 ?? '')
                                  }
                                  title={t('apps:mealInvoiceOcr.dictSuggestHint')}
                                  className="mt-0.5 block max-w-full truncate rounded bg-indigo-50 px-1.5 py-0.5 text-left text-[10px] text-indigo-600 hover:bg-indigo-100"
                                >
                                  {t('apps:mealInvoiceOcr.dictSuggest', {
                                    name: row.사전후보,
                                  })}
                                </button>
                              ) : null}
                            </div>
                          );
                        })}
                        {META_SELECTS.map((m) => (
                          <div key={m.key} className={`${m.width} self-center`}>
                            <select
                              aria-label={t(`apps:mealInvoiceOcr.table.${m.label}`)}
                              value={row[m.key] || m.opts[0]}
                              onChange={(e) =>
                                updateRow(docIndex, row._rid, m.key, e.target.value)
                              }
                              className="app-field-input-sm px-1 text-center"
                            >
                              {m.opts.map((opt) => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                            </select>
                          </div>
                        ))}
                        <div className={`${META_WIDTH.비고} self-center`}>
                          <input
                            aria-label={t('apps:mealInvoiceOcr.table.note')}
                            value={row.비고 ?? ''}
                            onChange={(e) =>
                              updateRow(docIndex, row._rid, '비고', e.target.value)
                            }
                            className="w-full rounded border border-gray-200 px-2 py-1 text-sm"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={() => addRow(docIndex)}
                  className="mt-1 inline-flex w-fit items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                >
                  <Plus className="h-3.5 w-3.5" />
                  {t('apps:mealInvoiceOcr.actions.addRow')}
                </button>
                </div>

                {/* 원본 페이지 이미지: 왼쪽 열, 스크롤해도 따라오도록 sticky. 좁아지면 뷰어 확대/드래그로 확인. */}
                {doc.페이지이미지 ? (
                  <>
                    <InvoiceImageViewer
                      src={doc.페이지이미지}
                      alt={t('apps:mealInvoiceOcr.table.original')}
                      widthPct={imageWidthPct}
                      onRotate={() => void rotateDocImage(docIndex)}
                      onEnlarge={() => openPageImageNewWindow(doc.페이지이미지 ?? '')}
                    />
                    {/* 사진↔표 분할선: 드래그해서 좌우 폭 조절(lg 이상에서만 표시). */}
                    <div
                      onMouseDown={onSplitterDown}
                      title={t('apps:mealInvoiceOcr.actions.resizeHint')}
                      className="hidden self-stretch lg:order-2 lg:flex lg:w-3 lg:cursor-col-resize lg:items-center lg:justify-center"
                    >
                      <span className="h-16 w-1 rounded bg-gray-300 transition-colors hover:bg-blue-400" />
                    </div>
                  </>
                ) : null}
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
