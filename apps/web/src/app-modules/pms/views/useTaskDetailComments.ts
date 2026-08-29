import { useCallback, useMemo, useState, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';

import {
  createTaskComment,
  type PmsComment,
  type PmsTaskListMember,
} from '../api/pms-api';
import {
  userOptionMatchesQuery,
  userOptionDisplayName,
} from '@/src/platform/users/user-option-picker-model';
import {
  getTaskDetailMutationErrorMessage,
  notifyTaskDetailUpdated,
} from './task-detail-mutation';

export type TaskCommentMentionToken = {
  displayName: string;
  userId: string;
};

export function getTaskDetailMentionState(value: string): {
  mentionOpen: boolean;
  mentionQuery: string;
} {
  const atIndex = value.lastIndexOf('@');
  if (atIndex < 0) return { mentionOpen: false, mentionQuery: '' };
  const query = value.slice(atIndex + 1);
  if (query.length === 0) return { mentionOpen: true, mentionQuery: '' };
  if (query.includes(' ')) return { mentionOpen: false, mentionQuery: '' };
  return { mentionOpen: true, mentionQuery: query.toLowerCase() };
}

export function getTaskDetailMentionCandidates<
  TMember extends Pick<PmsTaskListMember, 'email' | 'full_name'> & {
    user_id?: string;
  },
>(members: TMember[], mentionQuery: string): TMember[] {
  if (!mentionQuery) return members;
  return members.filter((member) =>
    userOptionMatchesQuery(
      {
        id: member.user_id ?? member.email,
        email: member.email,
        full_name: member.full_name,
      },
      mentionQuery,
    ),
  );
}

export function applyTaskDetailMentionPick(
  commentDraft: string,
  displayName: string,
): string {
  const atIndex = commentDraft.lastIndexOf('@');
  if (atIndex < 0) return `${commentDraft}@${displayName} `;
  return `${commentDraft.slice(0, atIndex)}@${displayName} `;
}

function pushTextContent(
  content: Record<string, unknown>[],
  text: string,
): void {
  if (!text) return;
  content.push({ type: 'text', text, styles: {} });
}

export function buildTaskCommentBodyBlocks(
  body: string,
  mentionTokens: readonly TaskCommentMentionToken[],
): Record<string, unknown>[] | null {
  if (!mentionTokens.length) return null;
  const content: Record<string, unknown>[] = [];
  let cursor = 0;

  for (const token of mentionTokens) {
    const marker = `@${token.displayName}`;
    const index = body.indexOf(marker, cursor);
    if (index < 0) continue;
    pushTextContent(content, body.slice(cursor, index));
    content.push({
      type: 'mention',
      props: {
        userId: token.userId,
        displayName: token.displayName,
      },
    });
    cursor = index + marker.length;
  }

  if (!content.some((item) => item.type === 'mention')) {
    return null;
  }
  pushTextContent(content, body.slice(cursor));
  return [
    {
      type: 'paragraph',
      content,
    },
  ];
}

export function useTaskDetailComments({
  canEdit,
  members,
  onUpdate,
  setComments,
  setSaveError,
  taskId,
  token,
  t,
  workspaceSlug,
}: {
  canEdit: boolean;
  members: PmsTaskListMember[];
  onUpdate?: () => void | Promise<void>;
  setComments: (value: SetStateAction<PmsComment[]>) => void;
  setSaveError: (message: string | null) => void;
  taskId: string;
  token: string | null;
  t: TFunction;
  workspaceSlug: string;
}) {
  const [commentDraft, setCommentDraft] = useState('');
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionTokens, setMentionTokens] = useState<TaskCommentMentionToken[]>(
    [],
  );
  const mentionCandidates = useMemo(
    () => getTaskDetailMentionCandidates(members, mentionQuery),
    [members, mentionQuery],
  );

  const handleCommentDraftChange = useCallback(
    (value: string) => {
      if (!canEdit) return;
      setCommentDraft(value);
      const nextMentionState = getTaskDetailMentionState(value);
      setMentionOpen(nextMentionState.mentionOpen);
      setMentionQuery(nextMentionState.mentionQuery);
    },
    [canEdit],
  );

  const closeMention = useCallback(() => {
    setMentionOpen(false);
  }, []);

  const handleMentionPick = useCallback((member: PmsTaskListMember) => {
    const displayName = userOptionDisplayName({
      id: member.user_id,
      email: member.email,
      full_name: member.full_name,
    });
    setCommentDraft((current) =>
      applyTaskDetailMentionPick(current, displayName),
    );
    setMentionTokens((current) => [
      ...current.filter((token) => token.userId !== member.user_id),
      { userId: member.user_id, displayName },
    ]);
    setMentionOpen(false);
  }, []);

  const handleCommentSubmit = useCallback(() => {
    if (!token || !canEdit || !workspaceSlug || !commentDraft.trim()) return;
    setSaveError(null);
    const body = commentDraft.trim();
    const bodyBlocks = buildTaskCommentBodyBlocks(body, mentionTokens);
    createTaskComment(token, taskId, body, bodyBlocks, workspaceSlug)
      .then(async (newComment) => {
        setComments((prev) => [...prev, newComment]);
        setCommentDraft('');
        setMentionTokens([]);
        setMentionOpen(false);
        setMentionQuery('');
        await notifyTaskDetailUpdated(onUpdate);
      })
      .catch((error) => {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.createCommentFailed'),
          ),
        );
      });
  }, [
    canEdit,
    commentDraft,
    mentionTokens,
    onUpdate,
    setComments,
    setSaveError,
    t,
    taskId,
    token,
    workspaceSlug,
  ]);

  return {
    closeMention,
    commentDraft,
    handleCommentDraftChange,
    handleCommentSubmit,
    handleMentionPick,
    mentionCandidates,
    mentionOpen,
  };
}
