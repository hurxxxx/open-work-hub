import { Button } from '@open-alm/ui';
import { Loader2, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { UserOptionRow } from '@/src/platform/users/UserSearchMultiSelect';
import { userOptionNameWithDepartment } from '@/src/platform/users/user-option-picker-model';
import type {
  PmsActivityLog,
  PmsComment,
  PmsTaskListMember,
} from '../api/pms-api';
import { formatDate, initials } from './pms-constants';

type TaskDetailActivityPanelProps = {
  activityLogs: PmsActivityLog[];
  canEdit: boolean;
  commentDraft: string;
  comments: PmsComment[];
  isVisible: boolean;
  loading: boolean;
  mentionCandidates: PmsTaskListMember[];
  mentionOpen: boolean;
  members: PmsTaskListMember[];
  onCloseMention: () => void;
  onCommentDraftChange: (value: string) => void;
  onCommentSubmit: () => void;
  onMentionPick: (member: PmsTaskListMember) => void;
  resolveFileUrl?: (url: string) => Promise<string>;
};

type CommentBodySegment =
  | { text: string; type: 'text' }
  | {
      displayName: string;
      key: string;
      type: 'mention';
      userId: string | null;
    };

function mentionDisplayName(
  userId: string | null,
  displayName: string | null | undefined,
  membersById: Map<string, PmsTaskListMember>,
): string {
  if (displayName) return displayName;
  const member = userId ? membersById.get(userId) : undefined;
  if (!member) return 'Unknown';
  return userOptionNameWithDepartment({
    id: member.user_id,
    email: member.email,
    full_name: member.full_name,
    primary_org_unit_name: member.primary_org_unit_name,
  });
}

function pushCommentTextSegment(
  segments: CommentBodySegment[],
  text: unknown,
): void {
  if (typeof text !== 'string' || !text) return;
  segments.push({ type: 'text', text });
}

function commentBodyBlockSegments(
  bodyBlocks: PmsComment['body_blocks'],
  membersById: Map<string, PmsTaskListMember>,
): CommentBodySegment[] {
  if (!Array.isArray(bodyBlocks)) return [];
  const segments: CommentBodySegment[] = [];
  bodyBlocks.forEach((block, blockIndex) => {
    const content = Array.isArray(block.content) ? block.content : [];
    for (const contentItem of content) {
      if (!contentItem || typeof contentItem !== 'object') continue;
      const item = contentItem as Record<string, unknown>;
      if (item.type === 'mention') {
        const props = (
          item.props && typeof item.props === 'object' ? item.props : {}
        ) as Record<string, unknown>;
        const attrs = (
          item.attrs && typeof item.attrs === 'object' ? item.attrs : {}
        ) as Record<string, unknown>;
        const userIdValue =
          props.userId ??
          props.user_id ??
          attrs.userId ??
          attrs.user_id ??
          attrs.id;
        const displayNameValue = props.displayName ?? props.display_name;
        const userId = typeof userIdValue === 'string' ? userIdValue : null;
        segments.push({
          type: 'mention',
          key: `${blockIndex}-${segments.length}-${userId ?? 'unknown'}`,
          userId,
          displayName: mentionDisplayName(
            userId,
            typeof displayNameValue === 'string' ? displayNameValue : null,
            membersById,
          ),
        });
        continue;
      }
      pushCommentTextSegment(segments, item.text);
    }
    if (blockIndex < bodyBlocks.length - 1) {
      pushCommentTextSegment(segments, '\n');
    }
  });
  return segments;
}

export function getTaskCommentBodySegments(
  body: string,
  bodyBlocks: PmsComment['body_blocks'],
  members: PmsTaskListMember[],
): CommentBodySegment[] {
  const memberById = new Map(members.map((member) => [member.user_id, member]));
  const blockSegments = commentBodyBlockSegments(bodyBlocks, memberById);
  if (blockSegments.length > 0) {
    return blockSegments;
  }
  const parts = body.split(/(@[0-9a-f-]{36})/gi);
  return parts.flatMap((part, index): CommentBodySegment[] => {
    if (!part) return [];
    const userId = part.startsWith('@') ? part.slice(1) : null;
    if (!userId || !memberById.has(userId))
      return [{ type: 'text', text: part }];
    return [
      {
        type: 'mention',
        key: `${index}-${userId}`,
        userId,
        displayName: mentionDisplayName(userId, null, memberById),
      },
    ];
  });
}

function renderCommentBody(segments: CommentBodySegment[]) {
  return segments.map((segment, index) => {
    if (segment.type === 'text') {
      return segment.text;
    }
    return (
      <span
        key={`${segment.key}-${index}`}
        className="inline-flex items-center rounded bg-app-info/20 px-1.5 py-0.5 text-xs font-medium text-app-info-text"
        data-user-id={segment.userId ?? undefined}
      >
        @{segment.displayName}
      </span>
    );
  });
}

export function TaskDetailActivityPanel({
  activityLogs,
  canEdit,
  commentDraft,
  comments,
  isVisible,
  loading,
  mentionCandidates,
  mentionOpen,
  members,
  onCloseMention,
  onCommentDraftChange,
  onCommentSubmit,
  onMentionPick,
  resolveFileUrl,
}: TaskDetailActivityPanelProps) {
  const { t } = useTranslation('apps');
  void resolveFileUrl;

  return (
    <div
      id="task-detail-activity-panel"
      data-testid="task-detail-activity-panel"
      className={`${isVisible ? 'flex' : 'hidden'} min-h-0 w-full flex-1 flex-col bg-app-bg lg:flex lg:w-[340px] lg:flex-none lg:shrink-0`}
      role="tabpanel"
    >
      <div className="px-4 py-3 border-b border-app-border">
        <h3 className="app-text-title-md text-app-ink">
          {t('pms.taskDetail.activity')}
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar px-4 py-3 space-y-3">
        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={18} className="animate-spin text-app-ink/40" />
          </div>
        ) : (
          <>
            {activityLogs.map((log) => (
              <div key={log.id} className="flex gap-2">
                <div className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-app-border bg-app-surface-sidebar text-[8px] font-bold text-app-ink/60">
                  {initials(log.actor_name)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="app-text-caption text-app-ink/60">
                    {log.message}
                  </p>
                  <span className="app-text-micro text-app-ink/30">
                    {formatDate(log.created_at)}
                  </span>
                </div>
              </div>
            ))}

            {comments.map((comment) => (
              <div key={comment.id} className="flex gap-2">
                <div className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-app-accent text-[8px] font-bold text-app-accent-fg">
                  {initials(comment.author_name)}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="app-text-caption font-bold text-app-ink">
                    {comment.author_name}
                  </span>
                  <p className="app-text-caption mt-0.5 whitespace-pre-wrap break-words text-app-ink/60">
                    {renderCommentBody(
                      getTaskCommentBodySegments(
                        comment.body,
                        comment.body_blocks,
                        members,
                      ),
                    )}
                  </p>
                  <span className="app-text-micro text-app-ink/30">
                    {formatDate(comment.created_at)}
                  </span>
                </div>
              </div>
            ))}

            {activityLogs.length === 0 && comments.length === 0 && (
              <p className="app-text-body py-8 text-center text-app-ink/30">
                {t('pms.taskDetail.noActivity')}
              </p>
            )}
          </>
        )}
      </div>

      <div className="relative flex items-center gap-2 border-t border-app-border px-4 py-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shrink-0 lg:pb-3">
        <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-app-accent text-[8px] font-bold text-app-accent-fg">
          {t('pms.taskDetail.me')}
        </div>
        <div className="flex-1 relative">
          <input
            aria-label={t('pms.taskDetail.commentPlaceholder')}
            type="text"
            value={commentDraft}
            onChange={(e) => onCommentDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.nativeEvent.isComposing &&
                !mentionOpen
              ) {
                e.preventDefault();
                onCommentSubmit();
              }
              if (e.key === 'Escape') onCloseMention();
            }}
            placeholder={
              canEdit
                ? t('pms.taskDetail.commentPlaceholder')
                : t('pms.taskDetail.commentsReadOnly')
            }
            className="app-text-body w-full rounded-lg border border-app-border bg-transparent px-3 py-1.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
            disabled={!canEdit}
          />
          {mentionOpen && canEdit && (
            <>
              <button
                aria-label={t('common:actions.close')}
                type="button"
                className="fixed inset-0 z-10"
                onClick={onCloseMention}
              />
              <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-app-bg border border-app-border rounded-lg shadow-xl py-1 max-h-40 overflow-y-auto">
                {mentionCandidates.map((m) => (
                  <UserOptionRow
                    currentUserLabel={t('pms.taskDetail.me')}
                    density="compact"
                    key={m.user_id}
                    onClick={() => onMentionPick(m)}
                    user={{ ...m, id: m.user_id }}
                  />
                ))}
                {mentionCandidates.length === 0 && (
                  <p className="app-text-caption px-3 py-2 text-app-ink/40">
                    {t('pms.taskDetail.noMatches')}
                  </p>
                )}
              </div>
            </>
          )}
        </div>
        {canEdit ? (
          <Button
            variant="ghost"
            size="icon"
            className="shrink-0"
            onClick={onCommentSubmit}
          >
            <Send size={14} />
          </Button>
        ) : null}
      </div>
    </div>
  );
}
