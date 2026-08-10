import { describe, expect, it } from 'vitest';

import type { DmThread, DmUser } from '../api/dm-api';
import {
  canManageDmGroupMembers,
  createDmThreadTextDraftOverride,
  directDmGroupParticipantUserIds,
  dmGroupMemberActionTargetId,
  findCurrentDmThreadParticipant,
  isDirectDmGroupCreateActionDisabled,
  isDmConversationCreateActionDisabled,
  isDmGroupCreateActionDisabled,
  isDmGroupMemberPanelVisible,
  isDmGroupMemberRemovable,
  resolveDmConversationCreateCommand,
  resolveDmGroupCreateCommand,
  resolveDmThreadTextDraft,
  selectedDmGroupUserIdSet,
  selectedDmThreadParticipantIdSet,
  toggleDmGroupSelectedUser,
} from './dm-group-thread-model';

describe('dm group thread model', () => {
  it('toggles selected users and exposes their id set', () => {
    const ada = user({ id: 'u1', full_name: 'Ada Lovelace' });
    const grace = user({ id: 'u2', full_name: 'Grace Hopper' });
    const selected = toggleDmGroupSelectedUser([ada], grace);

    expect(selected).toEqual([ada, grace]);
    expect(toggleDmGroupSelectedUser(selected, ada)).toEqual([grace]);
    expect([...selectedDmGroupUserIdSet(selected)]).toEqual(['u1', 'u2']);
  });

  it('gates group creation without mutating title text', () => {
    const ada = user({ id: 'u1' });
    const grace = user({ id: 'u2' });

    expect(
      resolveDmGroupCreateCommand({
        authenticated: true,
        creatingGroup: false,
        groupTitle: '  Release room  ',
        selectedUsers: [ada, grace],
      }),
    ).toEqual({
      participantUserIds: ['u1', 'u2'],
      title: '  Release room  ',
    });
    expect(
      resolveDmGroupCreateCommand({
        authenticated: false,
        creatingGroup: false,
        groupTitle: 'Release room',
        selectedUsers: [ada, grace],
      }),
    ).toBeNull();
    expect(
      resolveDmGroupCreateCommand({
        authenticated: true,
        creatingGroup: false,
        groupTitle: 'Release room',
        selectedUsers: [ada],
      }),
    ).toBeNull();
    expect(
      resolveDmGroupCreateCommand({
        authenticated: true,
        creatingGroup: true,
        groupTitle: 'Release room',
        selectedUsers: [ada, grace],
      }),
    ).toBeNull();
    expect(
      isDmGroupCreateActionDisabled({
        creatingGroup: false,
        selectedUsers: [ada],
      }),
    ).toBe(true);
    expect(
      isDmGroupCreateActionDisabled({
        creatingGroup: true,
        selectedUsers: [ada, grace],
      }),
    ).toBe(true);
    expect(
      isDmGroupCreateActionDisabled({
        creatingGroup: false,
        selectedUsers: [ada, grace],
      }),
    ).toBe(false);
  });

  it('resolves unified conversation creation from selected recipients', () => {
    const ada = user({ id: 'u1' });
    const grace = user({ id: 'u2' });

    expect(
      resolveDmConversationCreateCommand({
        authenticated: true,
        creating: false,
        groupTitle: '',
        selectedUsers: [ada],
      }),
    ).toEqual({ kind: 'direct', recipientUserId: 'u1' });
    expect(
      resolveDmConversationCreateCommand({
        authenticated: true,
        creating: false,
        groupTitle: 'Release room',
        selectedUsers: [ada, grace],
      }),
    ).toEqual({
      kind: 'group',
      participantUserIds: ['u1', 'u2'],
      title: 'Release room',
    });
    expect(
      isDmConversationCreateActionDisabled({
        creating: false,
        selectedUsers: [],
      }),
    ).toBe(true);
    expect(
      isDmConversationCreateActionDisabled({
        creating: false,
        selectedUsers: [ada],
      }),
    ).toBe(false);
  });

  it('builds a new group recipient list from a direct conversation', () => {
    const grace = user({ id: 'u2' });
    const duplicate = user({ id: 'u2' });

    expect(
      directDmGroupParticipantUserIds({
        existingRecipientUserId: 'u1',
        selectedUsers: [grace, duplicate],
      }),
    ).toEqual(['u1', 'u2']);
    expect(
      isDirectDmGroupCreateActionDisabled({
        creating: false,
        existingRecipientUserId: 'u1',
        selectedUsers: [],
      }),
    ).toBe(true);
    expect(
      isDirectDmGroupCreateActionDisabled({
        creating: false,
        existingRecipientUserId: 'u1',
        selectedUsers: [grace],
      }),
    ).toBe(false);
  });

  it('resolves thread text drafts only for the matching selected thread', () => {
    const override = createDmThreadTextDraftOverride('c1', 'Draft title');

    expect(
      resolveDmThreadTextDraft({
        fallback: 'Saved title',
        override,
        threadId: 'c1',
      }),
    ).toBe('Draft title');
    expect(
      resolveDmThreadTextDraft({
        fallback: 'Saved title',
        override,
        threadId: 'c2',
      }),
    ).toBe('Saved title');
    expect(
      resolveDmThreadTextDraft({
        fallback: null,
        override: null,
        threadId: 'c1',
      }),
    ).toBe('');
  });

  it('derives member panel state from group thread participants', () => {
    const owner = participant(user({ id: 'u1' }), 'owner');
    const admin = participant(user({ id: 'u2' }), 'admin');
    const member = participant(user({ id: 'u3' }), 'member');
    const thread = conversation({
      conversation_type: 'group',
      participants: [owner, admin, member],
    });

    expect([...selectedDmThreadParticipantIdSet(thread)]).toEqual([
      'u1',
      'u2',
      'u3',
    ]);
    expect(findCurrentDmThreadParticipant(thread, 'u2')).toBe(admin);
    expect(findCurrentDmThreadParticipant(thread, null)).toBeNull();
    expect(canManageDmGroupMembers(owner)).toBe(true);
    expect(canManageDmGroupMembers(admin)).toBe(true);
    expect(canManageDmGroupMembers(member)).toBe(false);
    expect(
      isDmGroupMemberPanelVisible({
        memberPanelOpen: true,
        selectedThread: thread,
      }),
    ).toBe(true);
    expect(
      isDmGroupMemberPanelVisible({
        memberPanelOpen: true,
        selectedThread: conversation({ conversation_type: 'direct' }),
      }),
    ).toBe(false);
    expect(
      isDmGroupMemberRemovable({
        canManageMembers: true,
        currentUserId: 'u1',
        participant: owner,
      }),
    ).toBe(false);
    expect(
      isDmGroupMemberRemovable({
        canManageMembers: true,
        currentUserId: 'u1',
        participant: member,
      }),
    ).toBe(true);
    expect(
      dmGroupMemberActionTargetId({ currentUserId: 'u1', threadId: 'c1' }),
    ).toBe('u1');
    expect(
      dmGroupMemberActionTargetId({ currentUserId: null, threadId: 'c1' }),
    ).toBe('c1');
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
  role: DmThread['participants'][number]['role'] = 'member',
): DmThread['participants'][number] {
  return {
    role,
    user: participantUser,
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
