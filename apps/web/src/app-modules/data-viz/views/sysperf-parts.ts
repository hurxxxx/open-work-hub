// i18n-exempt-file: SysPerf parts category keys and legacy catalog labels are API/domain contract data.
// 부품사양 12카테고리 — 원본 sys_perf.js L136~169 의 상수/카탈로그 트리 로직 이식.
import type { SysPerfPartsCatalogItem } from '../api/dataviz-api';
import {
  SYSPERF_PART_LABEL_COLORS,
  SYSPERF_PART_TYPE_COLORS,
} from './data-viz-colors';

export const PART_CAT_LABELS: Record<string, string> = {
  comp: '컴프',
  indoor_condenser: '실내 콘덴서',
  condenser: '콘덴서',
  cooling_fan: '쿨링팬',
  radiator: '라디에이터',
  ihx: 'IHX',
  txv: '팽창밸브',
  battery_chiller: '배터리 칠러',
  eva: '에바',
  hvac: 'HVAC',
  heater_core: '히터코어',
  ptc: 'PTC',
};

export const PART_CAT_ORDER = [
  'comp',
  'indoor_condenser',
  'condenser',
  'cooling_fan',
  'radiator',
  'ihx',
  'txv',
  'battery_chiller',
  'eva',
  'hvac',
  'heater_core',
  'ptc',
] as const;
export type PartCategoryKey = (typeof PART_CAT_ORDER)[number];

export const COMP_DRIVE_LABELS: Record<string, string> = {
  belt: '벨트식',
  electric: '전동식',
};
export const COMPETITOR_SUBTYPE = '경쟁사';
export const COMP_SUBS: Record<string, string[]> = {
  belt: ['내부가변', '외부가변', COMPETITOR_SUBTYPE],
  electric: ['DE', 'DEC', COMPETITOR_SUBTYPE],
};
export const NONE_OPTION = '사양없음';

// 업로드 칩 4서브라벨 색상 (원본 LBL_COLORS)
export const LBL_COLORS = SYSPERF_PART_LABEL_COLORS;

export const PART_TYPES = ['양산', '개발', '경쟁사'] as const;
export type PartType = (typeof PART_TYPES)[number];
export const DEFAULT_PART_TYPE: PartType = PART_TYPES[0];
export const PART_TYPE_COLORS: Record<PartType, string> =
  SYSPERF_PART_TYPE_COLORS;

export interface CatalogItem {
  id: number;
  name: string;
}
export interface PartCatalogTree {
  comp: {
    belt: Record<string, CatalogItem[]>;
    electric: Record<string, CatalogItem[]>;
  };
  [key: string]: unknown;
}

export function emptyCatalog(): PartCatalogTree {
  const cat: PartCatalogTree = {
    comp: {
      belt: { 내부가변: [], 외부가변: [], 경쟁사: [] },
      electric: { DE: [], DEC: [], 경쟁사: [] },
    },
  };
  PART_CAT_ORDER.forEach((k) => {
    if (k !== 'comp') (cat as Record<string, CatalogItem[]>)[k] = [];
  });
  return cat;
}

// 서버 rows → 카탈로그 트리 (원본 _rebuildPartCatalog)
export function rebuildPartCatalog(
  rows: SysPerfPartsCatalogItem[],
): PartCatalogTree {
  const cat = emptyCatalog();
  (rows || []).forEach((r) => {
    const c = r.category;
    const item: CatalogItem = { id: r.id, name: r.name };
    if (c === 'comp') {
      const dt = r.drive_type || 'belt';
      const st = r.sub_type || '내부가변';
      if (!cat.comp[dt as 'belt' | 'electric'])
        (cat.comp as Record<string, Record<string, CatalogItem[]>>)[dt] = {};
      if (!cat.comp[dt as 'belt' | 'electric'][st])
        cat.comp[dt as 'belt' | 'electric'][st] = [];
      cat.comp[dt as 'belt' | 'electric'][st].push(item);
    } else if ((cat as Record<string, CatalogItem[]>)[c] !== undefined) {
      (cat as Record<string, CatalogItem[]>)[c].push(item);
    }
  });
  return cat;
}

// 컴프 업로드 표시그룹: BASE 6 sub_type → 업로드 4 그룹 (원본 groups 배열)
//   전동 = electric DE+DEC, 경쟁사 = belt경쟁사 + electric경쟁사
export function compDisplayGroups(
  tree: PartCatalogTree,
): { label: string; items: CatalogItem[] }[] {
  const c = tree.comp || { belt: {}, electric: {} };
  return [
    { label: '내부가변', items: c.belt?.['내부가변'] || [] },
    { label: '외부가변', items: c.belt?.['외부가변'] || [] },
    {
      label: '전동',
      items: (c.electric?.DE || []).concat(c.electric?.DEC || []),
    },
    {
      label: '경쟁사',
      items: (c.belt?.['경쟁사'] || []).concat(c.electric?.['경쟁사'] || []),
    },
  ];
}

// 카테고리별 칩 목록 (comp 제외)
export function partItems(
  tree: PartCatalogTree,
  partKey: string,
): CatalogItem[] {
  return (
    ((tree as Record<string, CatalogItem[]>)[partKey] as CatalogItem[]) || []
  );
}
