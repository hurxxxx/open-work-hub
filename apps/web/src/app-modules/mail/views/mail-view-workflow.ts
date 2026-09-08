import type {
  MailAccount,
  MailAccountConnectionPayload,
  MailConnectionTestResponse,
  MailDraft,
  MailMessage,
  MailMessageDetail,
  MailMessageListResponse,
  MailSummaryResponse,
  MailSyncResponse,
} from '../api/mail-api';
import { normalizeAccountPayload } from './mail-view-model';

export interface MailAdapter {
  listAccounts(token: string): Promise<MailAccount[]>;
  listMessages(
    token: string,
    params: {
      query?: string;
      unread?: boolean;
      starred?: boolean;
      limit?: number;
    },
  ): Promise<MailMessageListResponse>;
  listDrafts(token: string): Promise<MailDraft[]>;
  getMessage(token: string, messageId: string): Promise<MailMessageDetail>;
  updateFlags(
    token: string,
    messageId: string,
    payload: { is_read?: boolean; is_starred?: boolean },
  ): Promise<MailMessage>;
  testAccount(
    token: string,
    payload: MailAccountConnectionPayload,
  ): Promise<MailConnectionTestResponse>;
  createAccount(
    token: string,
    payload: MailAccountConnectionPayload,
  ): Promise<MailAccount>;
  updateAccount(
    token: string,
    accountId: string,
    payload: Partial<MailAccountConnectionPayload>,
  ): Promise<MailAccount>;
  syncAccount(token: string, accountId: string): Promise<MailSyncResponse>;
  summarizeMessage(
    token: string,
    messageId: string,
  ): Promise<MailSummaryResponse>;
  createReplyDraft(
    token: string,
    messageId: string,
    instruction: string,
  ): Promise<MailDraft>;
  updateDraft(
    token: string,
    draftId: string,
    payload: Partial<
      Pick<
        MailDraft,
        | 'to_text'
        | 'cc_text'
        | 'bcc_text'
        | 'subject'
        | 'text_body'
        | 'html_body'
      >
    >,
  ): Promise<MailDraft>;
  sendDraft(token: string, draftId: string): Promise<MailDraft>;
}

export interface MailSnapshot {
  accounts: MailAccount[];
  messages: MailMessage[];
  drafts: MailDraft[];
}

export interface MailCommandContext {
  adapter: MailAdapter;
  token: string;
}

export interface LoadMailSnapshotInput extends MailCommandContext {
  query: string;
  unread: boolean;
  starred: boolean;
  limit?: number;
}

export type CreateMailAccountResult =
  | { status: 'created'; account: MailAccount }
  | { status: 'connection-failed'; message: string };

export type DetailReadMarkResult =
  | { status: 'already-read' }
  | {
      status: 'pending';
      optimistic: MailMessageDetail;
      rollback: MailMessageDetail;
      commit: Promise<
        | { status: 'updated'; message: MailMessage }
        | { status: 'rollback'; message: MailMessageDetail }
      >;
    };

export async function loadMailSnapshot({
  adapter,
  token,
  query,
  unread,
  starred,
  limit = 75,
}: LoadMailSnapshotInput): Promise<MailSnapshot> {
  const [accounts, messageRows, drafts] = await Promise.all([
    adapter.listAccounts(token),
    adapter.listMessages(token, {
      query: query.trim() || undefined,
      unread,
      starred,
      limit,
    }),
    adapter.listDrafts(token),
  ]);
  return { accounts, messages: messageRows.items, drafts };
}

export function failedConnectionMessage(
  test: MailConnectionTestResponse,
): string {
  return [test.incoming_error, test.smtp_error].filter(Boolean).join(' / ');
}

export async function createMailAccountCommand(
  context: MailCommandContext,
  form: MailAccountConnectionPayload,
): Promise<CreateMailAccountResult> {
  const payload = normalizeAccountPayload(form);
  const test = await context.adapter.testAccount(context.token, payload);
  if (!test.incoming_ok || !test.smtp_ok) {
    return {
      status: 'connection-failed',
      message: failedConnectionMessage(test),
    };
  }
  const account = await context.adapter.createAccount(context.token, payload);
  return { status: 'created', account };
}

export async function updateMailAccountCommand(
  context: MailCommandContext,
  accountId: string,
  form: MailAccountConnectionPayload,
): Promise<MailAccount> {
  const payload = normalizeAccountPayload(form, {
    copySharedCredentials: false,
  });
  return context.adapter.updateAccount(context.token, accountId, payload);
}

export async function sendMailDraftCommand(
  context: MailCommandContext,
  draft: MailDraft,
): Promise<MailDraft> {
  const saved = await context.adapter.updateDraft(context.token, draft.id, {
    to_text: draft.to_text,
    cc_text: draft.cc_text,
    bcc_text: draft.bcc_text,
    subject: draft.subject,
    text_body: draft.text_body,
    html_body: draft.html_body,
  });
  return context.adapter.sendDraft(context.token, saved.id);
}

export function startUnreadDetailReadMark(
  context: MailCommandContext,
  message: MailMessageDetail,
): DetailReadMarkResult {
  if (message.is_read) {
    return { status: 'already-read' };
  }
  return {
    status: 'pending',
    optimistic: { ...message, is_read: true },
    rollback: message,
    commit: context.adapter
      .updateFlags(context.token, message.id, { is_read: true })
      .then((updated) => ({ status: 'updated' as const, message: updated }))
      .catch(() => ({ status: 'rollback' as const, message })),
  };
}
