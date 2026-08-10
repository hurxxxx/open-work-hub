import {
  apiFetchJson,
  apiFetchJsonWithMappedError,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';

export interface MailAccountConnectionPayload {
  email_address: string;
  display_name: string;
  account_label: string;
  protocol: 'imap' | 'pop3';
  incoming_host: string;
  incoming_port: number;
  incoming_security: 'ssl' | 'starttls' | 'none';
  incoming_username: string;
  incoming_password: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: 'ssl' | 'starttls' | 'none';
  smtp_username: string;
  smtp_password: string;
}

export interface MailAccount {
  id: string;
  email_address: string;
  display_name: string;
  account_label: string;
  protocol: string;
  provider_kind: string;
  incoming_host: string;
  incoming_port: number;
  incoming_security: string;
  incoming_username: string;
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
  smtp_username: string;
  sync_enabled: boolean;
  status: string;
  last_sync_at: string | null;
  last_error: string | null;
  last_sync_new_count: number;
  last_sync_updated_count: number;
  last_sync_deleted_count: number;
}

export interface MailMessage {
  id: string;
  account_id: string;
  folder: string;
  subject: string;
  from_text: string;
  to_text: string;
  cc_text: string;
  snippet: string;
  received_at: string | null;
  is_read: boolean;
  is_starred: boolean;
  has_attachments: boolean;
}

export interface MailMessageDetail extends MailMessage {
  body: {
    text_body: string;
    html_body: string;
  };
  attachments: Array<{
    id: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    disposition: string;
    downloaded_at: string | null;
  }>;
}

export interface MailDraft {
  id: string;
  account_id: string;
  source_message_id: string | null;
  to_text: string;
  cc_text: string;
  bcc_text: string;
  subject: string;
  text_body: string;
  html_body: string;
  ai_generated: boolean;
  status: string;
  send_error: string | null;
  sent_message_id: string | null;
  sent_at: string | null;
}

export interface MailMessageListResponse {
  items: MailMessage[];
  total: number;
}

export interface MailSummaryResponse {
  message_id: string;
  summary: string;
}

export interface MailConnectionTestResponse {
  incoming_ok: boolean;
  smtp_ok: boolean;
  incoming_error: string | null;
  smtp_error: string | null;
}

export interface MailSyncResponse {
  account: MailAccount;
  queued: boolean;
  job_id: string;
  task_id?: string | null;
}

function mailPath(path: string): string {
  return `/api/v1/mail${path}`;
}

async function requestWithFallback<T>(
  path: string,
  token: string,
  fallbackKey: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      path,
      token,
      init,
      (error) => new Error(error.message || i18n.t(fallbackKey)),
    );
  } catch (error) {
    if (error instanceof Error && error.message) {
      throw error;
    }
    throw new Error(i18n.t(fallbackKey));
  }
}

export async function listMailAccounts(token: string) {
  return requestWithFallback<MailAccount[]>(
    mailPath('/accounts'),
    token,
    'apps:mail.errors.loadFailed',
  );
}

export async function createMailAccount(
  token: string,
  payload: MailAccountConnectionPayload,
) {
  return requestWithFallback<MailAccount>(
    mailPath('/accounts'),
    token,
    'apps:mail.errors.accountCreateFailed',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function updateMailAccount(
  token: string,
  accountId: string,
  payload: Partial<MailAccountConnectionPayload>,
) {
  return requestWithFallback<MailAccount>(
    mailPath(`/accounts/${encodeURIComponent(accountId)}`),
    token,
    'apps:mail.errors.accountUpdateFailed',
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function testMailAccount(
  token: string,
  payload: MailAccountConnectionPayload,
) {
  return requestWithFallback<MailConnectionTestResponse>(
    mailPath('/accounts/test'),
    token,
    'apps:mail.errors.accountTestFailed',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function syncMailAccount(token: string, accountId: string) {
  return requestWithFallback<MailSyncResponse>(
    mailPath(`/accounts/${encodeURIComponent(accountId)}/sync`),
    token,
    'apps:mail.errors.syncFailed',
    { method: 'POST' },
  );
}

export async function listMailMessages(
  token: string,
  params: {
    query?: string;
    unread?: boolean;
    starred?: boolean;
    limit?: number;
  },
) {
  const search = new URLSearchParams();
  if (params.query) search.set('query', params.query);
  if (params.unread) search.set('unread', 'true');
  if (params.starred) search.set('starred', 'true');
  if (params.limit) search.set('limit', String(params.limit));
  return requestWithFallback<MailMessageListResponse>(
    mailPath(`/messages${search.size ? `?${search}` : ''}`),
    token,
    'apps:mail.errors.loadFailed',
  );
}

export async function getMailMessage(token: string, messageId: string) {
  return requestWithFallback<MailMessageDetail>(
    mailPath(`/messages/${encodeURIComponent(messageId)}`),
    token,
    'apps:mail.errors.messageLoadFailed',
  );
}

export async function updateMailFlags(
  token: string,
  messageId: string,
  payload: { is_read?: boolean; is_starred?: boolean },
) {
  return apiFetchJson<MailMessage>(
    mailPath(`/messages/${encodeURIComponent(messageId)}/flags`),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function summarizeMailMessage(token: string, messageId: string) {
  return requestWithFallback<MailSummaryResponse>(
    mailPath(`/messages/${encodeURIComponent(messageId)}/summarize`),
    token,
    'apps:mail.errors.aiFailed',
    { method: 'POST' },
  );
}

export async function createReplyDraft(
  token: string,
  messageId: string,
  instruction: string,
) {
  return requestWithFallback<MailDraft>(
    mailPath(`/messages/${encodeURIComponent(messageId)}/reply-draft`),
    token,
    'apps:mail.errors.aiFailed',
    {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    },
  );
}

export async function listMailDrafts(token: string) {
  return apiFetchJson<MailDraft[]>(mailPath('/drafts'), token);
}

export async function updateMailDraft(
  token: string,
  draftId: string,
  payload: Partial<
    Pick<
      MailDraft,
      'to_text' | 'cc_text' | 'bcc_text' | 'subject' | 'text_body' | 'html_body'
    >
  >,
) {
  return apiFetchJson<MailDraft>(
    mailPath(`/drafts/${encodeURIComponent(draftId)}`),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function sendMailDraft(token: string, draftId: string) {
  return requestWithFallback<MailDraft>(
    mailPath(`/drafts/${encodeURIComponent(draftId)}/send`),
    token,
    'apps:mail.errors.sendFailed',
    { method: 'POST' },
  );
}
