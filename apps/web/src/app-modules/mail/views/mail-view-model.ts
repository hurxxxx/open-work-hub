import { formatDateTime } from '@/src/platform/time/time-utils';
import type {
  MailAccount,
  MailAccountConnectionPayload,
  MailDraft,
  MailMessage,
  MailMessageDetail,
} from '../api/mail-api';

export const fieldClassName =
  'app-text-body w-full rounded-md border border-app-border bg-app-bg px-3 py-2 text-app-ink transition-colors placeholder:text-app-ink/35 focus:border-app-accent focus:outline-none';

export const actionButtonClassName =
  'inline-flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 app-text-control text-app-ink transition-colors hover:bg-app-surface-muted disabled:cursor-not-allowed disabled:opacity-50';

export interface MailViewState {
  accounts: MailAccount[];
  messages: MailMessage[];
  drafts: MailDraft[];
  selectedMessageId: string | null;
  selectedDraftId: string | null;
  detail: MailMessageDetail | null;
  summary: string;
  query: string;
  replyInstruction: string;
  accountForm: MailAccountConnectionPayload;
  accountEditForms: Record<string, MailAccountConnectionPayload>;
  busy: boolean;
  error: string | null;
}

export type MailViewAction =
  | {
      type: 'loadSuccess';
      accounts: MailAccount[];
      messages: MailMessage[];
      drafts: MailDraft[];
    }
  | { type: 'setError'; error: string | null }
  | { type: 'setBusy'; busy: boolean }
  | { type: 'setQuery'; query: string }
  | { type: 'setSelectedMessageId'; messageId: string | null }
  | { type: 'setSelectedDraftId'; draftId: string | null }
  | { type: 'clearDetail' }
  | { type: 'messageLoadStart' }
  | { type: 'messageLoadSuccess'; message: MailMessageDetail }
  | { type: 'messageReadOptimistic'; message: MailMessageDetail }
  | { type: 'messageFlagUpdate'; message: MailMessage }
  | { type: 'messageFlagRollback'; message: MailMessage }
  | { type: 'setSummary'; summary: string }
  | { type: 'setReplyInstruction'; replyInstruction: string }
  | { type: 'setAccountForm'; accountForm: MailAccountConnectionPayload }
  | { type: 'resetAccountForm' }
  | {
      type: 'setAccountEditForm';
      accountId: string;
      form: MailAccountConnectionPayload;
    }
  | { type: 'accountUpdated'; account: MailAccount }
  | { type: 'draftUpsert'; draft: MailDraft; select?: boolean }
  | { type: 'draftChange'; draft: MailDraft | null };

export function blankAccount(): MailAccountConnectionPayload {
  return {
    email_address: '',
    display_name: '',
    account_label: '',
    protocol: 'imap',
    incoming_host: '',
    incoming_port: 993,
    incoming_security: 'ssl',
    incoming_username: '',
    incoming_password: '',
    smtp_host: '',
    smtp_port: 587,
    smtp_security: 'starttls',
    smtp_username: '',
    smtp_password: '',
  };
}

export type MailAccountFormChange = {
  [Field in keyof MailAccountConnectionPayload]: {
    field: Field;
    value: MailAccountConnectionPayload[Field];
  };
}[keyof MailAccountConnectionPayload];

export interface MailAccountFormRules {
  copySharedCredentials?: boolean;
}

function shouldMirrorSharedCredential({
  copySharedCredentials,
  previousSource,
  target,
}: {
  copySharedCredentials: boolean;
  previousSource: string;
  target: string;
}): boolean {
  return copySharedCredentials && (!target || target === previousSource);
}

export function applyAccountFormChange(
  form: MailAccountConnectionPayload,
  change: MailAccountFormChange,
  rules: MailAccountFormRules = {},
): MailAccountConnectionPayload {
  const copySharedCredentials = rules.copySharedCredentials ?? true;
  if (change.field === 'incoming_username') {
    return {
      ...form,
      incoming_username: change.value,
      smtp_username: shouldMirrorSharedCredential({
        copySharedCredentials,
        previousSource: form.incoming_username,
        target: form.smtp_username,
      })
        ? change.value
        : form.smtp_username,
    };
  }
  if (change.field === 'incoming_password') {
    return {
      ...form,
      incoming_password: change.value,
      smtp_password: shouldMirrorSharedCredential({
        copySharedCredentials,
        previousSource: form.incoming_password,
        target: form.smtp_password,
      })
        ? change.value
        : form.smtp_password,
    };
  }
  return { ...form, [change.field]: change.value };
}

export const MAIL_VIEW_INITIAL_STATE: MailViewState = {
  accounts: [],
  messages: [],
  drafts: [],
  selectedMessageId: null,
  selectedDraftId: null,
  detail: null,
  summary: '',
  query: '',
  replyInstruction: '',
  accountForm: blankAccount(),
  accountEditForms: {},
  busy: false,
  error: null,
};

export function accountToForm(
  account: MailAccount,
): MailAccountConnectionPayload {
  return {
    email_address: account.email_address,
    display_name: account.display_name,
    account_label: account.account_label,
    protocol: account.protocol === 'pop3' ? 'pop3' : 'imap',
    incoming_host: account.incoming_host,
    incoming_port: account.incoming_port,
    incoming_security:
      account.incoming_security === 'starttls' ||
      account.incoming_security === 'none'
        ? account.incoming_security
        : 'ssl',
    incoming_username: account.incoming_username,
    incoming_password: '',
    smtp_host: account.smtp_host,
    smtp_port: account.smtp_port,
    smtp_security:
      account.smtp_security === 'ssl' || account.smtp_security === 'none'
        ? account.smtp_security
        : 'starttls',
    smtp_username: account.smtp_username,
    smtp_password: '',
  };
}

function looksLikePartialCopy(value: string, source: string): boolean {
  const trimmed = value.trim();
  const sourceTrimmed = source.trim();
  return Boolean(
    trimmed &&
      trimmed.length < sourceTrimmed.length &&
      sourceTrimmed.startsWith(trimmed),
  );
}

export function normalizeAccountPayload(
  form: MailAccountConnectionPayload,
  options: { copySharedCredentials: boolean } = { copySharedCredentials: true },
): MailAccountConnectionPayload {
  const incomingUsername = form.incoming_username.trim();
  const incomingPassword = form.incoming_password;
  const smtpUsername = form.smtp_username.trim();
  const smtpPassword = form.smtp_password;
  return {
    ...form,
    email_address: form.email_address.trim(),
    account_label: form.account_label.trim(),
    incoming_host: form.incoming_host.trim(),
    incoming_username: incomingUsername,
    smtp_host: form.smtp_host.trim(),
    smtp_username:
      options.copySharedCredentials &&
      (!smtpUsername || looksLikePartialCopy(smtpUsername, incomingUsername))
        ? incomingUsername
        : smtpUsername,
    smtp_password:
      options.copySharedCredentials &&
      (!smtpPassword || looksLikePartialCopy(smtpPassword, incomingPassword))
        ? incomingPassword
        : smtpPassword,
  };
}

export function nextAccountEditForms(
  accounts: MailAccount[],
  current: Record<string, MailAccountConnectionPayload>,
): Record<string, MailAccountConnectionPayload> {
  const next: Record<string, MailAccountConnectionPayload> = {};
  for (const account of accounts) {
    next[account.id] = current[account.id] ?? accountToForm(account);
  }
  return next;
}

export function replaceMessage(
  messages: MailMessage[],
  updated: MailMessage,
): MailMessage[] {
  return messages.map((message) =>
    message.id === updated.id ? updated : message,
  );
}

export function patchMessage(
  messages: MailMessage[],
  messageId: string,
  patch: Partial<MailMessage>,
): MailMessage[] {
  return messages.map((message) =>
    message.id === messageId ? { ...message, ...patch } : message,
  );
}

export function mailViewReducer(
  state: MailViewState,
  action: MailViewAction,
): MailViewState {
  switch (action.type) {
    case 'loadSuccess': {
      const selectedMessageId =
        state.selectedMessageId &&
        action.messages.some(
          (message) => message.id === state.selectedMessageId,
        )
          ? state.selectedMessageId
          : (action.messages[0]?.id ?? null);
      const selectedDraftId =
        state.selectedDraftId &&
        action.drafts.some((draft) => draft.id === state.selectedDraftId)
          ? state.selectedDraftId
          : (action.drafts[0]?.id ?? null);
      return {
        ...state,
        accounts: action.accounts,
        messages: action.messages,
        drafts: action.drafts,
        selectedMessageId,
        selectedDraftId,
        accountEditForms: nextAccountEditForms(
          action.accounts,
          state.accountEditForms,
        ),
      };
    }
    case 'setError':
      return { ...state, error: action.error };
    case 'setBusy':
      return { ...state, busy: action.busy };
    case 'setQuery':
      return { ...state, query: action.query };
    case 'setSelectedMessageId':
      return { ...state, selectedMessageId: action.messageId };
    case 'setSelectedDraftId':
      return { ...state, selectedDraftId: action.draftId };
    case 'clearDetail':
      return { ...state, detail: null };
    case 'messageLoadStart':
      return { ...state, summary: '' };
    case 'messageLoadSuccess':
      return { ...state, detail: action.message };
    case 'messageReadOptimistic':
      return {
        ...state,
        detail: { ...action.message, is_read: true },
        messages: patchMessage(state.messages, action.message.id, {
          is_read: true,
        }),
      };
    case 'messageFlagUpdate':
      return {
        ...state,
        messages: replaceMessage(state.messages, action.message),
        detail:
          state.detail?.id === action.message.id
            ? { ...state.detail, ...action.message }
            : state.detail,
      };
    case 'messageFlagRollback':
      return {
        ...state,
        messages: replaceMessage(state.messages, action.message),
        detail:
          state.detail?.id === action.message.id
            ? { ...state.detail, ...action.message }
            : state.detail,
      };
    case 'setSummary':
      return { ...state, summary: action.summary };
    case 'setReplyInstruction':
      return { ...state, replyInstruction: action.replyInstruction };
    case 'setAccountForm':
      return { ...state, accountForm: action.accountForm };
    case 'resetAccountForm':
      return { ...state, accountForm: blankAccount() };
    case 'setAccountEditForm':
      return {
        ...state,
        accountEditForms: {
          ...state.accountEditForms,
          [action.accountId]: action.form,
        },
      };
    case 'accountUpdated':
      return {
        ...state,
        accounts: state.accounts.map((account) =>
          account.id === action.account.id ? action.account : account,
        ),
        accountEditForms: {
          ...state.accountEditForms,
          [action.account.id]: accountToForm(action.account),
        },
      };
    case 'draftUpsert':
      return {
        ...state,
        drafts: [
          action.draft,
          ...state.drafts.filter((draft) => draft.id !== action.draft.id),
        ],
        selectedDraftId: action.select
          ? action.draft.id
          : state.selectedDraftId,
      };
    case 'draftChange':
      if (!action.draft) {
        return state;
      }
      return {
        ...state,
        drafts: state.drafts.map((draft) =>
          draft.id === action.draft?.id ? action.draft : draft,
        ),
      };
    default:
      return state;
  }
}

export function formatMailDate(
  value: string | null,
  locale: string,
  timeZone: string,
) {
  if (!value) return '';
  return formatDateTime(value, {
    dateStyle: 'medium',
    locale,
    timeStyle: 'short',
    timeZone,
  });
}
