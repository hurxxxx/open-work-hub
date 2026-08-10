import { describe, expect, it } from 'vitest';

import type { SysPerfUploadedFile } from '../api/dataviz-api';
import {
  buildSysPerfTestInfoItems,
  seedTestInfo,
  type CommonInfo,
  type FileInfo,
} from './sysperf-testinfo';

function sheet(sheet_name: string) {
  return {
    sheet_name,
    info_text: '',
    headers: [],
    header_count: 0,
    header_row: 0,
    info_row: 0,
    header_numeric_counts: {},
  };
}

describe('sysperf test info model', () => {
  it('prefers underscore filename fields while keeping auto-matched parts', () => {
    const files: SysPerfUploadedFile[] = [
      {
        file_id: 7,
        filename: '20260101_CN7_LOT42_SPEC_COOLING_500g_note.csv',
        auto_match: {
          car_code: 'AUTO-CAR',
          test_item: 'AUTO-ITEM',
          test_date: 'AUTO-DATE',
          refrigerant_charge: 'AUTO-CHARGE',
          comp: 'AUTO-COMP',
          txv: 'AUTO-TXV',
          condenser: 'AUTO-COND',
        },
      },
    ];

    const seeded = seedTestInfo(files);

    expect(seeded.common.car_code).toBe('CN7');
    expect(seeded.perFile[7]).toMatchObject({
      test_item: 'COOLING',
      test_date: '20260101',
      refrigerant_charge: '500g',
      lot_no: 'LOT42',
    });
    expect(seeded.parts[7].comp.direct).toBe('AUTO-COMP');
    expect(seeded.parts[7].txv.direct).toBe('AUTO-TXV');
    expect(seeded.parts[7].condenser.direct).toBe('AUTO-COND');
  });

  it('falls back to auto match when the filename has no underscore fields', () => {
    const files: SysPerfUploadedFile[] = [
      {
        file_id: 8,
        filename: 'plain-name.csv',
        auto_match: {
          car_code: 'AUTO-CAR',
          test_item: 'AUTO-ITEM',
          test_date: 'AUTO-DATE',
          refrigerant_charge: 'AUTO-CHARGE',
        },
      },
    ];

    const seeded = seedTestInfo(files);

    expect(seeded.common.car_code).toBe('AUTO-CAR');
    expect(seeded.perFile[8]).toMatchObject({
      test_item: 'AUTO-ITEM',
      test_date: 'AUTO-DATE',
      refrigerant_charge: 'AUTO-CHARGE',
      lot_no: '',
    });
  });

  it('builds one test-info save item for every uploaded sheet', () => {
    const common: CommonInfo = {
      car_code: 'CN7',
      car_type: 'EV',
      engine: 'PE',
      stage: 'P1',
      car_number: '42',
    };
    const perFile: Record<number, FileInfo> = {
      7: {
        test_item: 'Cooling',
        test_date: '20260101',
        refrigerant_charge: '500g',
        lot_no: 'LOT42',
      },
    };
    const files: SysPerfUploadedFile[] = [
      {
        file_id: 7,
        filename: 'file.xlsx',
        sheets: [sheet('Sheet1'), sheet('Sheet2')],
      },
    ];

    expect(buildSysPerfTestInfoItems({ files, common, perFile })).toEqual([
      {
        file_id: 7,
        sheet_name: 'Sheet1',
        car_model: 'CN7',
        spec: '',
        test_item: 'Cooling',
        test_date: '20260101',
        lot_no: 'LOT42',
        refrigerant: '500g',
        note: '',
      },
      {
        file_id: 7,
        sheet_name: 'Sheet2',
        car_model: 'CN7',
        spec: '',
        test_item: 'Cooling',
        test_date: '20260101',
        lot_no: 'LOT42',
        refrigerant: '500g',
        note: '',
      },
    ]);
  });
});
