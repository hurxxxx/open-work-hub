import { useCallback, useMemo, useState } from 'react';

import {
  addSpaceMember,
  removeSpaceMember,
  updateSpaceMemberRole,
  type PmsSpaceMember,
  type PmsUserSummary,
} from '../api/pms-api';
import {
  DEFAULT_SPACE_MEMBER_ROLE,
  NO_MEMBER_SELECTION,
  buildTaskListMemberCandidateOptions,
} from './task-list-members-model';

export { DEFAULT_SPACE_MEMBER_ROLE, NO_MEMBER_SELECTION };

type MemberErrorMessages = {
  addFailed: string;
  removeFailed: string;
  updateRoleFailed: string;
};

type UseTaskListMembersControllerParams = {
  availableUsers: PmsUserSummary[];
  candidatePlaceholder: string;
  errorMessages: MemberErrorMessages;
  onError: (message: string | null) => void;
  onMembersChanged?: (members: PmsSpaceMember[]) => void;
  teamId: string | null;
  token: string | null | undefined;
};

export function useTaskListMembersController({
  availableUsers,
  candidatePlaceholder,
  errorMessages,
  onError,
  onMembersChanged,
  teamId,
  token,
}: UseTaskListMembersControllerParams) {
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [selectedUserId, setSelectedUserId] = useState(NO_MEMBER_SELECTION);
  const [selectedRole, setSelectedRole] = useState(DEFAULT_SPACE_MEMBER_ROLE);
  const [addingMember, setAddingMember] = useState(false);

  const replaceMembers = useCallback(
    (updated: PmsSpaceMember[]) => {
      setMembers(updated);
      onMembersChanged?.(updated);
    },
    [onMembersChanged],
  );

  const memberCandidateOptions = useMemo(() => {
    return buildTaskListMemberCandidateOptions({
      availableUsers,
      candidatePlaceholder,
      members,
    });
  }, [availableUsers, candidatePlaceholder, members]);

  const handleAddMember = useCallback(async () => {
    if (!token || !teamId || selectedUserId === NO_MEMBER_SELECTION) return;
    setAddingMember(true);
    onError(null);
    try {
      const added = await addSpaceMember(token, teamId, {
        user_id: selectedUserId,
        role: selectedRole,
      });
      replaceMembers([...members, added]);
      setSelectedUserId(NO_MEMBER_SELECTION);
      setSelectedRole(DEFAULT_SPACE_MEMBER_ROLE);
    } catch (caughtError) {
      onError(
        caughtError instanceof Error
          ? caughtError.message
          : errorMessages.addFailed,
      );
    } finally {
      setAddingMember(false);
    }
  }, [
    errorMessages.addFailed,
    members,
    onError,
    replaceMembers,
    selectedRole,
    selectedUserId,
    teamId,
    token,
  ]);

  const handleRoleChange = useCallback(
    async (userId: string, role: string) => {
      if (!token || !teamId) return;
      onError(null);
      try {
        const updatedMember = await updateSpaceMemberRole(
          token,
          teamId,
          userId,
          role,
        );
        replaceMembers(
          members.map((member) =>
            member.user_id === userId ? updatedMember : member,
          ),
        );
      } catch (caughtError) {
        onError(
          caughtError instanceof Error
            ? caughtError.message
            : errorMessages.updateRoleFailed,
        );
      }
    },
    [
      errorMessages.updateRoleFailed,
      members,
      onError,
      replaceMembers,
      teamId,
      token,
    ],
  );

  const handleRemoveMember = useCallback(
    async (userId: string) => {
      if (!token || !teamId) return;
      onError(null);
      try {
        await removeSpaceMember(token, teamId, userId);
        replaceMembers(members.filter((member) => member.user_id !== userId));
      } catch (caughtError) {
        onError(
          caughtError instanceof Error
            ? caughtError.message
            : errorMessages.removeFailed,
        );
      }
    },
    [
      errorMessages.removeFailed,
      members,
      onError,
      replaceMembers,
      teamId,
      token,
    ],
  );

  return {
    addingMember,
    handleAddMember,
    handleRemoveMember,
    handleRoleChange,
    memberCandidateOptions,
    members,
    replaceMembers,
    selectedRole,
    selectedUserId,
    setSelectedRole,
    setSelectedUserId,
  };
}
