import { describe, expect, it } from 'vitest';

import {
  AI_SECURITY_TABS,
  resolveAiSecurityTab,
  withAiSecurityTab,
} from './admin-ai-security-model';

describe('AI security tabs', () => {
  it('contains only external-transfer security surfaces', () => {
    expect(AI_SECURITY_TABS).toEqual([
      'overview',
      'monitoring',
      'data',
      'rules',
      'exceptions',
      'simulator',
    ]);
  });

  it('uses the URL tab as the stable navigation state', () => {
    expect(resolveAiSecurityTab(null)).toBe('overview');
    expect(resolveAiSecurityTab('unknown')).toBe('overview');
    expect(resolveAiSecurityTab('rules')).toBe('rules');
    expect(
      withAiSecurityTab(
        new URLSearchParams('source=metric'),
        'monitoring',
      ).toString(),
    ).toBe('source=metric&tab=monitoring');
    expect(
      withAiSecurityTab(
        new URLSearchParams('source=metric&tab=rules'),
        'overview',
      ).toString(),
    ).toBe('source=metric');
  });
});
