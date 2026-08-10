import { describe, expect, it, vi } from 'vitest';

import type {
  MailAccount,
  MailAccountConnectionPayload,
  MailDraft,
  MailMessage,
  MailMessageDetail,
} from '../api/mail-api';
import { blankAccount } from './mail-view-model';
import {
  createMailAccountCommand,
  loadMailSnapshot,
  sendMailDraftCommand,
  startUnreadDetailReadMark,
  updateMailAccountCommand,
  type MailAdapter,
} from './mail-workspace-workflow';

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
    email_address: ' ada@example.com ',
    incoming_host: ' imap.example.com ',
    incoming_username: 'ada@example.com',
    incoming_password: 'secret',
    smtp_host: ' smtp.example.com ',
    ...overrides,
  };
}

function adapter(overrides: Partial<MailAdapter> = {}): MailAdapter {
  return {
    listAccounts: vi.fn().mockResolvedValue([account()]),
    listMessages: vi.fn().mockResolvedValue({ items: [message()], total: 1 }),
    listDrafts: vi.fn().mockResolvedValue([draft()]),
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

describe('mail-workspace-workflow', () => {
  it('loads snapshots with trimmed query and unread/starred filters', async () => {
    const client = adapter();

    await loadMailSnapshot({
      adapter: client,
      token: 'token-1',
      query: '  spec  ',
      unread: true,
      starred: true,
    });

    expect(client.listMessages).toHaveBeenCalledWith('token-1', {
      query: 'spec',
      unread: true,
      starred: true,
      limit: 75,
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

    const result = await createMailAccountCommand(
      { adapter: client, token: 'token-1' },
      payload(),
    );

    expect(result).toEqual({
      status: 'connection-failed',
      message: 'incoming failed / smtp failed',
    });
    expect(client.createAccount).not.toHaveBeenCalled();
  });

  it('updates accounts with credential mirroring disabled', async () => {
    const client = adapter();

    await updateMailAccountCommand(
      { adapter: client, token: 'token-1' },
      'account-1',
      payload({
        incoming_username: 'full-user@example.com',
        smtp_username: 'full',
        incoming_password: 'full-secret',
        smtp_password: 'ful',
      }),
    );

    expect(client.updateAccount).toHaveBeenCalledWith(
      'token-1',
      'account-1',
      expect.objectContaining({
        incoming_username: 'full-user@example.com',
        smtp_username: 'full',
        incoming_password: 'full-secret',
        smtp_password: 'ful',
      }),
    );
  });

  it('saves editable draft fields before sending', async () => {
    const savedDraft = draft({ id: 'draft-1', subject: 'Edited subject' });
    const sentDraft = draft({
      id: 'draft-1',
      status: 'sent',
      subject: 'Edited subject',
    });
    const client = adapter({
      updateDraft: vi.fn().mockResolvedValue(savedDraft),
      sendDraft: vi.fn().mockResolvedValue(sentDraft),
    });

    const result = await sendMailDraftCommand(
      { adapter: client, token: 'token-1' },
      draft({ subject: 'Edited subject' }),
    );

    expect(client.updateDraft).toHaveBeenCalledWith('token-1', 'draft-1', {
      to_text: 'team@example.com',
      cc_text: '',
      bcc_text: '',
      subject: 'Edited subject',
      text_body: 'Draft body',
      html_body: '',
    });
    expect(client.sendDraft).toHaveBeenCalledWith('token-1', 'draft-1');
    expect(
      vi.mocked(client.updateDraft).mock.invocationCallOrder[0],
    ).toBeLessThan(vi.mocked(client.sendDraft).mock.invocationCallOrder[0]);
    expect(result).toEqual(sentDraft);
  });

  it('returns optimistic and rollback outcomes for unread detail read-mark failures', async () => {
    const unreadDetail = detail({ is_read: false });
    const client = adapter({
      updateFlags: vi.fn().mockRejectedValue(new Error('flag failed')),
    });

    const result = startUnreadDetailReadMark(
      { adapter: client, token: 'token-1' },
      unreadDetail,
    );

    expect(result.status).toBe('pending');
    if (result.status !== 'pending') return;
    expect(result.optimistic).toMatchObject({ id: 'message-1', is_read: true });
    expect(result.rollback).toBe(unreadDetail);
    await expect(result.commit).resolves.toEqual({
      status: 'rollback',
      message: unreadDetail,
    });
  });
});
