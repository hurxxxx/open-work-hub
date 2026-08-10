import type { SysPerfDbSavePayload } from '../api/dataviz-api';
import { partFields, type PartsState } from './sysperf-parts-state';
import {
  EMPTY_FILE_INFO,
  type CommonInfo,
  type FileInfo,
} from './sysperf-testinfo';

export function buildSysPerfDbSavePayload({
  fileId,
  sheet,
  common,
  perFile,
  parts,
}: {
  fileId: number;
  sheet: string;
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
  parts: Record<number, PartsState>;
}): SysPerfDbSavePayload {
  const fileInfo = perFile[fileId] || EMPTY_FILE_INFO;
  return {
    file_id: fileId,
    sheet_name: sheet,
    car_code: common.car_code,
    car_type: common.car_type,
    engine: common.engine,
    stage: common.stage,
    car_number: common.car_number,
    test_item: fileInfo.test_item,
    test_date: fileInfo.test_date,
    refrigerant_charge: fileInfo.refrigerant_charge,
    ...partFields(parts, fileId),
  };
}
