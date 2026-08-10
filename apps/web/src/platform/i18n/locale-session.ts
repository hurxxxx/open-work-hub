export interface LocaleSessionConfig<Locale extends string> {
  defaultLocale: Locale;
  supportedLocales: readonly Locale[];
  storageKey: string;
}

export interface LocaleStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface LocaleDocument {
  documentElement: {
    lang: string;
  };
}

export interface LocaleI18n<Locale extends string> {
  language?: string;
  changeLanguage(locale: Locale): unknown;
}

export interface LocaleStoreDependencies {
  store?: LocaleStore | null;
}

export interface LocaleSessionDependencies<Locale extends string>
  extends LocaleStoreDependencies {
  document?: LocaleDocument | null;
  i18n?: LocaleI18n<Locale> | null;
}

function resolveLocaleStore(
  dependencies: LocaleStoreDependencies,
): LocaleStore | null {
  if ('store' in dependencies) {
    return dependencies.store ?? null;
  }
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

function resolveLocaleDocument<Locale extends string>(
  dependencies: LocaleSessionDependencies<Locale>,
): LocaleDocument | null {
  if ('document' in dependencies) {
    return dependencies.document ?? null;
  }
  if (typeof document === 'undefined') {
    return null;
  }
  return document;
}

export function isSupportedLocale<Locale extends string>(
  value: string | null | undefined,
  config: Pick<LocaleSessionConfig<Locale>, 'supportedLocales'>,
): value is Locale {
  return (
    typeof value === 'string' &&
    config.supportedLocales.includes(value as Locale)
  );
}

export function normalizeLocale<Locale extends string>(
  value: string | null | undefined,
  config: Pick<
    LocaleSessionConfig<Locale>,
    'defaultLocale' | 'supportedLocales'
  >,
): Locale {
  return isSupportedLocale(value, config) ? value : config.defaultLocale;
}

export function readStoredLocale<Locale extends string>(
  config: LocaleSessionConfig<Locale>,
  dependencies: LocaleStoreDependencies = {},
): Locale {
  try {
    const store = resolveLocaleStore(dependencies);
    if (!store) {
      return config.defaultLocale;
    }
    return normalizeLocale(store.getItem(config.storageKey), config);
  } catch {
    return config.defaultLocale;
  }
}

export function persistLocale<Locale extends string>(
  locale: Locale,
  config: LocaleSessionConfig<Locale>,
  dependencies: LocaleStoreDependencies = {},
): void {
  try {
    const store = resolveLocaleStore(dependencies);
    if (!store) {
      return;
    }
    store.setItem(config.storageKey, locale);
  } catch {
    return;
  }
}

export function syncLocale<Locale extends string>(
  locale: string | null | undefined,
  config: LocaleSessionConfig<Locale>,
  dependencies: LocaleSessionDependencies<Locale> = {},
): Locale {
  const normalized = normalizeLocale(locale, config);
  if (dependencies.i18n && dependencies.i18n.language !== normalized) {
    void dependencies.i18n.changeLanguage(normalized);
  }
  persistLocale(normalized, config, dependencies);

  const targetDocument = resolveLocaleDocument(dependencies);
  if (targetDocument) {
    targetDocument.documentElement.lang = normalized;
  }

  return normalized;
}
