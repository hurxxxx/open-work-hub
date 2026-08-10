import {
  apiFetchJson,
  ApiRequestError,
  jsonHeaders,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

const CATEGORY_API = {
  variable: '\uac00\ubcc0',
  electric: '\uc804\ub3d9',
} as const;

const REFRIGERANT_API = {
  new: '\uc2e0\ub0c9\ub9e4',
  old: '\uad6c\ub0c9\ub9e4',
} as const;

export type PerfCategory = keyof typeof CATEGORY_API;
export type PerfRefrigerant = keyof typeof REFRIGERANT_API;
export type PerfCategoryApi = (typeof CATEGORY_API)[PerfCategory];
export type PerfRefrigerantApi = (typeof REFRIGERANT_API)[PerfRefrigerant];

export const VARIABLE_CAPACITIES = [
  '122cc',
  '130cc',
  '140cc',
  '155cc',
  '160cc',
  '180cc',
  '190cc',
  'Benchmark',
] as const;
export const ELECTRIC_CAPACITIES = [
  '19\ucc28\uc218',
  '21\ucc28\uc218',
] as const;

export interface DataVizSpec {
  raw: string;
  nominal: number | null;
  lsl: number | null;
  usl: number | null;
}

export interface DataVizItem {
  item: string;
  spec: DataVizSpec;
  count: number;
}

export interface DataVizGroup {
  id: string;
  file: string;
  sheet: string;
  model: string;
  items: DataVizItem[];
}

export interface DataVizPoint {
  index: number;
  value: number;
  date: string | null;
}

export interface DataVizSeries {
  id: string;
  model: string;
  sheet: string;
  item: string;
  spec: DataVizSpec;
  points: DataVizPoint[];
}

export interface PerfRow {
  id?: string;
  category?: string;
  refrigerant?: string;
  capacity?: string;
  test_group: string;
  comp_type: string;
  serial_no: string;
  test_date: string;
  car_model: string;
  engine_spec: string;
  remarks: string;
  source_file: string;
  rpm: number | null;
  pd: number | null;
  td: number | null;
  ps: number | null;
  ts: number | null;
  pc: number | null;
  mass_flow: number | null;
  vol_eff: number | null;
  ocr: number | null;
  cooling_cap_a: number | null;
  cooling_cap_f: number | null;
  power_kw: number | null;
  cop_sc: number | null;
  heat_balance: number | null;
  torque: number | null;
  // 항목별 경고 종류: 'ref'=승인도 기준값 위반(주황 셀), 'tol'=시험공차 위반(빨간 글자)
  warnings?: Record<string, 'ref' | 'tol'>;
  no_ref?: boolean;
}

export interface PerfAverage {
  test_group: string;
  comp_type?: string;
  count: number;
  [field: string]: number | string | null | undefined;
}

export interface PerfParseResult {
  category: string;
  file_count: number;
  row_count: number;
  rows: PerfRow[];
  averages: PerfAverage[];
}

export interface PerfMasterUploadResult {
  ok: boolean;
  filename: string;
  category: string;
  imported_sheets: string[];
  row_count: number;
}

export interface PerfSourceUploadItem {
  filename: string;
  status: 'ok' | 'duplicate' | 'error';
  row_count: number;
  warning_count: number;
  error?: string;
  rows: Array<Partial<PerfRow> & { warnings?: Record<string, 'ref' | 'tol'> }>;
}

export interface PerfSourceUploadResult {
  status: string;
  success_count: number;
  results: PerfSourceUploadItem[];
}

export interface PerfDataResponse {
  data: PerfRow[];
}

export interface PerfAnalysisResult {
  averages: PerfAverage[];
  comp_averages: PerfAverage[];
  latest: PerfRow[];
}

export interface ToleranceResponse {
  ref_values: Record<string, Record<string, number | null>>;
  car_models: string[];
  profiles: string[];
}

export interface ToleranceAllResponse {
  models: Record<string, Record<string, Record<string, number | null>>>;
  cap_models: Record<string, { capacity: string; model: string }>;
}

export type TolSign = '±' | '+' | '-' | '편측';

// 시험공차 프로필의 셀 — 기준값(ref) 기준.
// sign 이 ±/+/- 이면 tol 이 공차폭(lower 미사용).
// sign 이 '편측'이면 tol = 상한(+) 편차, lower = 하한(-) 편차.
export interface ProfileTolCell {
  ref: number | null;
  sign: TolSign;
  tol: number | null;
  lower: number | null;
}

export interface ToleranceProfileResponse {
  tol_data: Record<string, Record<string, ProfileTolCell>>;
  cars: string[];
  profiles: string[];
}

export function apiCategory(category: PerfCategory): PerfCategoryApi {
  return CATEGORY_API[category];
}

export function apiRefrigerant(
  refrigerant: PerfRefrigerant,
): PerfRefrigerantApi {
  return REFRIGERANT_API[refrigerant];
}

export function capacitiesForCategory(
  category: PerfCategory,
): readonly string[] {
  return category === 'electric' ? ELECTRIC_CAPACITIES : VARIABLE_CAPACITIES;
}

export function listCoreMeasurementGroups(
  token: string,
  workspaceSlug: string,
): Promise<DataVizGroup[]> {
  return apiFetchJson<DataVizGroup[]>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/core-measurement/groups',
      workspaceSlug,
    ),
    token,
  );
}

export function getCoreMeasurementSeries(
  token: string,
  workspaceSlug: string,
  groupId: string,
  item: string,
): Promise<DataVizSeries> {
  const query = new URLSearchParams({ group_id: groupId, item }).toString();
  return apiFetchJson<DataVizSeries>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/core-measurement/series?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function parseCompressorPerf(
  token: string,
  workspaceSlug: string,
  files: File[],
  category: PerfCategory,
): Promise<PerfParseResult> {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  form.append('category', apiCategory(category));
  return apiFetchJson<PerfParseResult>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/parse',
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: form },
  );
}

export function uploadCompressorPerfMaster(
  token: string,
  workspaceSlug: string,
  file: File,
  category: PerfCategory,
): Promise<PerfMasterUploadResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('category', apiCategory(category));
  return apiFetchJson<PerfMasterUploadResult>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/upload-master',
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: form },
  );
}

export function uploadCompressorPerfSources(
  token: string,
  workspaceSlug: string,
  files: File[],
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
): Promise<PerfSourceUploadResult> {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  form.append('category', apiCategory(category));
  form.append('refrigerant', apiRefrigerant(refrigerant));
  form.append('capacity', capacity);
  return apiFetchJson<PerfSourceUploadResult>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/upload-sources',
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: form },
  );
}

export function listCompressorPerfData(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
): Promise<PerfDataResponse> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
  }).toString();
  return apiFetchJson<PerfDataResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/data?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function getCompressorPerfAnalysis(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
): Promise<PerfAnalysisResult> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
  }).toString();
  return apiFetchJson<PerfAnalysisResult>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/analysis?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function resetCompressorPerfData(
  token: string,
  workspaceSlug: string,
  category: PerfCategory | null,
): Promise<{ status: string }> {
  return apiFetchJson<{ status: string }>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/reset',
      workspaceSlug,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        category: category ? apiCategory(category) : null,
      }),
    },
  );
}

export function deleteCompressorPerfRow(
  token: string,
  workspaceSlug: string,
  rowId: string,
): Promise<{ status: string }> {
  return apiFetchJson<{ status: string }>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/data/${rowId}`,
      workspaceSlug,
    ),
    token,
    { method: 'DELETE' },
  );
}

export function getTolerance(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
  carModel: string,
): Promise<ToleranceResponse> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
    car_model: carModel,
  }).toString();
  return apiFetchJson<ToleranceResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/tolerance?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function getToleranceAll(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity = '',
): Promise<ToleranceAllResponse> {
  const params: Record<string, string> = {
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
  };
  if (capacity) params.capacity = capacity;
  const query = new URLSearchParams(params).toString();
  return apiFetchJson<ToleranceAllResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/tolerance/all?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function saveTolerance(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
  carModel: string,
  refValues: Record<string, Record<string, number | null>>,
): Promise<{ status: string }> {
  return apiFetchJson<{ status: string }>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/tolerance',
      workspaceSlug,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        category: apiCategory(category),
        refrigerant: apiRefrigerant(refrigerant),
        capacity,
        car_model: carModel,
        ref_values: refValues,
      }),
    },
  );
}

export function uploadToleranceFile(
  token: string,
  workspaceSlug: string,
  file: File,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
): Promise<{ status: string; inserted: number; filename: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('category', apiCategory(category));
  form.append('refrigerant', apiRefrigerant(refrigerant));
  return apiFetchJson<{ status: string; inserted: number; filename: string }>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/tolerance/upload',
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: form },
  );
}

export function getToleranceProfile(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
  profile: string,
): Promise<ToleranceProfileResponse> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
    profile,
  }).toString();
  return apiFetchJson<ToleranceProfileResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/tol-profile?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export interface ToleranceProfileAllResponse {
  profiles: Record<string, Record<string, Record<string, ProfileTolCell>>>;
}

export function getToleranceProfileAll(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
): Promise<ToleranceProfileAllResponse> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
  }).toString();
  return apiFetchJson<ToleranceProfileAllResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/tol-profile/all?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function saveToleranceProfile(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
  profile: string,
  tolData: Record<string, Record<string, ProfileTolCell>>,
  cars: string[],
): Promise<{ status: string }> {
  return apiFetchJson<{ status: string }>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/compressor-perf/tol-profile',
      workspaceSlug,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        category: apiCategory(category),
        refrigerant: apiRefrigerant(refrigerant),
        capacity,
        profile,
        tol_data: tolData,
        cars,
      }),
    },
  );
}

export async function downloadCompressorPerfData(
  token: string,
  workspaceSlug: string,
  category: PerfCategory,
  refrigerant: PerfRefrigerant,
  capacity: string,
  allRefrigerant: boolean,
): Promise<Blob> {
  const query = new URLSearchParams({
    category: apiCategory(category),
    refrigerant: apiRefrigerant(refrigerant),
    capacity,
    all_refrigerant: allRefrigerant ? '1' : '0',
    no_warning_color: '1',
  }).toString();
  const response = await fetch(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/compressor-perf/download-data?${query}`,
      workspaceSlug,
    ),
    { headers: jsonHeaders(token), cache: 'no-store' },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed with ${response.status}.`,
      payload,
    );
  }
  return response.blob();
}

// ═══ 컴프 신뢰성 (복합내구 + 간이벤치) ═══

export interface DurabilityColSeries {
  x: number[];
  y: (number | null)[];
}

export interface DurabilityGraphResponse {
  status: string;
  data: Record<string, DurabilityColSeries>;
  columns: string[];
  total_rows: number;
  sampled_points?: number;
  original_rows?: number;
  slice_start?: number;
  slice_end?: number;
  type?: string;
  machine?: string;
  error?: string;
}

export interface DurabilityUploadResponse {
  status: string;
  file_count: number;
  total_rows: number;
  columns: number;
  column_names: string[];
  fix_row1: number;
  fix_row2: number;
  channel_signal_map: Record<string, string>;
  error?: string;
}

export function uploadDurability(
  token: string,
  workspaceSlug: string,
  files: File[],
  opts: {
    type: string;
    machine: string;
    testItem: string;
    fixRow1?: number;
    fixRow2?: number;
    autoDetect?: boolean;
  },
): Promise<DurabilityUploadResponse> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  form.append('type', opts.type);
  form.append('machine', opts.machine);
  form.append('test_item', opts.testItem);
  form.append('fix_row1', String(opts.fixRow1 ?? 0));
  form.append('fix_row2', String(opts.fixRow2 ?? 0));
  if (opts.autoDetect) form.append('auto_detect', '1');
  return apiFetchJson<DurabilityUploadResponse>(
    rewriteWorkspaceApiPath(
      '/api/v1/dataviz/comp-reliability/durability-upload',
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: form },
  );
}

// 업로드 진행률(%)이 필요해 fetch 대신 XHR 사용 — xhr.upload.onprogress.
// onProgress 는 0~99(업로드 중), 업로드 완료 후 100(서버 파싱 시작) 으로 콜백.
export function uploadDurabilityWithProgress(
  token: string,
  workspaceSlug: string,
  files: File[],
  opts: {
    type: string;
    machine: string;
    testItem: string;
    fixRow1?: number;
    fixRow2?: number;
    autoDetect?: boolean;
  },
  onProgress?: (percent: number) => void,
): Promise<DurabilityUploadResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    form.append('type', opts.type);
    form.append('machine', opts.machine);
    form.append('test_item', opts.testItem);
    form.append('fix_row1', String(opts.fixRow1 ?? 0));
    form.append('fix_row2', String(opts.fixRow2 ?? 0));
    if (opts.autoDetect) form.append('auto_detect', '1');

    const xhr = new XMLHttpRequest();
    xhr.open(
      'POST',
      rewriteWorkspaceApiPath(
        '/api/v1/dataviz/comp-reliability/durability-upload',
        workspaceSlug,
      ),
    );
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('Accept', 'application/json');

    // 진행 표시 — 로컬에선 네트워크 전송이 거의 즉시라, 실제 시간 대부분은 서버
    // 파싱이다. 전송은 0~40% 로 매핑하고, 전송 완료 후엔 파일당 ~1.8초로 추정한
    // 시간 기반 시뮬레이션으로 40→95% 를 부드럽게 채운다(응답 오면 100%).
    const estimateMs = Math.max(2500, files.length * 1800);
    let simTimer: ReturnType<typeof setInterval> | null = null;
    const stopSim = () => {
      if (simTimer != null) {
        clearInterval(simTimer);
        simTimer = null;
      }
    };
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.min(40, Math.round((e.loaded / e.total) * 40)));
      }
    };
    xhr.upload.onload = () => {
      // 네트워크 전송 완료 → 서버 파싱 구간 시뮬레이션 시작 (40→95%).
      const startedAt = Date.now();
      onProgress?.(40);
      simTimer = setInterval(() => {
        const frac = Math.min(1, (Date.now() - startedAt) / estimateMs);
        onProgress?.(Math.min(95, 40 + Math.round(frac * 55)));
      }, 200);
    };
    xhr.onload = () => {
      stopSim();
      onProgress?.(100);
      let data: DurabilityUploadResponse | null = null;
      try {
        data = JSON.parse(xhr.responseText) as DurabilityUploadResponse;
      } catch {
        reject(
          new ApiRequestError(
            xhr.status,
            i18n.t('apps:ai.dataViz.errors.parseResponse'),
            null,
          ),
        );
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else {
        const detail = (data as unknown as { detail?: string })?.detail;
        reject(
          new ApiRequestError(
            xhr.status,
            typeof detail === 'string'
              ? detail
              : `Request failed with ${xhr.status}.`,
            data,
          ),
        );
      }
    };
    xhr.onerror = () => {
      stopSim();
      reject(
        new ApiRequestError(0, i18n.t('apps:ai.dataViz.errors.network'), null),
      );
    };
    xhr.send(form);
  });
}

export function getDurabilityGraph(
  token: string,
  workspaceSlug: string,
  opts: {
    type: string;
    machine: string;
    testItem: string;
    cols?: string;
    maxPoints?: number;
  },
): Promise<DurabilityGraphResponse> {
  const query = new URLSearchParams({
    type: opts.type,
    machine: opts.machine,
    test_item: opts.testItem,
    cols: opts.cols ?? '__ALL__',
    max_points: String(opts.maxPoints ?? 5000),
  }).toString();
  return apiFetchJson<DurabilityGraphResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/comp-reliability/durability-graph?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

export function getDurabilityGraphElec(
  token: string,
  workspaceSlug: string,
  opts: {
    type: string;
    machine: string;
    testItem: string;
    cols: string;
    xMode: string;
    xParam: string;
    maxPoints?: number;
  },
): Promise<DurabilityGraphResponse> {
  const query = new URLSearchParams({
    type: opts.type,
    machine: opts.machine,
    test_item: opts.testItem,
    cols: opts.cols,
    x_mode: opts.xMode,
    x_param: opts.xParam,
    max_points: String(opts.maxPoints ?? 5000),
  }).toString();
  return apiFetchJson<DurabilityGraphResponse>(
    rewriteWorkspaceApiPath(
      `/api/v1/dataviz/comp-reliability/durability-graph-elec?${query}`,
      workspaceSlug,
    ),
    token,
  );
}

// ═══════════════════════════════════════════════════════════
//  시스템 성능 (sys-perf)
// ═══════════════════════════════════════════════════════════

const SP_BASE = '/api/v1/dataviz/sys-perf';

function spPath(workspaceSlug: string, path: string): string {
  return rewriteWorkspaceApiPath(`${SP_BASE}${path}`, workspaceSlug);
}

export interface SysPerfSheetInfo {
  sheet_name: string;
  info_text: string;
  headers: string[];
  header_count: number;
  header_row: number;
  info_row: number;
  header_numeric_counts: Record<string, number>;
}

export interface SysPerfPartsSpecRef {
  id: number;
  name: string;
  car_code: string;
  comp: string;
  condenser: string;
  txv: string;
  hvac: string;
  pipe: string;
  refrigerant_charge: string;
  note: string;
}

export interface SysPerfAutoMatch {
  car_code?: string;
  car_model?: string;
  segment?: string;
  comp?: string;
  txv?: string;
  condenser?: string;
  refrigerant_charge?: string;
  test_item?: string;
  test_date?: string;
  parts_specs?: SysPerfPartsSpecRef[];
  [k: string]: unknown;
}

export interface SysPerfUploadedFile {
  file_id?: number;
  filename: string;
  sheets?: SysPerfSheetInfo[];
  all_sheets?: string[];
  auto_match?: SysPerfAutoMatch;
  error?: string;
}

export interface SysPerfUploadResponse {
  status: string;
  files: SysPerfUploadedFile[];
}

export function sysPerfUpload(
  token: string,
  workspaceSlug: string,
  files: File[],
): Promise<SysPerfUploadResponse> {
  const form = new FormData();
  for (const f of files) form.append('files', f);
  return apiFetchJson<SysPerfUploadResponse>(
    spPath(workspaceSlug, '/upload'),
    token,
    { method: 'POST', body: form },
  );
}

export interface SysPerfTestInfoItem {
  file_id: number;
  sheet_name: string;
  car_model: string;
  spec: string;
  test_item: string;
  test_date: string;
  lot_no: string;
  refrigerant: string;
  note: string;
}

export function sysPerfSaveTestInfo(
  token: string,
  workspaceSlug: string,
  items: SysPerfTestInfoItem[],
): Promise<{ status: string }> {
  return apiFetchJson<{ status: string }>(
    spPath(workspaceSlug, '/test-info'),
    token,
    {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ items }),
    },
  );
}

export interface SysPerfMatchedStandard {
  id: number;
  standard_name: string;
  unit: string;
  category: string;
  display_order: number;
}

export interface SysPerfAutoMatchResult {
  col_index: number;
  original_name: string;
  matched: SysPerfMatchedStandard | null;
}

export function sysPerfAutoMatch(
  token: string,
  workspaceSlug: string,
  fileId: number,
  headers: string[],
): Promise<{ status: string; matches: SysPerfAutoMatchResult[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/auto-match'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ file_id: fileId, headers }),
  });
}

export interface SysPerfMapping {
  original_name: string;
  standard_name: string;
  col_index: number;
}

export function sysPerfConfirmMatch(
  token: string,
  workspaceSlug: string,
  fileId: number,
  sheetName: string,
  mappings: SysPerfMapping[],
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, '/confirm-match'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({
      file_id: fileId,
      sheet_name: sheetName,
      mappings,
    }),
  });
}

export interface SysPerfSheetData {
  status?: string;
  columns: string[];
  data: Record<string, (number | null)[]>;
  total_rows: number;
  error?: string;
}

export function sysPerfSheetData(
  token: string,
  workspaceSlug: string,
  fileId: number,
  sheet: string,
  maxRows = 5000,
): Promise<SysPerfSheetData> {
  const q = new URLSearchParams({
    file_id: String(fileId),
    sheet,
    max_rows: String(maxRows),
  }).toString();
  return apiFetchJson<SysPerfSheetData>(
    spPath(workspaceSlug, `/sheet-data?${q}`),
    token,
  );
}

export interface SysPerfGraphData {
  status?: string;
  data: Record<string, (number | null)[]>;
  units: Record<string, string>;
  total_rows: number;
  error?: string;
}

export function sysPerfGraphData(
  token: string,
  workspaceSlug: string,
  fileId: number,
  sheet: string,
  maxPts = 3000,
): Promise<SysPerfGraphData> {
  const q = new URLSearchParams({
    file_id: String(fileId),
    sheet,
    max_pts: String(maxPts),
  }).toString();
  return apiFetchJson<SysPerfGraphData>(
    spPath(workspaceSlug, `/graph-data?${q}`),
    token,
  );
}

export interface SysPerfCycleData {
  status?: string;
  time: number;
  row_index: number;
  cycle: Record<string, number | null>;
  enthalpy: Record<string, number | null>;
  entropy: Record<string, number | null>;
  sh_sc: Record<string, number>;
  mappings: Record<string, string>;
  isenthalpic_notes: string[];
  warnings: Record<string, string[]>;
  error?: string;
}

export function sysPerfCycleData(
  token: string,
  workspaceSlug: string,
  fileId: number,
  sheet: string,
  time: number | null,
  refrigerant: string,
): Promise<SysPerfCycleData> {
  const params: Record<string, string> = {
    file_id: String(fileId),
    sheet,
    refrigerant,
  };
  if (time != null) params.time = String(time);
  const q = new URLSearchParams(params).toString();
  return apiFetchJson<SysPerfCycleData>(
    spPath(workspaceSlug, `/cycle-data?${q}`),
    token,
  );
}

export interface SysPerfIsoline {
  [k: string]: unknown;
}

export interface SysPerfPhDiagram {
  status?: string;
  has_coolprop: boolean;
  refrigerant: string;
  saturation: { h: number[]; p: number[] };
  isotherms: { T?: number; h: number[]; p: number[] }[];
  isentropes: { s?: number; h: number[]; p: number[] }[];
  isoquality: { q?: number; h: number[]; p: number[] }[];
  isochor: { v?: number; h: number[]; p: number[] }[];
  critical: { T: number | null; P: number | null; h: number | null };
  coolprop_error?: string;
}

export function sysPerfPhDiagram(
  token: string,
  workspaceSlug: string,
  refrigerant: string,
  refrigerantId?: number | null,
): Promise<SysPerfPhDiagram> {
  const params: Record<string, string> = { refrigerant };
  if (refrigerantId) params.refrigerant_id = String(refrigerantId);
  const q = new URLSearchParams(params).toString();
  return apiFetchJson<SysPerfPhDiagram>(
    spPath(workspaceSlug, `/ph-diagram-data?${q}`),
    token,
  );
}

export interface SysPerfTsDiagram {
  status?: string;
  has_coolprop: boolean;
  refrigerant: string;
  saturation: { s: number[]; t: number[] };
  isobars: { P?: number; s: number[]; t: number[] }[];
  isenthalps: { h?: number; s: number[]; t: number[] }[];
  critical: { T: number | null; s: number | null; P: number | null };
  coolprop_error?: string;
}

export function sysPerfTsDiagram(
  token: string,
  workspaceSlug: string,
  refrigerant: string,
  refrigerantId?: number | null,
): Promise<SysPerfTsDiagram> {
  const params: Record<string, string> = { refrigerant };
  if (refrigerantId) params.refrigerant_id = String(refrigerantId);
  const q = new URLSearchParams(params).toString();
  return apiFetchJson<SysPerfTsDiagram>(
    spPath(workspaceSlug, `/ts-diagram-data?${q}`),
    token,
  );
}

// ── BASE 관리 ──
export interface SysPerfStandardColumn {
  id: number;
  standard_name: string;
  keywords: string;
  unit: string;
  category: string;
  display_order: number;
}

export function sysPerfGetColumns(
  token: string,
  workspaceSlug: string,
): Promise<{ data: SysPerfStandardColumn[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/columns'), token);
}

export function sysPerfSaveColumn(
  token: string,
  workspaceSlug: string,
  item: Partial<SysPerfStandardColumn> & { standard_name: string },
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/columns'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(item),
  });
}

export function sysPerfDeleteColumn(
  token: string,
  workspaceSlug: string,
  colId: number,
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, `/base/columns/${colId}`), token, {
    method: 'DELETE',
  });
}

export function sysPerfGetItemKeywords(
  token: string,
  workspaceSlug: string,
): Promise<{ data: { item_n: number; keywords: string }[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/item-keywords'), token);
}

export interface SysPerfRefrigerant {
  id: number;
  name: string;
  formula: string;
}

export function sysPerfGetRefrigerants(
  token: string,
  workspaceSlug: string,
): Promise<{ data: SysPerfRefrigerant[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/refrigerants'), token);
}

export function sysPerfSaveRefrigerant(
  token: string,
  workspaceSlug: string,
  item: { name: string; formula: string },
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/refrigerants'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(item),
  });
}

export interface SysPerfRefrigerantPropRow {
  id?: number;
  refrigerant_id?: number;
  temperature: number | null;
  sat_pressure_kgcm2: number | null;
  sat_pressure_kpa: number | null;
  sat_pressure_bar: number | null;
  liq_enthalpy: number | null;
  vap_enthalpy: number | null;
  liq_entropy: number | null;
  vap_entropy: number | null;
  liq_specific_vol: number | null;
  vap_specific_vol: number | null;
}

export function sysPerfGetRefrigerantProps(
  token: string,
  workspaceSlug: string,
  refrigerantId: number,
): Promise<{ data: SysPerfRefrigerantPropRow[] }> {
  const q = new URLSearchParams({
    refrigerant_id: String(refrigerantId),
  }).toString();
  return apiFetchJson(
    spPath(workspaceSlug, `/base/refrigerant-props?${q}`),
    token,
  );
}

export function sysPerfImportRefrigerantProps(
  token: string,
  workspaceSlug: string,
  refrigerantId: number,
  file: File,
): Promise<{
  status: string;
  count: number;
  sheet: string;
  col_map: Record<string, string>;
}> {
  const form = new FormData();
  form.append('file', file);
  form.append('refrigerant_id', String(refrigerantId));
  return apiFetchJson(
    spPath(workspaceSlug, '/base/refrigerant-props/import'),
    token,
    { method: 'POST', body: form },
  );
}

export function sysPerfImportStatePoints(
  token: string,
  workspaceSlug: string,
  refrigerantId: number,
  file: File,
): Promise<{ status: string; count: number }> {
  const form = new FormData();
  form.append('file', file);
  form.append('refrigerant_id', String(refrigerantId));
  return apiFetchJson(
    spPath(workspaceSlug, '/base/state-points/import'),
    token,
    { method: 'POST', body: form },
  );
}

export interface SysPerfCarModel {
  id: number;
  brand: string;
  era: string;
  year: string;
  car_name: string;
  model_code: string;
  segment_code: string;
  segment_name: string;
  refrigerant: string;
  note: string;
}

export interface SysPerfCarModelSavePayload {
  id?: number | null;
  brand: string;
  era: string;
  year: string;
  car_name: string;
  model_code: string;
  segment_code: string;
  segment_name: string;
  refrigerant: string;
  note: string;
}

export function sysPerfGetCarModels(
  token: string,
  workspaceSlug: string,
  filters: { brand?: string; era?: string; segment?: string; q?: string } = {},
): Promise<{ data: SysPerfCarModel[] }> {
  const q = new URLSearchParams();
  if (filters.brand) q.set('brand', filters.brand);
  if (filters.era) q.set('era', filters.era);
  if (filters.segment) q.set('segment', filters.segment);
  if (filters.q) q.set('q', filters.q);
  const qs = q.toString();
  return apiFetchJson(
    spPath(workspaceSlug, `/base/car-models${qs ? `?${qs}` : ''}`),
    token,
  );
}

export function sysPerfSaveCarModel(
  token: string,
  workspaceSlug: string,
  item: SysPerfCarModelSavePayload,
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/car-models'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(item),
  });
}

export function sysPerfDeleteCarModel(
  token: string,
  workspaceSlug: string,
  modelId: number,
): Promise<{ status: string }> {
  return apiFetchJson(
    spPath(workspaceSlug, `/base/car-models/${modelId}`),
    token,
    { method: 'DELETE' },
  );
}

export interface SysPerfPartsSpec {
  id: number;
  name: string;
  car_code: string;
  comp: string;
  comp_prod: number;
  condenser: string;
  cond_prod: number;
  txv: string;
  txv_prod: number;
  hvac: string;
  hvac_prod: number;
  pipe: string;
  pipe_prod: number;
  refrigerant_charge: string;
  note: string;
}

export function sysPerfGetPartsSpecs(
  token: string,
  workspaceSlug: string,
  carCode = '',
): Promise<{ data: SysPerfPartsSpec[] }> {
  const q = carCode
    ? `?${new URLSearchParams({ car_code: carCode }).toString()}`
    : '';
  return apiFetchJson(spPath(workspaceSlug, `/base/parts-spec${q}`), token);
}

export function sysPerfSavePartsSpec(
  token: string,
  workspaceSlug: string,
  item: Partial<SysPerfPartsSpec> & { name: string },
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/parts-spec'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(item),
  });
}

export function sysPerfDeletePartsSpec(
  token: string,
  workspaceSlug: string,
  specId: number,
): Promise<{ status: string }> {
  return apiFetchJson(
    spPath(workspaceSlug, `/base/parts-spec/${specId}`),
    token,
    { method: 'DELETE' },
  );
}

export interface SysPerfPartsCatalogItem {
  id: number;
  category: string;
  drive_type: string;
  sub_type: string;
  name: string;
  sort_order: number;
  note: string;
  created_at?: string;
}

export interface SysPerfPartsCatalogSavePayload {
  id?: number | null;
  category: string;
  drive_type?: string;
  sub_type?: string;
  name: string;
  sort_order?: number;
  note?: string;
}

export function sysPerfGetPartsCatalog(
  token: string,
  workspaceSlug: string,
): Promise<{ data: SysPerfPartsCatalogItem[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/parts-catalog'), token);
}

export function sysPerfSavePartsCatalog(
  token: string,
  workspaceSlug: string,
  item: SysPerfPartsCatalogSavePayload,
): Promise<{ status: string; id: number }> {
  return apiFetchJson(spPath(workspaceSlug, '/base/parts-catalog'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(item),
  });
}

export function sysPerfDeletePartsCatalog(
  token: string,
  workspaceSlug: string,
  id: number,
): Promise<{ status: string }> {
  return apiFetchJson(
    spPath(workspaceSlug, `/base/parts-catalog/${id}`),
    token,
    {
      method: 'DELETE',
    },
  );
}

export interface SysPerfDbTest {
  id: number;
  file_id: number | null;
  filename: string;
  sheet_name: string;
  saved_at: string;
  csv_path: string;
  row_count: number;
  col_count: number;
  car_code: string;
  car_type: string;
  engine: string;
  stage: string;
  car_number: string;
  test_item: string;
  test_date: string;
  refrigerant_charge: string;
  comp: string;
  indoor_condenser: string;
  condenser: string;
  cooling_fan: string;
  radiator: string;
  ihx: string;
  txv: string;
  battery_chiller: string;
  eva: string;
  hvac: string;
  heater_core: string;
  ptc: string;
}

export interface SysPerfDbSavePayload {
  file_id: number;
  sheet_name: string;
  car_code: string;
  car_type: string;
  engine: string;
  stage: string;
  car_number: string;
  test_item: string;
  test_date: string;
  refrigerant_charge: string;
  comp: string;
  indoor_condenser: string;
  condenser: string;
  cooling_fan: string;
  radiator: string;
  ihx: string;
  txv: string;
  battery_chiller: string;
  eva: string;
  hvac: string;
  heater_core: string;
  ptc: string;
}

export function sysPerfDbSave(
  token: string,
  workspaceSlug: string,
  payload: SysPerfDbSavePayload,
): Promise<{
  status: string;
  test_id: number;
  csv: string;
  row_count: number;
  col_count: number;
}> {
  return apiFetchJson(spPath(workspaceSlug, '/db-save'), token, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(payload),
  });
}

export function sysPerfDbList(
  token: string,
  workspaceSlug: string,
): Promise<{ data: SysPerfDbTest[] }> {
  return apiFetchJson(spPath(workspaceSlug, '/db-list'), token);
}

export function sysPerfDbDelete(
  token: string,
  workspaceSlug: string,
  testId: number,
): Promise<{ status: string }> {
  return apiFetchJson(spPath(workspaceSlug, `/db-delete/${testId}`), token, {
    method: 'DELETE',
  });
}

export async function sysPerfDbCsv(
  token: string,
  workspaceSlug: string,
  testId: number,
): Promise<Blob> {
  const response = await fetch(spPath(workspaceSlug, `/db-csv/${testId}`), {
    headers: jsonHeaders(token),
    cache: 'no-store',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed with ${response.status}.`,
      payload,
    );
  }
  return response.blob();
}
