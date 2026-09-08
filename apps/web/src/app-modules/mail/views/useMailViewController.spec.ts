import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  MailAccount,
  MailAccountConnectionPayload,
  MailDraft,
  MailMessage,
  MailMessageDetail,
} from '../api/mail-api';
import {
  useMailViewController,
  type MailViewControllerMessages,
  type MailAdapter,
} from './useMailViewController';
import { blankAccount } from './mail-view-model';

function account(overrides: Partial<MailAccount> = {}): MailAccount {
  return {
    id: 'account-1',
    email_address: 'ada@example.com',
    display_name: 'Ada',
    account_label: 'Ada work',
    protocol: 'imap',
    provider_kind: 'custom',
    incoming_host: 'imap.example.com',
    incoming_port: 993,
    incoming_security: 'ssl',
    incoming_username: 'ada@example.com',
    smtp_host: 'smtp.example.com',
    smtp_port: 587,
    smtp_security: 'starttls',
    smtp_username: 'ada@example.com',
    sync_enabled: true,
    status: 'active',
    last_sync_at: null,
    last_error: null,
    last_sync_new_count: 0,
    last_sync_updated_count: 0,
    last_sync_deleted_count: 0,
    ...overrides,
  };
}

function message(overrides: Partial<MailMessage> = {}): MailMessage {
  return {
    id: 'message-1',
    account_id: 'account-1',
    folder: 'inbox',
    subject: 'Subject',
    from_text: 'Ada <ada@example.com>',
    to_text: 'team@example.com',
    cc_text: '',
    snippet: 'Hello',
    received_at: '2026-05-30T00:00:00Z',
    is_read: true,
    is_starred: false,
    has_attachments: false,
    ...overrides,
  };
}

function detail(overrides: Partial<MailMessageDetail> = {}): MailMessageDetail {
  return {
    ...message(overrides),
    body: { text_body: 'Hello', html_body: '<p>Hello</p>' },
    attachments: [],
    ...overrides,
  };
}

function draft(overrides: Partial<MailDraft> = {}): MailDraft {
  return {
    id: 'draft-1',
    account_id: 'account-1',
    source_message_id: null,
    to_text: 'team@example.com',
    cc_text: '',
    bcc_text: '',
    subject: 'Draft',
    text_body: 'Draft body',
    html_body: '',
    ai_generated: false,
    status: 'draft',
    send_error: null,
    sent_message_id: null,
    sent_at: null,
    ...overrides,
  };
}

function payload(
  overrides: Partial<MailAccountConnectionPayload> = {},
): MailAccountConnectionPayload {
  return {
    ...blankAccount(),
    email_address: 'ada@example.com',
    incoming_host: 'imap.example.com',
    incoming_username: 'ada@example.com',
    incoming_password: 'secret',
    smtp_host: 'smtp.example.com',
    ...overrides,
  };
}

function messages(): MailViewControllerMessages {
  return {
    loadFailed: 'load failed',
    messageLoadFailed: 'message load failed',
    accountCreateFailed: 'account create failed',
    accountUpdateFailed: 'account update failed',
    syncFailed: 'sync failed',
    aiFailed: 'ai failed',
    sendFailed: 'send failed',
    accountConnected: 'account connected',
    accountUpdated: 'account updated',
    syncQueued: 'sync queued',
    draftCreated: 'draft created',
    draftSent: 'draft sent',
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

function adapter(overrides: Partial<MailAdapter> = {}): MailAdapter {
  return {
    listAccounts: vi.fn().mockResolvedValue([account()]),
    listMessages: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    listDrafts: vi.fn().mockResolvedValue([]),
    getMessage: vi.fn().mockResolvedValue(detail()),
    updateFlags: vi.fn().mockResolvedValue(message()),
    testAccount: vi.fn().mockResolvedValue({
      incoming_ok: true,
      smtp_ok: true,
      incoming_error: null,
      smtp_error: null,
    }),
    createAccount: vi.fn().mockResolvedValue(account()),
    updateAccount: vi.fn().mockResolvedValue(account()),
    syncAccount: vi
      .fn()
      .mockResolvedValue({ account: account(), queued: true, job_id: 'job-1' }),
    summarizeMessage: vi
      .fn()
      .mockResolvedValue({ message_id: 'message-1', summary: 'Summary' }),
    createReplyDraft: vi.fn().mockResolvedValue(draft()),
    updateDraft: vi.fn().mockResolvedValue(draft()),
    sendDraft: vi.fn().mockResolvedValue(draft({ status: 'sent' })),
    ...overrides,
  };
}

function renderController(
  options: {
    client?: MailAdapter;
    view?: 'messages' | 'drafts' | 'settings';
    unread?: boolean;
    starred?: boolean;
  } = {},
) {
  const notify = { success: vi.fn() };
  const client = options.client ?? adapter();
  const rendered = renderHook(() =>
    useMailViewController({
      token: 'token-1',
      view: options.view ?? 'messages',
      unread: options.unread ?? false,
      starred: options.starred ?? false,
      messages: messages(),
      notify,
      client,
    }),
  );
  return { ...rendered, client, notify };
}

describe('useMailViewController', () => {
  it('loads mail snapshots with trimmed message query and filters', async () => {
    const client = adapter();
    const { result } = renderController({
      client,
      starred: true,
      unread: true,
    });

    await waitFor(() => expect(client.listMessages).toHaveBeenCalledTimes(1));
    vi.mocked(client.listMessages).mockClear();

    act(() => {
      result.current.actions.setQuery('  spec  ');
    });
    await act(async () => {
      await result.current.actions.refresh('  spec  ');
    });

    expect(client.listMessages).toHaveBeenCalledWith('token-1', {
      query: 'spec',
      unread: true,
      starred: true,
      limit: 75,
    });
  });

  it('marks unread message details as read optimistically and rolls back on flag failure', async () => {
    const unreadMessage = message({ id: 'message-1', is_read: false });
    const client = adapter({
      listMessages: vi
        .fn()
        .mockResolvedValue({ items: [unreadMessage], total: 1 }),
      getMessage: vi
        .fn()
        .mockResolvedValue(detail({ id: 'message-1', is_read: false })),
      updateFlags: vi.fn().mockRejectedValue(new Error('flag failed')),
    });
    const { result } = renderController({ client });

    await waitFor(() => {
      expect(client.updateFlags).toHaveBeenCalledWith('token-1', 'message-1', {
        is_read: true,
      });
    });
    await waitFor(() => {
      expect(result.current.state.detail?.is_read).toBe(false);
      expect(result.current.state.messages[0]?.is_read).toBe(false);
    });
  });

  it('blocks account creation when the connection test fails', async () => {
    const client = adapter({
      testAccount: vi.fn().mockResolvedValue({
        incoming_ok: false,
        smtp_ok: false,
        incoming_error: 'incoming failed',
        smtp_error: 'smtp failed',
      }),
    });
    const { result } = renderController({ client, view: 'settings' });

    act(() => {
      result.current.actions.setAccountForm(payload());
    });
    await act(async () => {
      await result.current.actions.createAccount();
    });

    expect(client.createAccount).not.toHaveBeenCalled();
    expect(result.current.state.error).toBe('incoming failed / smtp failed');
    expect(result.current.state.busy).toBe(false);
  });

  it('updates draft fields before sending and stores the sent draft', async () => {
    const initialDraft = draft({ id: 'draft-1', subject: 'Draft subject' });
    const savedDraft = draft({ id: 'draft-1', subject: 'Edited subject' });
    const sentDraft = draft({
      id: 'draft-1',
      status: 'sent',
      subject: 'Edited subject',
    });
    const client = adapter({
      listDrafts: vi.fn().mockResolvedValue([initialDraft]),
      updateDraft: vi.fn().mockResolvedValue(savedDraft),
      sendDraft: vi.fn().mockResolvedValue(sentDraft),
    });
    const { result } = renderController({ client, view: 'drafts' });

    await waitFor(() =>
      expect(result.current.selectedDraft?.id).toBe('draft-1'),
    );
    await act(async () => {
      await result.current.actions.sendDraft({
        ...initialDraft,
        subject: 'Edited subject',
      });
    });

    expect(client.updateDraft).toHaveBeenCalledWith(
      'token-1',
      'draft-1',
      expect.objectContaining({ subject: 'Edited subject' }),
    );
    expect(client.sendDraft).toHaveBeenCalledWith('token-1', 'draft-1');
    expect(
      vi.mocked(client.updateDraft).mock.invocationCallOrder[0],
    ).toBeLessThan(vi.mocked(client.sendDraft).mock.invocationCallOrder[0]);
    expect(result.current.state.drafts[0]).toEqual(sentDraft);
  });

  it('ignores stale message detail responses after selection changes', async () => {
    const firstDetail = deferred<MailMessageDetail>();
    const client = adapter({
      listMessages: vi.fn().mockResolvedValue({
        items: [message({ id: 'message-1' }), message({ id: 'message-2' })],
        total: 2,
      }),
      getMessage: vi.fn((_, messageId: string) =>
        messageId === 'message-1'
          ? firstDetail.promise
          : Promise.resolve(detail({ id: 'message-2', subject: 'Second' })),
      ),
    });
    const { result } = renderController({ client });

    await waitFor(() =>
      expect(result.current.state.selectedMessageId).toBe('message-1'),
    );
    act(() => {
      result.current.actions.selectMessage('message-2');
    });
    await waitFor(() =>
      expect(result.current.state.detail?.id).toBe('message-2'),
    );

    await act(async () => {
      firstDetail.resolve(detail({ id: 'message-1', subject: 'First' }));
      await firstDetail.promise;
    });

    expect(result.current.state.detail?.id).toBe('message-2');
  });
});
