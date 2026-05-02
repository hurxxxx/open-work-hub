import { vi } from 'vitest';
import '@/src/platform/i18n';

Object.defineProperty(window, 'scrollTo', {
  configurable: true,
  value: vi.fn(),
});
