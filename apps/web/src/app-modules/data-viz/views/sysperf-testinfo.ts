// 시험정보(공통/파일별) + 부품 상태 — 파일 업로드 탭(편집)과 데이터 표 탭(DB화)이 공유.
import type {
  SysPerfTestInfoItem,
  SysPerfUploadedFile,
} from '../api/dataviz-api';
import { emptyPartsState, type PartsState } from './sysperf-parts-state';

export interface CommonInfo {
  car_code: string;
  car_type: string;
  engine: string;
  stage: string;
  car_number: string;
}
export interface FileInfo {
  test_item: string;
  test_date: string;
  refrigerant_charge: string;
  lot_no: string;
}
export interface TestInfoState {
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
  parts: Record<number, PartsState>;
}

export const EMPTY_FILE_INFO: FileInfo = {
  test_item: '',
  test_date: '',
  refrigerant_charge: '',
  lot_no: '',
};
export const EMPTY_COMMON: CommonInfo = {
  car_code: '',
  car_type: '',
  engine: '',
  stage: '',
  car_number: '',
};

// 권장 파일명 양식 "시험일자_차종_LOT NO_사양_시험항목_냉매 충진량_비고" 분해.
// '_' 가 없으면 null → 백엔드 auto_match(정규식) 폴백.
export function parseUnderscoreName(filename: string): {
  test_date: string;
  car_code: string;
  lot_no: string;
  spec: string;
  test_item: string;
  refrigerant_charge: string;
  note: string;
} | null {
  const base = filename.replace(/\.(xlsx?|csv)$/i, '').trim();
  if (!base.includes('_')) return null;
  const p = base.split('_').map((s) => s.trim());
  return {
    test_date: p[0] || '',
    car_code: p[1] || '',
    lot_no: p[2] || '',
    spec: p[3] || '',
    test_item: p[4] || '',
    refrigerant_charge: p[5] || '',
    note: p.slice(6).join('_') || '',
  };
}

// 업로드 파일들 → 시험정보 초기 시드 (파일명 분해 우선, 없으면 auto_match).
export function seedTestInfo(validFiles: SysPerfUploadedFile[]): TestInfoState {
  const am0 = validFiles[0]?.auto_match || {};
  const un0 = validFiles[0]
    ? parseUnderscoreName(validFiles[0].filename)
    : null;
  const common: CommonInfo = {
    car_code: un0?.car_code || (am0.car_code as string) || '',
    car_type: '',
    engine: '',
    stage: '',
    car_number: '',
  };
  const perFile: Record<number, FileInfo> = {};
  const parts: Record<number, PartsState> = {};
  validFiles.forEach((f) => {
    if (f.file_id == null) return;
    const am = f.auto_match || {};
    const un = parseUnderscoreName(f.filename);
    perFile[f.file_id] = {
      test_item: un?.test_item || (am.test_item as string) || '',
      test_date: un?.test_date || (am.test_date as string) || '',
      refrigerant_charge:
        un?.refrigerant_charge || (am.refrigerant_charge as string) || '',
      lot_no: un?.lot_no || '',
    };
    const s = emptyPartsState();
    if (am.comp) s.comp = { ...s.comp, direct: am.comp as string };
    if (am.txv) s.txv = { ...s.txv, direct: am.txv as string };
    if (am.condenser)
      s.condenser = { ...s.condenser, direct: am.condenser as string };
    parts[f.file_id] = s;
  });
  return { common, perFile, parts };
}

export function buildSysPerfTestInfoItems({
  files,
  common,
  perFile,
}: {
  files: SysPerfUploadedFile[];
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
}): SysPerfTestInfoItem[] {
  return files.flatMap((file) => {
    const fileId = file.file_id;
    if (fileId == null) return [];
    const fileInfo = perFile[fileId] || EMPTY_FILE_INFO;
    return (file.sheets || []).map((sheet) => ({
      file_id: fileId,
      sheet_name: sheet.sheet_name,
      car_model: common.car_code,
      spec: '',
      test_item: fileInfo.test_item,
      test_date: fileInfo.test_date,
      lot_no: fileInfo.lot_no,
      refrigerant: fileInfo.refrigerant_charge,
      note: '',
    }));
  });
}
