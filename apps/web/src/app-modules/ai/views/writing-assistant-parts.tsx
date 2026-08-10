import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ClipboardCopy,
  Download,
  Languages,
  Loader2,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import {
  type DownloadFormat,
  type WritingLang,
  WritingAssistantApiError,
  downloadDocument,
  translateWriting,
} from '../api/writing-assistant-api';

const LANGS: WritingLang[] = ['ko', 'en', 'zh'];
const DOWNLOAD_FORMATS: DownloadFormat[] = ['txt', 'docx', 'pdf'];

export function SegButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'h-9 rounded-md px-3 app-text-control transition-colors',
        active
          ? 'bg-app-accent text-app-accent-fg'
          : 'text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
      )}
    >
      {children}
    </button>
  );
}

export function LangSelect({
  value,
  onChange,
}: {
  value: WritingLang;
  onChange: (lang: WritingLang) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="inline-flex gap-1 rounded-md border border-app-border bg-app-bg p-1">
      {LANGS.map((lang) => (
        <SegButton
          key={lang}
          active={value === lang}
          onClick={() => onChange(lang)}
        >
          {t(`ai.writingAssistant.langs.${lang}`)}
        </SegButton>
      ))}
    </div>
  );
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 block app-text-control text-app-ink/75">
      {children}
    </label>
  );
}

const TRANSLATION_MARKER = '[한국어 번역 / 참고용]';

/**
 * For non-Korean output the model returns the document, a "---" separator,
 * the "[한국어 번역 / 참고용]" header, then a Korean reference translation.
 * Split it so the deliverable (main) and the reference render separately.
 */
export function splitWritingResult(result: string): {
  main: string;
  reference: string | null;
} {
  const idx = result.indexOf(TRANSLATION_MARKER);
  if (idx < 0) {
    return { main: result, reference: null };
  }
  const main = result
    .slice(0, idx)
    .replace(/\s*-{3,}\s*$/, '')
    .trimEnd();
  const reference = result.slice(idx + TRANSLATION_MARKER.length).trim();
  // 마커 앞이 비어 있으면(번역 블록이 먼저 나온 경우) 결과물 패널을 비워 둔다.
  // 이전의 `main || result` 폴백은 한국어 참고 번역까지 결과물로 노출했다.
  return { main, reference: reference || null };
}

const SYNC_DEBOUNCE_MS = 1500;

/**
 * Editable text that stays in sync with a sibling panel via debounced
 * re-translation.
 *
 * - `source` is the parent-owned value. When it changes from the outside
 *   (a fresh generation, or the sibling translating into this panel) the local
 *   text is reseeded WITHOUT marking it dirty, so the incoming text does not
 *   bounce straight back through a re-translate.
 * - A user edit marks the text dirty and, after a debounce, translates it into
 *   `translateTo` and hands the result to `onTranslated` (which updates the
 *   sibling). `onChange` keeps the parent's copy of THIS panel in sync.
 * - `translateTo === null` disables translation (editable, no sibling).
 */
export function useSyncedText({
  source,
  translateTo,
  token,
  workspaceSlug,
  onTranslated,
  onChange,
}: {
  source: string;
  translateTo: WritingLang | null;
  token: string | null;
  workspaceSlug: string | null;
  onTranslated?: (translated: string) => void;
  onChange?: (next: string) => void;
}) {
  const { t } = useTranslation('apps');
  const [text, setText] = useState(source);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirtyRef = useRef(false);
  const reqIdRef = useRef(0);
  // Tracks the last value we observed/emitted so we can tell an external change
  // (reseed) apart from the echo of our own edit (which must not clear dirty).
  const lastSeenRef = useRef(source);

  useEffect(() => {
    if (source === lastSeenRef.current) return;
    lastSeenRef.current = source;
    // 사용자가 이 패널을 편집 중(dirty)이면 외부(형제) 번역 결과로 덮어쓰지 않는다.
    // 양쪽을 동시에 편집할 때, 한쪽 편집이 만든 번역이 늦게 도착해 다른 쪽의 더
    // 최신 편집을 외부 재시드로 간주해 지워 버리는 입력 유실을 막는다. 진행 중인
    // 사용자 입력이 우선이며, 그 입력은 곧 자체 디바운스로 번역돼 형제를 갱신한다.
    // (편집 중이 아니므로 진행 중인 요청도 없어, reqId 무효화는 불필요하다.)
    if (dirtyRef.current) return;
    // 외부 재시드가 들어오면 진행 중이던 재번역 요청을 무효화한다. 그러지 않으면
    // 늦게 도착한 낡은 번역이 방금 재시드된 값을 덮어쓴다.
    reqIdRef.current += 1;
    setText(source);
  }, [source]);

  useEffect(() => {
    if (!dirtyRef.current || !translateTo || !token || !text.trim()) return;
    const reqId = ++reqIdRef.current;
    // 언마운트/재실행 시 이미 발사된 요청의 결과를 버린다. reqId 가드는 같은
    // 인스턴스 안에서만 유효해, 재생성으로 패널이 key 리마운트되면 옛 인스턴스의
    // 진행 중 요청이 그대로 onTranslated 를 호출해 새 결과물을 덮어쓴다.
    let active = true;
    // 스피너/에러 리셋은 디바운스가 끝나 실제 요청이 나갈 때 한다. 동기적으로 켜면
    // 키 입력마다 요청 없이 '동기화 중...'이 표시돼 진행 상태를 잘못 알린다.
    const timer = window.setTimeout(async () => {
      setSyncing(true);
      setError(null);
      try {
        const data = await translateWriting({
          token,
          workspaceSlug,
          source: text,
          targetLang: translateTo,
        });
        if (active && reqIdRef.current === reqId) {
          // 동기화 성공 → dirty 해제. 그래야 이후 text 외 의존성(token,
          // workspaceSlug)이 바뀌어도 변경되지 않은 텍스트를 다시 번역하지 않는다.
          dirtyRef.current = false;
          onTranslated?.(data.result);
        }
      } catch (err) {
        if (active && reqIdRef.current === reqId) {
          setError(
            err instanceof WritingAssistantApiError
              ? err.message
              : t('ai.writingAssistant.errors.syncFailed'),
          );
        }
      } finally {
        if (active && reqIdRef.current === reqId) setSyncing(false);
      }
    }, SYNC_DEBOUNCE_MS);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [text, translateTo, token, workspaceSlug, onTranslated, t]);

  const edit = useCallback(
    (next: string) => {
      dirtyRef.current = true;
      lastSeenRef.current = next;
      setText(next);
      onChange?.(next);
    },
    [onChange],
  );

  const clearError = useCallback(() => setError(null), []);

  return { text, syncing, error, edit, clearError };
}

/**
 * Main deliverable panel: shows the document and copies/downloads it. When
 * `onChange` is provided the document becomes editable; pair it with
 * `translateTo`/`onTranslated` to push edits into the reference panel
 * (e.g. edit the English result → re-translate into the Korean reference).
 */
export function ResultPanel({
  content,
  loading,
  loadingLabel,
  placeholder,
  filename,
  token,
  workspaceSlug,
  onChange,
  translateTo = null,
  onTranslated,
}: {
  content: string;
  loading: boolean;
  loadingLabel: string;
  placeholder: string;
  filename: string;
  token: string | null;
  workspaceSlug: string | null;
  onChange?: (next: string) => void;
  translateTo?: WritingLang | null;
  onTranslated?: (translated: string) => void;
}) {
  const { t } = useTranslation('apps');
  const editable = Boolean(onChange);
  const {
    text,
    syncing,
    error: syncError,
    edit,
    clearError: clearSyncError,
  } = useSyncedText({
    source: content,
    translateTo: editable ? translateTo : null,
    token,
    workspaceSlug,
    onTranslated,
    onChange,
  });
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState<DownloadFormat | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // 새 생성/초기화로 결과물이 바뀌면 직전 다운로드 에러를 지운다.
  useEffect(() => {
    setDownloadError(null);
  }, [content]);

  const onCopy = async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const onDownload = async (format: DownloadFormat) => {
    if (!token || !text) return;
    // 다운로드 시작 시 이전 동기화 에러를 지운다. 그러지 않으면 stale 동기화
    // 에러가 다운로드 결과(성공/실패)를 가린다(아래 error 합성은 sync 우선).
    clearSyncError();
    setDownloadError(null);
    setDownloading(format);
    try {
      await downloadDocument({
        token,
        workspaceSlug,
        content: text,
        format,
        filename,
      });
    } catch (err) {
      setDownloadError(
        err instanceof WritingAssistantApiError
          ? err.message
          : t('ai.writingAssistant.errors.downloadFailed'),
      );
    } finally {
      setDownloading(null);
    }
  };

  const error = syncError ?? downloadError;

  return (
    <div className="flex min-h-0 flex-col rounded-md border border-app-border bg-app-surface">
      <div className="flex items-center justify-between gap-2 border-b border-app-border px-4 py-2.5">
        <h2 className="app-text-title flex items-center gap-1.5 truncate text-app-ink">
          {t('ai.writingAssistant.resultTitle')}
          {syncing ? (
            <span className="ml-1 inline-flex items-center gap-1 app-text-caption font-normal text-app-ink/45">
              <Loader2 className="size-3 animate-spin" />
              {t('ai.writingAssistant.syncing')}
            </span>
          ) : null}
        </h2>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            disabled={!text}
            onClick={() => void onCopy()}
            className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
          >
            {copied ? (
              <Check className="size-3" />
            ) : (
              <ClipboardCopy className="size-3" />
            )}
            {copied
              ? t('ai.writingAssistant.copied')
              : t('ai.writingAssistant.copy')}
          </button>
          {DOWNLOAD_FORMATS.map((format) => (
            <button
              key={format}
              type="button"
              disabled={!text || downloading !== null}
              onClick={() => void onDownload(format)}
              className="app-text-caption inline-flex items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
            >
              {downloading === format ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <Download className="size-3" />
              )}
              {format.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-xs text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {error}
        </div>
      ) : null}
      <div className="relative min-h-0 flex-1">
        {loading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-surface/80">
            <div className="flex flex-col items-center gap-2 app-text-body-sm text-app-ink/55">
              <Loader2 className="size-5 animate-spin" />
              {loadingLabel}
            </div>
          </div>
        ) : null}
        {editable ? (
          <textarea
            value={text}
            onChange={(event) => {
              // 편집을 다시 시작하면 이전 다운로드 에러를 지운다. (동기화 에러는
              // 디바운스 요청이 나갈 때 훅이 스스로 지운다.)
              setDownloadError(null);
              edit(event.target.value);
            }}
            placeholder={placeholder}
            className="h-full min-h-[320px] w-full resize-none bg-transparent p-4 app-text-body-sm leading-7 text-app-ink/75 outline-none placeholder:text-app-ink/35"
          />
        ) : (
          <div className="h-full min-h-[320px] overflow-y-auto whitespace-pre-wrap p-4 app-text-body-sm leading-7 text-app-ink/75">
            {text || <span className="text-app-ink/35">{placeholder}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Editable Korean reference panel. When the user edits the Korean text it is
 * re-translated (debounced) into the target language and the foreign deliverable
 * on the left is updated via `onSync`. Seeded from `initialText`; the parent
 * remounts this (via `key`) on each new generation. It also reflects external
 * updates to `initialText` (e.g. when the foreign deliverable is edited and
 * re-translated back into Korean) without bouncing a re-translate.
 */
export function TranslationPanel({
  initialText,
  lang,
  token,
  workspaceSlug,
  onSync,
  onChange,
  placeholder,
}: {
  initialText: string;
  lang: 'en' | 'zh';
  token: string | null;
  workspaceSlug: string | null;
  onSync: (foreignText: string) => void;
  onChange?: (next: string) => void;
  placeholder: string;
}) {
  const { t } = useTranslation('apps');
  const { text, syncing, error, edit } = useSyncedText({
    source: initialText,
    translateTo: lang,
    token,
    workspaceSlug,
    onTranslated: onSync,
    onChange,
  });
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex min-h-0 flex-col rounded-md border border-app-border bg-app-bg">
      <div className="flex items-center justify-between gap-2 border-b border-app-border px-4 py-2.5">
        <h2 className="app-text-title flex items-center gap-1.5 truncate text-app-ink/70">
          <Languages className="size-4" />
          {t('ai.writingAssistant.referenceTitle')}
          {syncing ? (
            <span className="ml-1 inline-flex items-center gap-1 app-text-caption font-normal text-app-ink/45">
              <Loader2 className="size-3 animate-spin" />
              {t('ai.writingAssistant.syncing')}
            </span>
          ) : null}
        </h2>
        <button
          type="button"
          disabled={!text}
          onClick={() => void onCopy()}
          className="app-text-caption inline-flex shrink-0 items-center gap-1 rounded-md border border-app-border px-2.5 py-1 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
        >
          {copied ? (
            <Check className="size-3" />
          ) : (
            <ClipboardCopy className="size-3" />
          )}
          {copied
            ? t('ai.writingAssistant.copied')
            : t('ai.writingAssistant.copy')}
        </button>
      </div>
      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-xs text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {error}
        </div>
      ) : null}
      {/* Stay editable even when empty (model omitted the marker): typing Korean
          triggers re-translation and syncs the foreign deliverable on the left. */}
      <textarea
        value={text}
        onChange={(event) => edit(event.target.value)}
        placeholder={placeholder}
        className="min-h-[320px] flex-1 resize-none bg-transparent p-4 app-text-body-sm leading-6 text-app-ink/70 outline-none placeholder:text-app-ink/35"
      />
      <div className="border-t border-app-border px-4 py-1.5 app-text-caption text-app-ink/45">
        {t('ai.writingAssistant.syncHint')}
      </div>
    </div>
  );
}
