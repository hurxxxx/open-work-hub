import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, Loader2, Mail, RefreshCw } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  type MailTone,
  type WritingLang,
  WritingAssistantApiError,
  generateMail,
} from '../api/writing-assistant-api';
import {
  FieldLabel,
  LangSelect,
  ResultPanel,
  TranslationPanel,
  splitWritingResult,
} from './writing-assistant-parts';

const MAIL_TONES: MailTone[] = [
  'polite',
  'friendly',
  'formal',
  'concise',
  'apologize',
  'report',
  'assertive',
  'technical',
];

export function EmailAssistantView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceName = workspaceBootstrap.data?.workspace.name ?? '';

  const [originalMail, setOriginalMail] = useState('');
  const [intent, setIntent] = useState('');
  const [tone, setTone] = useState<MailTone>('polite');
  const [lang, setLang] = useState<WritingLang>('ko');
  const [main, setMain] = useState('');
  const [reference, setReference] = useState('');
  const [genKey, setGenKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    if (!intent.trim()) {
      setError(t('ai.emailAssistant.errors.empty'));
      return;
    }
    if (!token) return;
    setLoading(true);
    setError(null);
    setMain('');
    setReference('');
    try {
      const data = await generateMail({
        token,
        workspaceSlug,
        intent,
        originalMail,
        tone,
        lang,
      });
      const split = splitWritingResult(data.result);
      setMain(split.main);
      setReference(split.reference ?? '');
      setGenKey((key) => key + 1);
    } catch (err) {
      setError(
        err instanceof WritingAssistantApiError
          ? err.message
          : t('ai.emailAssistant.errors.generateFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [intent, lang, originalMail, t, token, tone, workspaceSlug]);

  const reset = () => {
    setOriginalMail('');
    setIntent('');
    setMain('');
    setReference('');
    setGenKey((key) => key + 1);
    setError(null);
    setTone('polite');
    setLang('ko');
  };

  // 한국어(참고) 편집 → 외국어 결과물 갱신.
  const handleSyncForeign = useCallback(
    (foreign: string) => setMain(foreign),
    [],
  );
  // 외국어 결과물 편집 → 한국어(참고) 번역 갱신.
  const handleSyncReference = useCallback(
    (korean: string) => setReference(korean),
    [],
  );
  const handleMainChange = useCallback((next: string) => setMain(next), []);
  const handleReferenceChange = useCallback(
    (next: string) => setReference(next),
    [],
  );
  const showTranslation = lang !== 'ko';

  return (
    <main className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-6">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <Mail className="size-5 shrink-0 text-app-ink/45" />
          <h1 className="app-text-title-lg truncate text-app-ink">
            {t('ai.emailAssistant.title')}
          </h1>
          {workspaceName ? (
            <span className="app-text-caption truncate text-app-ink/55">
              {workspaceName}
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={reset}
          className="app-text-control inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border px-3 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent"
        >
          <RefreshCw className="size-4" />
          {t('ai.emailAssistant.reset')}
        </button>
      </header>

      <div
        className={cn(
          'grid min-h-0 flex-1 grid-cols-1 gap-4 p-5',
          showTranslation ? 'lg:grid-cols-3' : 'lg:grid-cols-2',
        )}
      >
        <div className="flex min-h-0 flex-col gap-4">
          <div>
            <FieldLabel>{t('ai.emailAssistant.originalLabel')}</FieldLabel>
            <textarea
              value={originalMail}
              onChange={(e) => setOriginalMail(e.target.value)}
              placeholder={t('ai.emailAssistant.originalPlaceholder')}
              className="min-h-[200px] w-full resize-none rounded-md border border-app-border bg-app-surface p-3 app-text-body-sm leading-6 text-app-ink outline-none placeholder:text-app-ink/35 focus:border-app-accent"
            />
          </div>

          <div className="flex gap-4">
            <div className="min-w-0 flex-1">
              <FieldLabel>{t('ai.emailAssistant.toneLabel')}</FieldLabel>
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value as MailTone)}
                className="app-field-input"
              >
                {MAIL_TONES.map((value) => (
                  <option key={value} value={value}>
                    {t(`ai.emailAssistant.tones.${value}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="shrink-0">
              <FieldLabel>{t('ai.emailAssistant.langLabel')}</FieldLabel>
              <LangSelect value={lang} onChange={setLang} />
            </div>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <FieldLabel>{t('ai.emailAssistant.intentLabel')}</FieldLabel>
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder={t('ai.emailAssistant.intentPlaceholder')}
              className="min-h-[160px] flex-1 resize-none rounded-md border border-app-border bg-app-surface p-3 app-text-body-sm leading-6 text-app-ink outline-none placeholder:text-app-ink/35 focus:border-app-accent"
            />
          </div>

          {error ? (
            <div className="flex items-start gap-2 rounded-md border border-app-danger-border bg-app-danger-bg p-3 text-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}

          <button
            type="button"
            onClick={() => void run()}
            disabled={loading || !intent.trim()}
            className="app-text-control inline-flex h-11 items-center justify-center gap-2 rounded-md bg-app-accent px-6 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Mail className="size-4" />
            )}
            {loading
              ? t('ai.emailAssistant.generating')
              : t('ai.emailAssistant.generate')}
          </button>
        </div>

        <ResultPanel
          key={`result-${genKey}`}
          content={main}
          loading={loading}
          loadingLabel={t('ai.emailAssistant.generating')}
          placeholder={t('ai.emailAssistant.resultPlaceholder')}
          filename={t('ai.emailAssistant.filename')}
          token={token}
          workspaceSlug={workspaceSlug}
          onChange={handleMainChange}
          translateTo={showTranslation ? 'ko' : null}
          onTranslated={handleSyncReference}
        />

        {/* Right: editable Korean reference translation (foreign-language output only) */}
        {showTranslation ? (
          <TranslationPanel
            key={`reference-${genKey}`}
            initialText={reference}
            lang={lang as 'en' | 'zh'}
            token={token}
            workspaceSlug={workspaceSlug}
            onSync={handleSyncForeign}
            onChange={handleReferenceChange}
            placeholder={
              main
                ? t('ai.writingAssistant.translationMissing')
                : t('ai.writingAssistant.translationPlaceholder')
            }
          />
        ) : null}
      </div>
    </main>
  );
}
