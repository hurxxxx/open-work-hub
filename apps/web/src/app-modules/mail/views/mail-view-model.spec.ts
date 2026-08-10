import { describe, expect, it } from 'vitest';

import type {
  MailAccount,
  MailAccountConnectionPayload,
  MailDraft,
  MailMessage,
  MailMessageDetail,
} from '../api/mail-api';
import {
  MAIL_VIEW_INITIAL_STATE,
  accountToForm,
  applyAccountFormChange,
  mailViewReducer,
  nextAccountEditForms,
  normalizeAccountPayload,
} from './mail-view-model';

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

function payload(
  overrides: Partial<MailAccountConnectionPayload> = {},
): MailAccountConnectionPayload {
  return {
    email_address: ' ada@example.com ',
    display_name: 'Ada',
    account_label: ' Ada work ',
    protocol: 'imap',
    incoming_host: ' imap.example.com ',
    incoming_port: 993,
    incoming_security: 'ssl',
    incoming_username: ' ada@example.com ',
    incoming_password: 'secret-password',
    smtp_host: ' smtp.example.com ',
    smtp_port: 587,
    smtp_security: 'starttls',
    smtp_username: '',
    smtp_password: '',
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
    is_read: false,
    is_starred: false,
    has_attachments: false,
    ...overrides,
  };
}

function messageDetail(
  overrides: Partial<MailMessageDetail> = {},
): MailMessageDetail {
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

describe('mail view model', () => {
  it('applies account form field changes and mirrors shared usernames', () => {
    expect(
      applyAccountFormChange(payload(), {
        field: 'incoming_username',
        value: 'grace@example.com',
      }),
    ).toMatchObject({
      incoming_username: 'grace@example.com',
      smtp_username: 'grace@example.com',
    });

    expect(
      applyAccountFormChange(
        payload({
          incoming_username: 'ada@example.com',
          smtp_username: 'ada@example.com',
        }),
        { field: 'incoming_username', value: 'grace@example.com' },
      ),
    ).toMatchObject({
      incoming_username: 'grace@example.com',
      smtp_username: 'grace@example.com',
    });

    expect(
      applyAccountFormChange(
        payload({
          incoming_username: 'ada@example.com',
          smtp_username: 'smtp-only@example.com',
        }),
        { field: 'incoming_username', value: 'grace@example.com' },
      ),
    ).toMatchObject({
      incoming_username: 'grace@example.com',
      smtp_username: 'smtp-only@example.com',
    });
  });

  it('applies account form field changes and mirrors shared passwords', () => {
    expect(
      applyAccountFormChange(payload(), {
        field: 'incoming_password',
        value: 'new-password',
      }),
    ).toMatchObject({
      incoming_password: 'new-password',
      smtp_password: 'new-password',
    });

    expect(
      applyAccountFormChange(
        payload({
          incoming_password: 'old-password',
          smtp_password: 'smtp-only-password',
        }),
        { field: 'incoming_password', value: 'new-password' },
      ),
    ).toMatchObject({
      incoming_password: 'new-password',
      smtp_password: 'smtp-only-password',
    });
  });

  it('applies account form field changes without shared credential copying', () => {
    const changed = applyAccountFormChange(
      payload({
        incoming_username: 'ada@example.com',
        incoming_password: 'old-password',
      }),
      { field: 'incoming_username', value: 'grace@example.com' },
      { copySharedCredentials: false },
    );

    expect(changed).toMatchObject({
      incoming_username: 'grace@example.com',
      smtp_username: '',
      incoming_password: 'old-password',
      smtp_password: '',
    });
  });

  it('applies direct account form field replacements including numeric ports', () => {
    expect(
      applyAccountFormChange(payload(), {
        field: 'smtp_port',
        value: 465,
      }),
    ).toMatchObject({
      incoming_port: 993,
      smtp_port: 465,
    });
  });

  it('normalizes new account payloads and copies shared credentials', () => {
    expect(normalizeAccountPayload(payload())).toMatchObject({
      email_address: 'ada@example.com',
      incoming_host: 'imap.example.com',
      incoming_username: 'ada@example.com',
      smtp_host: 'smtp.example.com',
      smtp_username: 'ada@example.com',
      smtp_password: 'secret-password',
    });
  });

  it('repairs likely partial browser autofill SMTP credentials only when enabled', () => {
    const form = payload({
      incoming_username: 'ada@example.com',
      smtp_username: 'ada@',
      incoming_password: 'secret-password',
      smtp_password: 'secret',
    });

    expect(normalizeAccountPayload(form)).toMatchObject({
      smtp_username: 'ada@example.com',
      smtp_password: 'secret-password',
    });
    expect(
      normalizeAccountPayload(form, { copySharedCredentials: false }),
    ).toMatchObject({
      smtp_username: 'ada@',
      smtp_password: 'secret',
    });
  });

  it('maps account records to editable forms with safe protocol and security defaults', () => {
    expect(
      accountToForm(
        account({
          protocol: 'unknown',
          incoming_security: 'weird',
          smtp_security: 'weird',
        }),
      ),
    ).toMatchObject({
      protocol: 'imap',
      incoming_security: 'ssl',
      incoming_password: '',
      smtp_security: 'starttls',
      smtp_password: '',
    });
  });

  it('preserves dirty edit forms while adding forms for new accounts', () => {
    const dirty = payload({ display_name: 'Dirty edit' });
    const next = nextAccountEditForms(
      [
        account(),
        account({ id: 'account-2', email_address: 'grace@example.com' }),
      ],
      { 'account-1': dirty },
    );

    expect(next['account-1']).toBe(dirty);
    expect(next['account-2']).toMatchObject({
      email_address: 'grace@example.com',
      incoming_password: '',
      smtp_password: '',
    });
  });

  it('keeps valid selections on load and falls back when selections disappear', () => {
    const firstMessage = message({ id: 'message-1' });
    const secondMessage = message({ id: 'message-2' });
    const firstDraft = draft({ id: 'draft-1' });
    const secondDraft = draft({ id: 'draft-2' });
    const loaded = mailViewReducer(
      {
        ...MAIL_VIEW_INITIAL_STATE,
        selectedMessageId: 'message-2',
        selectedDraftId: 'draft-2',
      },
      {
        type: 'loadSuccess',
        accounts: [account()],
        messages: [firstMessage, secondMessage],
        drafts: [firstDraft, secondDraft],
      },
    );
    const reloaded = mailViewReducer(loaded, {
      type: 'loadSuccess',
      accounts: [account()],
      messages: [firstMessage],
      drafts: [firstDraft],
    });

    expect(loaded.selectedMessageId).toBe('message-2');
    expect(loaded.selectedDraftId).toBe('draft-2');
    expect(reloaded.selectedMessageId).toBe('message-1');
    expect(reloaded.selectedDraftId).toBe('draft-1');
  });

  it('projects message read and flag updates into list and detail state', () => {
    const unreadDetail = messageDetail({ id: 'message-1', is_read: false });
    const optimistic = mailViewReducer(
      {
        ...MAIL_VIEW_INITIAL_STATE,
        messages: [message({ id: 'message-1', is_read: false })],
      },
      { type: 'messageReadOptimistic', message: unreadDetail },
    );
    const starred = message({
      id: 'message-1',
      is_read: true,
      is_starred: true,
    });
    const updated = mailViewReducer(optimistic, {
      type: 'messageFlagUpdate',
      message: starred,
    });

    expect(optimistic.detail?.is_read).toBe(true);
    expect(optimistic.messages[0].is_read).toBe(true);
    expect(updated.messages[0]).toEqual(starred);
    expect(updated.detail).toMatchObject({ id: 'message-1', is_starred: true });
  });

  it('replaces updated accounts and refreshes only that account edit form', () => {
    const dirty = payload({ display_name: 'Dirty edit' });
    const state = {
      ...MAIL_VIEW_INITIAL_STATE,
      accounts: [account(), account({ id: 'account-2' })],
      accountEditForms: {
        'account-1': dirty,
        'account-2': payload({ display_name: 'Other dirty edit' }),
      },
    };
    const updatedAccount = account({
      id: 'account-1',
      display_name: 'Updated Ada',
    });

    const updated = mailViewReducer(state, {
      type: 'accountUpdated',
      account: updatedAccount,
    });

    expect(updated.accounts[0]).toEqual(updatedAccount);
    expect(updated.accountEditForms['account-1']).toMatchObject({
      display_name: 'Updated Ada',
      incoming_password: '',
      smtp_password: '',
    });
    expect(updated.accountEditForms['account-2']).toBe(
      state.accountEditForms['account-2'],
    );
  });
});
