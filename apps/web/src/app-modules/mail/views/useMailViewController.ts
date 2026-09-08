import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';

import {
  createMailAccount,
  createReplyDraft,
  getMailMessage,
  listMailAccounts,
  listMailDrafts,
  listMailMessages,
  sendMailDraft,
  summarizeMailMessage,
  syncMailAccount,
  testMailAccount,
  updateMailAccount,
  updateMailDraft,
  updateMailFlags,
  type MailAccountConnectionPayload,
  type MailDraft,
  type MailMessage,
} from '../api/mail-api';
import {
  MAIL_VIEW_INITIAL_STATE,
  mailViewReducer,
  type MailViewState,
} from './mail-view-model';
import {
  createMailAccountCommand,
  loadMailSnapshot,
  sendMailDraftCommand,
  startUnreadDetailReadMark,
  updateMailAccountCommand,
  type MailAdapter,
} from './mail-view-workflow';

export type { MailAdapter } from './mail-view-workflow';

export interface MailViewControllerMessages {
  loadFailed: string;
  messageLoadFailed: string;
  accountCreateFailed: string;
  accountUpdateFailed: string;
  syncFailed: string;
  aiFailed: string;
  sendFailed: string;
  accountConnected: string;
  accountUpdated: string;
  syncQueued: string;
  draftCreated: string;
  draftSent: string;
}

export interface MailViewControllerNotify {
  success(message: string): void;
}

export interface MailViewControllerOptions {
  token: string | null;
  view: 'messages' | 'drafts' | 'settings';
  unread: boolean;
  starred: boolean;
  messages: MailViewControllerMessages;
  notify: MailViewControllerNotify;
  client?: MailAdapter;
}

export interface MailViewController {
  state: MailViewState;
  selectedDraft: MailDraft | null;
  actions: {
    refresh(nextQuery?: string): Promise<void>;
    setQuery(query: string): void;
    selectMessage(messageId: string | null): void;
    selectDraft(draftId: string | null): void;
    setAccountForm(accountForm: MailAccountConnectionPayload): void;
    setAccountEditForm(
      accountId: string,
      form: MailAccountConnectionPayload,
    ): void;
    createAccount(): Promise<void>;
    updateAccount(accountId: string): Promise<void>;
    syncAccount(accountId: string): Promise<void>;
    starMessage(message: MailMessage): Promise<void>;
    summarizeMessage(): Promise<void>;
    setReplyInstruction(replyInstruction: string): void;
    createReplyDraft(): Promise<void>;
    changeDraft(draft: MailDraft | null): void;
    sendDraft(draft: MailDraft | null): Promise<void>;
  };
}

export const mailAdapter: MailAdapter = {
  listAccounts: listMailAccounts,
  listMessages: listMailMessages,
  listDrafts: listMailDrafts,
  getMessage: getMailMessage,
  updateFlags: updateMailFlags,
  testAccount: testMailAccount,
  createAccount: createMailAccount,
  updateAccount: updateMailAccount,
  syncAccount: syncMailAccount,
  summarizeMessage: summarizeMailMessage,
  createReplyDraft,
  updateDraft: updateMailDraft,
  sendDraft: sendMailDraft,
};

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function useMailViewController({
  token,
  view,
  unread,
  starred,
  messages,
  notify,
  client = mailAdapter,
}: MailViewControllerOptions): MailViewController {
  const [state, dispatch] = useReducer(
    mailViewReducer,
    MAIL_VIEW_INITIAL_STATE,
  );
  const queryRef = useRef(state.query);
  queryRef.current = state.query;
  const selectedDraft = useMemo(
    () =>
      state.drafts.find((draft) => draft.id === state.selectedDraftId) ?? null,
    [state.drafts, state.selectedDraftId],
  );

  const loadAll = useCallback(
    async (nextQuery?: string) => {
      if (!token) return;
      const queryForRequest = nextQuery ?? queryRef.current;
      dispatch({ type: 'setError', error: null });
      const snapshot = await loadMailSnapshot({
        adapter: client,
        token,
        query: queryForRequest,
        unread,
        starred,
      });
      dispatch({
        type: 'loadSuccess',
        accounts: snapshot.accounts,
        messages: snapshot.messages,
        drafts: snapshot.drafts,
      });
    },
    [client, starred, token, unread],
  );

  const refresh = useCallback(
    async (nextQuery?: string) => {
      try {
        await loadAll(nextQuery);
      } catch (err) {
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.loadFailed),
        });
      }
    },
    [loadAll, messages.loadFailed],
  );

  useEffect(() => {
    void refresh();
  }, [refresh, view]);

  useEffect(() => {
    if (!token || !state.selectedMessageId) {
      dispatch({ type: 'clearDetail' });
      return;
    }
    let cancelled = false;
    dispatch({ type: 'messageLoadStart' });
    client
      .getMessage(token, state.selectedMessageId)
      .then((message) => {
        if (cancelled) return;
        dispatch({ type: 'messageLoadSuccess', message });
        const readMark = startUnreadDetailReadMark(
          { adapter: client, token },
          message,
        );
        if (readMark.status === 'pending') {
          dispatch({
            type: 'messageReadOptimistic',
            message: readMark.optimistic,
          });
          void readMark.commit.then((outcome) => {
            if (cancelled) return;
            if (outcome.status === 'updated') {
              dispatch({ type: 'messageFlagUpdate', message: outcome.message });
            } else {
              dispatch({
                type: 'messageFlagRollback',
                message: outcome.message,
              });
            }
          });
        }
      })
      .catch((err) => {
        if (cancelled) return;
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.messageLoadFailed),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [client, messages.messageLoadFailed, state.selectedMessageId, token]);

  const createAccountAction = useCallback(async () => {
    if (!token) return;
    dispatch({ type: 'setBusy', busy: true });
    dispatch({ type: 'setError', error: null });
    try {
      const result = await createMailAccountCommand(
        { adapter: client, token },
        state.accountForm,
      );
      if (result.status === 'connection-failed') {
        dispatch({
          type: 'setError',
          error: result.message,
        });
        return;
      }
      dispatch({ type: 'resetAccountForm' });
      notify.success(messages.accountConnected);
      await loadAll();
    } catch (err) {
      dispatch({
        type: 'setError',
        error: errorMessage(err, messages.accountCreateFailed),
      });
    } finally {
      dispatch({ type: 'setBusy', busy: false });
    }
  }, [
    client,
    loadAll,
    messages.accountConnected,
    messages.accountCreateFailed,
    notify,
    state.accountForm,
    token,
  ]);

  const updateAccountAction = useCallback(
    async (accountId: string) => {
      if (!token) return;
      const form = state.accountEditForms[accountId];
      if (!form) return;
      dispatch({ type: 'setBusy', busy: true });
      dispatch({ type: 'setError', error: null });
      try {
        const updated = await updateMailAccountCommand(
          { adapter: client, token },
          accountId,
          form,
        );
        dispatch({ type: 'accountUpdated', account: updated });
        notify.success(messages.accountUpdated);
        await loadAll();
      } catch (err) {
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.accountUpdateFailed),
        });
      } finally {
        dispatch({ type: 'setBusy', busy: false });
      }
    },
    [
      client,
      loadAll,
      messages.accountUpdateFailed,
      messages.accountUpdated,
      notify,
      state.accountEditForms,
      token,
    ],
  );

  const syncAccountAction = useCallback(
    async (accountId: string) => {
      if (!token) return;
      dispatch({ type: 'setBusy', busy: true });
      dispatch({ type: 'setError', error: null });
      try {
        const response = await client.syncAccount(token, accountId);
        dispatch({ type: 'accountUpdated', account: response.account });
        notify.success(messages.syncQueued);
        await loadAll();
      } catch (err) {
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.syncFailed),
        });
      } finally {
        dispatch({ type: 'setBusy', busy: false });
      }
    },
    [client, loadAll, messages.syncFailed, messages.syncQueued, notify, token],
  );

  const starMessage = useCallback(
    async (message: MailMessage) => {
      if (!token) return;
      const optimistic = { ...message, is_starred: !message.is_starred };
      dispatch({ type: 'messageFlagUpdate', message: optimistic });
      try {
        const updated = await client.updateFlags(token, message.id, {
          is_starred: optimistic.is_starred,
        });
        dispatch({ type: 'messageFlagUpdate', message: updated });
      } catch (err) {
        dispatch({ type: 'messageFlagRollback', message });
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.loadFailed),
        });
      }
    },
    [client, messages.loadFailed, token],
  );

  const summarizeMessageAction = useCallback(async () => {
    if (!token || !state.detail) return;
    dispatch({ type: 'setBusy', busy: true });
    dispatch({ type: 'setError', error: null });
    try {
      const result = await client.summarizeMessage(token, state.detail.id);
      dispatch({ type: 'setSummary', summary: result.summary });
    } catch (err) {
      dispatch({
        type: 'setError',
        error: errorMessage(err, messages.aiFailed),
      });
    } finally {
      dispatch({ type: 'setBusy', busy: false });
    }
  }, [client, messages.aiFailed, state.detail, token]);

  const createReplyDraftAction = useCallback(async () => {
    if (!token || !state.detail) return;
    dispatch({ type: 'setBusy', busy: true });
    dispatch({ type: 'setError', error: null });
    try {
      const draft = await client.createReplyDraft(
        token,
        state.detail.id,
        state.replyInstruction,
      );
      dispatch({ type: 'draftUpsert', draft, select: true });
      notify.success(messages.draftCreated);
    } catch (err) {
      dispatch({
        type: 'setError',
        error: errorMessage(err, messages.aiFailed),
      });
    } finally {
      dispatch({ type: 'setBusy', busy: false });
    }
  }, [
    client,
    messages.aiFailed,
    messages.draftCreated,
    notify,
    state.detail,
    state.replyInstruction,
    token,
  ]);

  const sendDraftAction = useCallback(
    async (draft: MailDraft | null) => {
      if (!token || !draft) return;
      dispatch({ type: 'setBusy', busy: true });
      dispatch({ type: 'setError', error: null });
      try {
        const sent = await sendMailDraftCommand(
          { adapter: client, token },
          draft,
        );
        dispatch({ type: 'draftUpsert', draft: sent });
        notify.success(messages.draftSent);
      } catch (err) {
        dispatch({
          type: 'setError',
          error: errorMessage(err, messages.sendFailed),
        });
      } finally {
        dispatch({ type: 'setBusy', busy: false });
      }
    },
    [client, messages.draftSent, messages.sendFailed, notify, token],
  );

  const actions = useMemo<MailViewController['actions']>(
    () => ({
      refresh,
      setQuery: (query) => dispatch({ type: 'setQuery', query }),
      selectMessage: (messageId) =>
        dispatch({ type: 'setSelectedMessageId', messageId }),
      selectDraft: (draftId) =>
        dispatch({ type: 'setSelectedDraftId', draftId }),
      setAccountForm: (accountForm) =>
        dispatch({ type: 'setAccountForm', accountForm }),
      setAccountEditForm: (accountId, form) =>
        dispatch({ type: 'setAccountEditForm', accountId, form }),
      createAccount: createAccountAction,
      updateAccount: updateAccountAction,
      syncAccount: syncAccountAction,
      starMessage,
      summarizeMessage: summarizeMessageAction,
      setReplyInstruction: (replyInstruction) =>
        dispatch({ type: 'setReplyInstruction', replyInstruction }),
      createReplyDraft: createReplyDraftAction,
      changeDraft: (draft) => dispatch({ type: 'draftChange', draft }),
      sendDraft: sendDraftAction,
    }),
    [
      createAccountAction,
      createReplyDraftAction,
      refresh,
      sendDraftAction,
      starMessage,
      summarizeMessageAction,
      syncAccountAction,
      updateAccountAction,
    ],
  );

  return {
    state,
    selectedDraft,
    actions,
  };
}
