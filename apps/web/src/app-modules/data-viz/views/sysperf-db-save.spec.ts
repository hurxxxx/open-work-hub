import { describe, expect, it } from 'vitest';

import { emptyPartsState, type PartsState } from './sysperf-parts-state';
import { buildSysPerfDbSavePayload } from './sysperf-db-save';
import type { CommonInfo, FileInfo } from './sysperf-testinfo';

describe('sysperf DB save payload model', () => {
  it('builds the explicit DB save payload from common, per-file, and parts state', () => {
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
    const parts: Record<number, PartsState> = { 7: emptyPartsState() };
    parts[7].comp.direct = 'Direct Comp';
    parts[7].txv.selected = 'Selected TXV';

    expect(
      buildSysPerfDbSavePayload({
        fileId: 7,
        sheet: 'Sheet1',
        common,
        perFile,
        parts,
      }),
    ).toEqual({
      file_id: 7,
      sheet_name: 'Sheet1',
      car_code: 'CN7',
      car_type: 'EV',
      engine: 'PE',
      stage: 'P1',
      car_number: '42',
      test_item: 'Cooling',
      test_date: '20260101',
      refrigerant_charge: '500g',
      comp: 'Direct Comp',
      indoor_condenser: '',
      condenser: '',
      cooling_fan: '',
      radiator: '',
      ihx: '',
      txv: 'Selected TXV',
      battery_chiller: '',
      eva: '',
      hvac: '',
      heater_core: '',
      ptc: '',
    });
  });

  it('uses empty file info defaults when per-file metadata is missing', () => {
    const common: CommonInfo = {
      car_code: 'CN7',
      car_type: '',
      engine: '',
      stage: '',
      car_number: '',
    };

    expect(
      buildSysPerfDbSavePayload({
        fileId: 8,
        sheet: 'Sheet1',
        common,
        perFile: {},
        parts: {},
      }).test_item,
    ).toBe('');
  });
});
