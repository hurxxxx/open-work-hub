import { describe, expect, it } from 'vitest';

import {
  filterIconPickerKeys,
  iconPickerAllKeys,
  uniqueIconPickerKeys,
} from './icon-picker-model';

describe('icon picker model', () => {
  it('deduplicates and sorts icon keys', () => {
    expect(uniqueIconPickerKeys(['users', 'flask', 'users'])).toEqual([
      'flask',
      'users',
    ]);
  });

  it('builds an all-icons list from grouped keys', () => {
    expect(
      iconPickerAllKeys([
        { id: 'lab', label: 'Lab', iconKeys: ['flask', 'microscope'] },
        { id: 'work', label: 'Work', iconKeys: ['briefcase', 'flask'] },
      ]),
    ).toEqual(['briefcase', 'flask', 'microscope']);
  });

  it('filters by icon key and optional search text', () => {
    expect(
      filterIconPickerKeys(
        ['flask-conical', 'briefcase', 'shield-check'],
        'lab',
        (iconKey) => (iconKey === 'flask-conical' ? 'laboratory' : ''),
      ),
    ).toEqual(['flask-conical']);
  });
});
