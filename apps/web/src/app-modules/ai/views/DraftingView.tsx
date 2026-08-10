import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertCircle, FileText, Loader2, RefreshCw } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import { cn } from '@/src/lib/utils';
import {
  type DraftType,
  type WritingLang,
  WritingAssistantApiError,
  generateDraft,
} from '../api/writing-assistant-api';
import {
  FieldLabel,
  LangSelect,
  ResultPanel,
  TranslationPanel,
  splitWritingResult,
} from './writing-assistant-parts';

const DRAFT_TYPES: DraftType[] = [
  'general',
  'cooperation',
  'purchase',
  'report',
  'proposal',
  'minutes',
];

export function DraftingView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceName = workspaceBootstrap.data?.workspace.name ?? '';

  const [text, setText] = useState('');
  const [draftType, setDraftType] = useState<DraftType>('general');
  const [lang, setLang] = useState<WritingLang>('ko');
  const [main, setMain] = useState('');
  const [reference, setReference] = useState('');
  const [genKey, setGenKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    if (!text.trim()) {
      setError(t('ai.drafting.errors.empty'));
      return;
    }
    if (!token) return;
    setLoading(true);
    setError(null);
    setMain('');
    setReference('');
    try {
      const data = await generateDraft({
        token,
        workspaceSlug,
        text,
        type: draftType,
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
          : t('ai.drafting.errors.generateFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [draftType, lang, t, text, token, workspaceSlug]);

  const reset = () => {
    setText('');
    setMain('');
    setReference('');
    setGenKey((key) => key + 1);
    setError(null);
    setDraftType('general');
    setLang('ko');
  };

  const handleSync = useCallback((foreign: string) => setMain(foreign), []);
  const showTranslation = lang !== 'ko';

  return (
    <main className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-6">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <FileText className="size-5 shrink-0 text-app-ink/45" />
          <h1 className="app-text-title-lg truncate text-app-ink">
            {t('ai.drafting.title')}
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
          {t('ai.drafting.reset')}
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
            <FieldLabel>{t('ai.drafting.typeLabel')}</FieldLabel>
            <div className="flex flex-wrap gap-2">
              {DRAFT_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setDraftType(type)}
                  className={
                    draftType === type
                      ? 'rounded-md bg-app-accent px-3 py-1.5 app-text-control text-app-accent-fg'
                      : 'rounded-md border border-app-border px-3 py-1.5 app-text-control text-app-ink/70 transition-colors hover:bg-app-surface-hover hover:text-app-ink'
                  }
                >
                  {t(`ai.drafting.types.${type}`)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <FieldLabel>{t('ai.drafting.langLabel')}</FieldLabel>
            <LangSelect value={lang} onChange={setLang} />
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <FieldLabel>{t('ai.drafting.inputLabel')}</FieldLabel>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t(`ai.drafting.placeholders.${draftType}`)}
              className="min-h-[220px] flex-1 resize-none rounded-md border border-app-border bg-app-surface p-3 app-text-body-sm leading-6 text-app-ink outline-none placeholder:text-app-ink/35 focus:border-app-accent"
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
            disabled={loading || !text.trim()}
            className="app-text-control inline-flex h-11 items-center justify-center gap-2 rounded-md bg-app-accent px-6 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <FileText className="size-4" />
            )}
            {loading ? t('ai.drafting.generating') : t('ai.drafting.generate')}
          </button>
        </div>

        <ResultPanel
          content={main}
          loading={loading}
          loadingLabel={t('ai.drafting.generating')}
          placeholder={t('ai.drafting.resultPlaceholder')}
          filename={t(`ai.drafting.filenames.${draftType}`)}
          token={token}
          workspaceSlug={workspaceSlug}
        />

        {/* Right: editable Korean reference translation (foreign-language output only) */}
        {showTranslation ? (
          <TranslationPanel
            key={genKey}
            initialText={reference}
            lang={lang as 'en' | 'zh'}
            token={token}
            workspaceSlug={workspaceSlug}
            onSync={handleSync}
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
