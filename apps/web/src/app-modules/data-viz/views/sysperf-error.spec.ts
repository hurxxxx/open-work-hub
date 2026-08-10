import { describe, expect, it } from 'vitest';

import { formatSysPerfErrorMessage } from './sysperf-error';

describe('sysperf error model', () => {
  it('uses Error messages and falls back for non-Error failures', () => {
    expect(formatSysPerfErrorMessage(new Error('network'), 'failed')).toBe(
      'network',
    );
    expect(formatSysPerfErrorMessage('bad', 'failed')).toBe('failed');
    expect(formatSysPerfErrorMessage(new Error(''), 'failed')).toBe('failed');
  });
});
