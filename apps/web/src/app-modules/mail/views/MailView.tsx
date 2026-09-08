import { Search } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { useFeedback } from '@open-work-hub/ui';
import { InlineNotice } from '@open-work-hub/ui/feedback/inline-notice';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import { DraftEditor } from './DraftEditor';
import { DraftList } from './DraftList';
import { MailSettingsView } from './MailSettingsView';
import { MessageDetail } from './MessageDetail';
import { MessageList } from './MessageList';
import { NoMailAccountState } from './NoMailAccountState';
import { actionButtonClassName, fieldClassName } from './mail-view-model';
import { useMailViewController } from './useMailViewController';

export function MailView() {
  return useMailViewElement();
}

function useMailViewElement() {
  const [searchParams] = useSearchParams();
  const { token, user } = useAuth();
  const { i18n, t } = useTranslation('apps');
  const timeZone = normalizeTimeZone(user?.time_zone);
  const toast = useFeedback();
  const notify = useMemo(
    () => ({
      success: (message: string) => toast.success(message),
    }),
    [toast],
  );
  const controllerMessages = useMemo(
    () => ({
      loadFailed: t('mail.errors.loadFailed'),
      messageLoadFailed: t('mail.errors.messageLoadFailed'),
      accountCreateFailed: t('mail.errors.accountCreateFailed'),
      accountUpdateFailed: t('mail.errors.accountUpdateFailed'),
      syncFailed: t('mail.errors.syncFailed'),
      aiFailed: t('mail.errors.aiFailed'),
      sendFailed: t('mail.errors.sendFailed'),
      accountConnected: t('mail.account.connected'),
      accountUpdated: t('mail.account.updated'),
      syncQueued: t('mail.syncQueued'),
      draftCreated: t('mail.draft.created'),
      draftSent: t('mail.draft.sent'),
    }),
    [t],
  );
  const view =
    searchParams.get('view') === 'drafts'
      ? 'drafts'
      : searchParams.get('view') === 'settings'
        ? 'settings'
        : 'messages';
  const unread = searchParams.get('unread') === 'true';
  const starred = searchParams.get('starred') === 'true';
  const { state, selectedDraft, actions } = useMailViewController({
    token,
    view,
    unread,
    starred,
    messages: controllerMessages,
    notify,
  });
  const {
    accounts,
    messages,
    drafts,
    selectedMessageId,
    selectedDraftId,
    detail,
    summary,
    query,
    replyInstruction,
    accountForm,
    accountEditForms,
    busy,
    error,
  } = state;

  return (
    <div className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-app-border px-4 py-3">
        <div className="min-w-0">
          <p className="app-text-caption text-app-ink/55">
            {t('mail.eyebrow')}
          </p>
          <h1 className="app-text-title-md truncate">{t('mail.title')}</h1>
        </div>
        {view === 'messages' ? (
          <div className="flex min-w-0 items-center gap-2">
            <div className="relative w-[280px] max-w-[40vw]">
              <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-app-ink/35" />
              <input
                aria-label={t('mail.searchPlaceholder')}
                className={`${fieldClassName} pl-9`}
                onChange={(event) => actions.setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void actions.refresh(query);
                }}
                placeholder={t('mail.searchPlaceholder')}
                value={query}
              />
            </div>
            <button
              className={actionButtonClassName}
              disabled={busy}
              onClick={() => void actions.refresh(query)}
              type="button"
            >
              <Search size={16} />
              <span>{t('mail.actions.search')}</span>
            </button>
          </div>
        ) : null}
      </header>

      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      {view === 'settings' ? (
        <MailSettingsView
          accountEditForms={accountEditForms}
          accountForm={accountForm}
          accounts={accounts}
          busy={busy}
          onChangeAccountForm={actions.setAccountForm}
          onChangeAccountEditForm={actions.setAccountEditForm}
          onCreateAccount={actions.createAccount}
          onSyncAccount={actions.syncAccount}
          onUpdateAccount={actions.updateAccount}
        />
      ) : accounts.length === 0 ? (
        <NoMailAccountState />
      ) : (
        <main className="grid min-h-0 flex-1 grid-cols-[minmax(320px,420px)_1fr] overflow-hidden">
          {view === 'drafts' ? (
            <DraftList
              drafts={drafts}
              onSelect={actions.selectDraft}
              selectedId={selectedDraftId}
            />
          ) : (
            <MessageList
              locale={i18n.language}
              messages={messages}
              onSelect={actions.selectMessage}
              onStar={(message) => void actions.starMessage(message)}
              selectedId={selectedMessageId}
              timeZone={timeZone}
            />
          )}

          {view === 'drafts' ? (
            <DraftEditor
              busy={busy}
              draft={selectedDraft}
              onChange={actions.changeDraft}
              onSend={actions.sendDraft}
            />
          ) : (
            <MessageDetail
              busy={busy}
              detail={detail}
              locale={i18n.language}
              replyInstruction={replyInstruction}
              summary={summary}
              timeZone={timeZone}
              onCreateDraft={actions.createReplyDraft}
              onInstructionChange={actions.setReplyInstruction}
              onSummarize={actions.summarizeMessage}
            />
          )}
        </main>
      )}
    </div>
  );
}
