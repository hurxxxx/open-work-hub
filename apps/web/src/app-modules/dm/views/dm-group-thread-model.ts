import type { DmThread, DmUser } from '../api/dm-api';

type IdentifiedDmUser = Pick<DmUser, 'id'>;

export interface DmThreadTextDraftOverride {
  threadId: string;
  value: string;
}

export interface DmGroupCreateCommand {
  participantUserIds: string[];
  title: string;
}

export type DmConversationCreateCommand =
  | { kind: 'direct'; recipientUserId: string }
  | { kind: 'group'; participantUserIds: string[]; title: string };

export type DmGroupThreadParticipant = DmThread['participants'][number];

export function toggleDmGroupSelectedUser<T extends IdentifiedDmUser>(
  selectedUsers: readonly T[],
  nextUser: T,
): T[] {
  return selectedUsers.some((item) => item.id === nextUser.id)
    ? selectedUsers.filter((item) => item.id !== nextUser.id)
    : [...selectedUsers, nextUser];
}

export function selectedDmGroupUserIdSet(
  selectedUsers: readonly IdentifiedDmUser[],
): Set<string> {
  return new Set(selectedUsers.map((selectedUser) => selectedUser.id));
}

export function resolveDmGroupCreateCommand(input: {
  authenticated: boolean;
  creatingGroup: boolean;
  groupTitle: string;
  selectedUsers: readonly IdentifiedDmUser[];
}): DmGroupCreateCommand | null {
  if (
    !input.authenticated ||
    input.selectedUsers.length < 2 ||
    input.creatingGroup
  ) {
    return null;
  }
  return {
    participantUserIds: input.selectedUsers.map(
      (selectedUser) => selectedUser.id,
    ),
    title: input.groupTitle,
  };
}

export function resolveDmConversationCreateCommand(input: {
  authenticated: boolean;
  creating: boolean;
  groupTitle: string;
  selectedUsers: readonly IdentifiedDmUser[];
}): DmConversationCreateCommand | null {
  if (
    !input.authenticated ||
    input.creating ||
    input.selectedUsers.length === 0
  ) {
    return null;
  }
  if (input.selectedUsers.length === 1) {
    return {
      kind: 'direct',
      recipientUserId: input.selectedUsers[0].id,
    };
  }
  return {
    kind: 'group',
    participantUserIds: input.selectedUsers.map(
      (selectedUser) => selectedUser.id,
    ),
    title: input.groupTitle,
  };
}

export function isDmConversationCreateActionDisabled(input: {
  creating: boolean;
  selectedUsers: readonly IdentifiedDmUser[];
}): boolean {
  return input.selectedUsers.length === 0 || input.creating;
}

export function directDmGroupParticipantUserIds(input: {
  existingRecipientUserId: string | null | undefined;
  selectedUsers: readonly IdentifiedDmUser[];
}): string[] {
  const userIds = [
    input.existingRecipientUserId,
    ...input.selectedUsers.map((user) => user.id),
  ].filter((userId): userId is string => Boolean(userId));
  return [...new Set(userIds)];
}

export function isDirectDmGroupCreateActionDisabled(input: {
  creating: boolean;
  existingRecipientUserId: string | null | undefined;
  selectedUsers: readonly IdentifiedDmUser[];
}): boolean {
  return (
    input.creating ||
    directDmGroupParticipantUserIds(input).length < 2 ||
    input.selectedUsers.length === 0
  );
}

export function isDmGroupCreateActionDisabled(input: {
  creatingGroup: boolean;
  selectedUsers: readonly IdentifiedDmUser[];
}): boolean {
  return input.selectedUsers.length < 2 || input.creatingGroup;
}

export function createDmThreadTextDraftOverride(
  threadId: string,
  value: string,
): DmThreadTextDraftOverride {
  return { threadId, value };
}

export function resolveDmThreadTextDraft(input: {
  fallback: string | null | undefined;
  override: DmThreadTextDraftOverride | null;
  threadId: string | null | undefined;
}): string {
  if (input.override && input.override.threadId === input.threadId) {
    return input.override.value;
  }
  return input.fallback ?? '';
}

export function selectedDmThreadParticipantIdSet(
  thread: Pick<DmThread, 'participants'> | null | undefined,
): Set<string> {
  return new Set(
    (thread?.participants ?? []).map((participant) => participant.user.id),
  );
}

export function findCurrentDmThreadParticipant(
  thread: Pick<DmThread, 'participants'> | null | undefined,
  currentUserId: string | null | undefined,
): DmGroupThreadParticipant | null {
  if (!thread || !currentUserId) return null;
  return (
    thread.participants.find(
      (participant) => participant.user.id === currentUserId,
    ) ?? null
  );
}

export function canManageDmGroupMembers(
  participant: DmGroupThreadParticipant | null | undefined,
): boolean {
  return participant?.role === 'owner' || participant?.role === 'admin';
}

export function isDmGroupMemberPanelVisible(input: {
  memberPanelOpen: boolean;
  selectedThread: Pick<DmThread, 'conversation_type'> | null | undefined;
}): boolean {
  return (
    input.memberPanelOpen && input.selectedThread?.conversation_type === 'group'
  );
}

export function isDmGroupMemberRemovable(input: {
  canManageMembers: boolean;
  currentUserId: string | null | undefined;
  participant: DmGroupThreadParticipant;
}): boolean {
  return (
    input.canManageMembers && input.participant.user.id !== input.currentUserId
  );
}

export function dmGroupMemberActionTargetId(input: {
  currentUserId: string | null | undefined;
  threadId: string;
}): string {
  return input.currentUserId ?? input.threadId;
}
