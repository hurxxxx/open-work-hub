import { selectUserOptionsForPicker } from '@/src/platform/users/user-option-picker-model';

import type { PmsSpaceMember, PmsUserSummary } from '../api/pms-api';

export type RoleValue = 'owner' | 'admin' | 'member' | 'viewer';

export type RoleOptionConfig = {
  value: RoleValue;
  labelKey: string;
  descriptionKey: string;
};

export const SPACE_MEMBER_ROLE_OPTIONS: RoleOptionConfig[] = [
  {
    value: 'admin',
    labelKey: 'pms.settings.role.admin',
    descriptionKey: 'pms.spaceMembers.roleDescription.admin',
  },
  {
    value: 'member',
    labelKey: 'pms.settings.role.member',
    descriptionKey: 'pms.spaceMembers.roleDescription.member',
  },
  {
    value: 'viewer',
    labelKey: 'pms.settings.role.viewer',
    descriptionKey: 'pms.spaceMembers.roleDescription.viewer',
  },
];

export const OWNER_ROLE_OPTION: RoleOptionConfig = {
  value: 'owner',
  labelKey: 'pms.settings.role.owner',
  descriptionKey: 'pms.spaceMembers.roleDescription.owner',
};

export const SPACE_MEMBER_ROLE_LABEL_KEYS: Record<string, string> = {
  owner: 'pms.settings.role.owner',
  admin: 'pms.settings.role.admin',
  member: 'pms.settings.role.member',
  viewer: 'pms.settings.role.viewer',
};

export const SPACE_MEMBER_ROW_MENU_WIDTH = 200;
export const SPACE_MEMBER_ROW_MENU_ESTIMATED_HEIGHT = 360;
const SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER = 8;
const SPACE_MEMBER_ROW_MENU_ANCHOR_GAP = 4;

type SpaceMemberRowMenuAnchorRect = {
  bottom: number;
  right: number;
  top: number;
};

export type SpaceMemberRowMenuPosition = {
  left: number;
  top: number;
};

export function spaceMemberRowMenuPosition({
  anchorRect,
  menuHeight = SPACE_MEMBER_ROW_MENU_ESTIMATED_HEIGHT,
  menuWidth = SPACE_MEMBER_ROW_MENU_WIDTH,
  viewportHeight,
  viewportWidth,
}: {
  anchorRect: SpaceMemberRowMenuAnchorRect;
  menuHeight?: number;
  menuWidth?: number;
  viewportHeight: number;
  viewportWidth: number;
}): SpaceMemberRowMenuPosition {
  const minLeft = SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER;
  const maxLeft = Math.max(
    minLeft,
    viewportWidth - menuWidth - SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER,
  );
  const left = Math.min(
    Math.max(anchorRect.right - menuWidth, minLeft),
    maxLeft,
  );
  const belowTop = anchorRect.bottom + SPACE_MEMBER_ROW_MENU_ANCHOR_GAP;
  const aboveTop =
    anchorRect.top - menuHeight - SPACE_MEMBER_ROW_MENU_ANCHOR_GAP;
  const viewportBottom = viewportHeight - SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER;

  if (belowTop + menuHeight <= viewportBottom) {
    return { left, top: belowTop };
  }

  if (aboveTop >= SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER) {
    return { left, top: aboveTop };
  }

  const maxTop = Math.max(
    SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER,
    viewportHeight - menuHeight - SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER,
  );
  const top = Math.min(
    Math.max(belowTop, SPACE_MEMBER_ROW_MENU_VIEWPORT_GUTTER),
    maxTop,
  );

  return { left, top };
}

export interface SpaceMembersModalState {
  members: PmsSpaceMember[];
  allUsers: PmsUserSummary[];
  loading: boolean;
  error: string | null;
  busyUserId: string | null;
  inviteQuery: string;
  inviteFocused: boolean;
  memberSearch: string;
  openRowMenu: string | null;
}

export type SpaceMembersModalAction =
  | { type: 'loadStart' }
  | { type: 'loadSuccess'; members: PmsSpaceMember[]; users: PmsUserSummary[] }
  | { type: 'loadFailure'; error: string }
  | { type: 'setError'; error: string | null }
  | { type: 'setBusyUserId'; busyUserId: string | null }
  | { type: 'setInviteQuery'; inviteQuery: string }
  | { type: 'setInviteFocused'; inviteFocused: boolean }
  | { type: 'setMemberSearch'; memberSearch: string }
  | { type: 'setOpenRowMenu'; openRowMenu: string | null }
  | { type: 'toggleRowMenu'; userId: string };

export const SPACE_MEMBERS_INITIAL_STATE: SpaceMembersModalState = {
  members: [],
  allUsers: [],
  loading: false,
  error: null,
  busyUserId: null,
  inviteQuery: '',
  inviteFocused: false,
  memberSearch: '',
  openRowMenu: null,
};

export function spaceMembersModalReducer(
  state: SpaceMembersModalState,
  action: SpaceMembersModalAction,
): SpaceMembersModalState {
  switch (action.type) {
    case 'loadStart':
      return { ...state, loading: true, error: null };
    case 'loadSuccess':
      return {
        ...state,
        members: action.members,
        allUsers: action.users,
        loading: false,
      };
    case 'loadFailure':
      return { ...state, loading: false, error: action.error };
    case 'setError':
      return { ...state, error: action.error };
    case 'setBusyUserId':
      return { ...state, busyUserId: action.busyUserId };
    case 'setInviteQuery':
      return { ...state, inviteQuery: action.inviteQuery };
    case 'setInviteFocused':
      return { ...state, inviteFocused: action.inviteFocused };
    case 'setMemberSearch':
      return { ...state, memberSearch: action.memberSearch };
    case 'setOpenRowMenu':
      return { ...state, openRowMenu: action.openRowMenu };
    case 'toggleRowMenu':
      return {
        ...state,
        openRowMenu: state.openRowMenu === action.userId ? null : action.userId,
      };
  }
}

export function roleOptionConfigForUser(
  canManageAdmins: boolean,
): RoleOptionConfig[] {
  return canManageAdmins
    ? [OWNER_ROLE_OPTION, ...SPACE_MEMBER_ROLE_OPTIONS]
    : SPACE_MEMBER_ROLE_OPTIONS;
}

export function spaceMemberIds(
  members: readonly PmsSpaceMember[],
): Set<string> {
  return new Set(members.map((member) => member.user_id));
}

export function inviteCandidates({
  allUsers,
  currentUserId,
  memberIds,
  query,
  limit = 6,
}: {
  allUsers: readonly PmsUserSummary[];
  currentUserId?: string | null;
  memberIds: ReadonlySet<string>;
  query: string;
  limit?: number;
}): PmsUserSummary[] {
  return selectUserOptionsForPicker({
    users: allUsers,
    query,
    currentUserId,
    excludeIds: memberIds,
    limit,
  });
}

export function visibleSpaceMembers({
  locale,
  members,
  query,
}: {
  locale: string;
  members: readonly PmsSpaceMember[];
  query: string;
}): PmsSpaceMember[] {
  const trimmed = query.trim().toLowerCase();
  const sorted = Array.from(members).sort(compareSpaceMembers(locale));
  if (!trimmed) return sorted;
  return sorted.filter(
    (member) =>
      member.full_name.toLowerCase().includes(trimmed) ||
      member.email.toLowerCase().includes(trimmed),
  );
}

export function compareSpaceMembers(
  locale: string,
): (left: PmsSpaceMember, right: PmsSpaceMember) => number {
  const rank: Record<string, number> = {
    owner: 0,
    admin: 1,
    member: 2,
    viewer: 3,
  };
  return (left, right) => {
    const leftRank = rank[left.role] ?? 4;
    const rightRank = rank[right.role] ?? 4;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.full_name.localeCompare(right.full_name, locale);
  };
}

export function canMutateSpaceMember({
  canManage,
  canManageAdmins,
  currentUserId,
  member,
}: {
  canManage: boolean;
  canManageAdmins: boolean;
  currentUserId: string | undefined;
  member: PmsSpaceMember;
}): boolean {
  if (!canManage || member.user_id === currentUserId) {
    return false;
  }
  return (
    canManageAdmins || (member.role !== 'owner' && member.role !== 'admin')
  );
}
