import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  normalizeLocale,
  persistLocale,
  readStoredLocale,
  syncLocale,
  type LocaleSessionConfig,
  type LocaleStore,
} from './locale-session';

type TestLocale = 'ko-KR' | 'en-US';

const config = {
  defaultLocale: 'ko-KR',
  supportedLocales: ['ko-KR', 'en-US'],
  storageKey: 'ai-do:locale',
} satisfies LocaleSessionConfig<TestLocale>;

function createStore(initial: Record<string, string> = {}): {
  store: LocaleStore;
  values: Map<string, string>;
} {
  const values = new Map(Object.entries(initial));
  return {
    store: {
      getItem: vi.fn((key: string) => values.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        values.set(key, value);
      }),
    },
    values,
  };
}

describe('locale-session', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('normalizes unsupported locale values to the default', () => {
    expect(normalizeLocale('en-US', config)).toBe('en-US');
    expect(normalizeLocale('ko-KR', config)).toBe('ko-KR');
    expect(normalizeLocale('fr-FR', config)).toBe('ko-KR');
    expect(normalizeLocale(null, config)).toBe('ko-KR');
    expect(normalizeLocale(undefined, config)).toBe('ko-KR');
  });

  it('reads stored locales through an injected store', () => {
    const english = createStore({ [config.storageKey]: 'en-US' });
    const invalid = createStore({ [config.storageKey]: 'invalid' });

    expect(readStoredLocale(config, { store: english.store })).toBe('en-US');
    expect(readStoredLocale(config, { store: invalid.store })).toBe('ko-KR');
  });

  it('uses defaults when browser globals are unavailable', () => {
    vi.stubGlobal('window', undefined);
    vi.stubGlobal('document', undefined);

    expect(readStoredLocale(config)).toBe('ko-KR');
    expect(() => persistLocale('en-US', config)).not.toThrow();
    expect(syncLocale('en-US', config)).toBe('en-US');
  });

  it('swallows localStorage read and write failures', () => {
    const store: LocaleStore = {
      getItem: vi.fn(() => {
        throw new Error('storage blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('storage blocked');
      }),
    };

    expect(readStoredLocale(config, { store })).toBe('ko-KR');
    expect(() => persistLocale('en-US', config, { store })).not.toThrow();
  });

  it('syncs i18n, storage, and document side effects from injected dependencies', () => {
    const { store, values } = createStore();
    const changeLanguage = vi.fn();
    const document = { documentElement: { lang: 'ko-KR' } };

    expect(
      syncLocale('en-US', config, {
        document,
        i18n: { language: 'ko-KR', changeLanguage },
        store,
      }),
    ).toBe('en-US');

    expect(changeLanguage).toHaveBeenCalledWith('en-US');
    expect(values.get(config.storageKey)).toBe('en-US');
    expect(document.documentElement.lang).toBe('en-US');
  });

  it('falls back invalid sync input and suppresses unchanged i18n changes', () => {
    const { store, values } = createStore();
    const changeLanguage = vi.fn();
    const document = { documentElement: { lang: 'en-US' } };

    expect(
      syncLocale('invalid', config, {
        document,
        i18n: { language: 'ko-KR', changeLanguage },
        store,
      }),
    ).toBe('ko-KR');

    expect(changeLanguage).not.toHaveBeenCalled();
    expect(values.get(config.storageKey)).toBe('ko-KR');
    expect(document.documentElement.lang).toBe('ko-KR');
  });

  it('tolerates missing document and i18n dependencies', () => {
    const { store, values } = createStore();

    expect(
      syncLocale('en-US', config, {
        document: null,
        i18n: null,
        store,
      }),
    ).toBe('en-US');
    expect(values.get(config.storageKey)).toBe('en-US');
  });
});
