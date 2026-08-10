import {
  DEFAULT_PART_TYPE,
  PART_CAT_ORDER,
  type PartCategoryKey,
  type PartType,
} from './sysperf-parts';

export interface PartSel {
  selected: string;
  direct: string;
  type: PartType;
}

export type PartsState = Record<string, PartSel>;

export function emptyPartsState(): PartsState {
  const out: PartsState = {};
  PART_CAT_ORDER.forEach((key) => {
    out[key] = { selected: '', direct: '', type: DEFAULT_PART_TYPE };
  });
  return out;
}

export function partVal(
  parts: Record<number, PartsState>,
  fid: number,
  key: string,
): string {
  const part = parts[fid]?.[key];
  return part?.direct || part?.selected || '';
}

export function partFields(
  parts: Record<number, PartsState>,
  fid: number,
): Record<PartCategoryKey, string> {
  const out = {} as Record<PartCategoryKey, string>;
  PART_CAT_ORDER.forEach((key) => {
    out[key] = partVal(parts, fid, key);
  });
  return out;
}
