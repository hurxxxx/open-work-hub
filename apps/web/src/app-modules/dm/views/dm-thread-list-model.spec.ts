import { describe, expect, it } from 'vitest';

import type { DmMessage, DmThread, DmUser } from '../api/dm-api';
import {
  buildDmThreadListItem,
  displayDmUserName,
  dmInitials,
  dmMessagePreviewText,
  dmThreadDisplayName,
  dmThreadPreviewText,
  dmUnreadBadge,
} from './dm-thread-list-model';

function t(key: string, values?: Record<string, unknown>): string {
  if (!values) return key;
  return `${key}:${Object.entries(values)
    .map(([name, value]) => `${name}=${String(value)}`)
    .join(',')}`;
}

describe('dm thread list model', () => {
  it('derives user display labels and initials', () => {
    expect(displayDmUserName(user({ display_name: 'Ada' }))).toBe('Ada');
    expect(displayDmUserName(user({ display_name: '' }))).toBe('Ada Lovelace');
    expect(dmInitials('Ada Lovelace')).toBe('AL');
    expect(dmInitials('')).toBe('DM');
  });

  it('builds direct and group conversation display names', () => {
    expect(
      dmThreadDisplayName(
        conversation({
          conversation_type: 'direct',
          other_user: user({ display_name: 'Grace' }),
        }),
        'u1',
      ),
    ).toBe('Grace');
    expect(dmThreadDisplayName(conversation({ title: 'Release room' }), 'u1')).toBe(
      'Release room',
    );
    expect(
      dmThreadDisplayName(
        conversation({
          display_name: null,
          participants: [
            participant(user({ id: 'u1', full_name: 'Me' })),
            participant(user({ id: 'u2', full_name: 'Ada Lovelace' })),
            participant(user({ id: 'u3', full_name: 'Grace Hopper' })),
            participant(user({ id: 'u4', full_name: 'Katherine Johnson' })),
            participant(user({ id: 'u5', full_name: 'Hidden User' })),
          ],
          title: null,
        }),
        'u1',
      ),
    ).toBe('Ada Lovelace, Grace Hopper, Katherine Johnson');
  });

  it('creates localized message and thread previews', () => {
    expect(dmMessagePreviewText(message({ body: ' hello ' }), t)).toBe(' hello ');
    expect(
      dmMessagePreviewText(
        message({
          attachments: [attachment({ filename: 'plan.pdf' })],
          body: '',
        }),
        t,
      ),
    ).toBe('dm.attachmentPreviewFile:filename=plan.pdf');
    expect(
      dmMessagePreviewText(
        message({
          attachments: [
            attachment({ id: 'a1' }),
            attachment({ id: 'a2' }),
          ],
          body: '',
        }),
        t,
      ),
    ).toBe('dm.attachmentPreviewCount:count=2');
    expect(dmThreadPreviewText(conversation({ last_message: null }), t)).toBe(
      'dm.emptyThread',
    );
    expect(
      dmThreadPreviewText(
        conversation({
          last_message: message({ body: 'Update', sender_name: 'Ada' }),
        }),
        t,
      ),
    ).toBe('Ada: Update');
  });

  it('caps unread badges and builds stable thread list items', () => {
    const thread = conversation({
      id: 'c2',
      last_message: message({ body: 'Ping' }),
      title: 'Ops',
      unread_count: 12,
    });

    expect(dmUnreadBadge(0)).toBeNull();
    expect(dmUnreadBadge(3)).toBe('3');
    expect(dmUnreadBadge(12)).toBe('9+');
    expect(
      buildDmThreadListItem({
        activeThreadId: 'c2',
        currentUserId: 'u1',
        thread,
        translate: t,
      }),
    ).toEqual({
      active: true,
      id: 'c2',
      initials: 'O',
      name: 'Ops',
      preview: 'User One: Ping',
      unreadBadge: '9+',
    });
  });
});

function user(overrides: Partial<DmUser> = {}): DmUser {
  return {
    id: 'u1',
    email: 'user@example.test',
    full_name: 'Ada Lovelace',
    display_name: '',
    avatar_url: null,
    ...overrides,
  };
}

function participant(
  participantUser: DmUser,
): DmThread['participants'][number] {
  return {
    role: 'member',
    user: participantUser,
  };
}

function attachment(
  overrides: Partial<DmMessage['attachments'][number]> = {},
): DmMessage['attachments'][number] {
  return {
    id: 'a1',
    filename: 'file.txt',
    content_type: 'text/plain',
    size_bytes: 100,
    is_image: false,
    preview_url: null,
    download_url: null,
    created_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

function message(overrides: Partial<DmMessage> = {}): DmMessage {
  return {
    id: 'm1',
    conversation_id: 'c1',
    thread_id: 'c1',
    sequence: 1,
    sender_id: 'u1',
    sender_name: 'User One',
    body: '',
    attachments: [],
    created_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

function conversation(overrides: Partial<DmThread> = {}): DmThread {
  return {
    id: 'c1',
    conversation_type: 'group',
    thread_type: 'group',
    title: null,
    display_name: 'Team chat',
    other_user: null,
    participants: [],
    participant_count: 2,
    last_message: null,
    unread_count: 0,
    last_read_message_id: null,
    muted_at: null,
    created_by_id: 'u1',
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}
