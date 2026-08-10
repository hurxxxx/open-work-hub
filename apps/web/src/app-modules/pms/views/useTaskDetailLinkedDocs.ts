import {
  useCallback,
  useState,
  type RefObject,
  type SetStateAction,
} from 'react';
import type { TFunction } from 'i18next';
import type { BlockContent } from '@open-work-hub/ui';

import {
  createNativeDoc,
  listDocPages,
  updateDocPage,
} from '@/src/app-modules/docs/public-api';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
} from '@/src/platform/workspaces/workspace-utils';
import {
  attachTaskDoc,
  detachTaskDoc,
  type PmsTask,
  type PmsTaskDocLink,
} from '../api/pms-api';
import {
  getTaskDetailMutationErrorMessage,
  notifyTaskDetailUpdated,
} from './task-detail-mutation';

type WorkspaceUser = Parameters<typeof resolveDefaultWorkspaceAppPath>[0];

export function resolveTaskDetailPromotedDocContent({
  descriptionBlocks,
  issueDescriptionBlocks,
}: {
  descriptionBlocks: BlockContent | null;
  issueDescriptionBlocks: PmsTask['description_blocks'];
}): Record<string, unknown>[] {
  return (
    (descriptionBlocks as Record<string, unknown>[] | null) ??
    issueDescriptionBlocks ??
    []
  );
}

export function resolveTaskDetailDocPath({
  docId,
  user,
  workspaceSlug,
}: {
  docId: string;
  user: WorkspaceUser;
  workspaceSlug: string | null;
}): string {
  const suffix = `/${docId}`;
  return workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'docs', suffix)
    : resolveDefaultWorkspaceAppPath(user, 'docs', suffix);
}

export function useTaskDetailLinkedDocs({
  canEdit,
  descriptionBlocksRef,
  issue,
  onUpdate,
  setLinkedDocs,
  setSaveError,
  spaceId,
  token,
  t,
  user,
  workspaceSlug,
}: {
  canEdit: boolean;
  descriptionBlocksRef: RefObject<BlockContent | null>;
  issue: Pick<PmsTask, 'description_blocks' | 'id' | 'title'>;
  onUpdate?: () => void | Promise<void>;
  setLinkedDocs: (value: SetStateAction<PmsTaskDocLink[]>) => void;
  setSaveError: (message: string | null) => void;
  spaceId: string | null;
  token: string | null;
  t: TFunction;
  user: WorkspaceUser;
  workspaceSlug: string | null;
}) {
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [promotingDescription, setPromotingDescription] = useState(false);

  const buildDocPath = useCallback(
    (docId: string) => resolveTaskDetailDocPath({ docId, user, workspaceSlug }),
    [user, workspaceSlug],
  );

  const handlePromoteDescriptionToDoc = useCallback(async () => {
    if (!token || !canEdit || promotingDescription) return;
    setPromotingDescription(true);
    setSaveError(null);

    try {
      const contentBlocks = resolveTaskDetailPromotedDocContent({
        descriptionBlocks: descriptionBlocksRef.current,
        issueDescriptionBlocks: issue.description_blocks,
      });
      const doc = await createNativeDoc(
        token,
        {
          title: issue.title,
          first_page_title: t('pms.taskDetail.promotedDocPageTitle'),
          source_app: 'pms',
          source_kind: 'task_description',
          source_ref: issue.id,
          doc_type: 'memo',
          content_format: 'block',
          primary_target: spaceId
            ? {
                app: 'pms',
                type: 'space',
                id: spaceId,
              }
            : null,
        },
        workspaceSlug,
      );

      const pages = await listDocPages(token, doc.id, null, workspaceSlug);
      const firstPage = pages.items[0];
      if (firstPage) {
        await updateDocPage(
          token,
          firstPage.id,
          {
            title: t('pms.taskDetail.promotedDocPageTitle'),
            content_blocks: contentBlocks,
          },
          null,
          workspaceSlug,
        );
      }

      const response = await attachTaskDoc(
        token,
        issue.id,
        doc.id,
        workspaceSlug,
      );
      setLinkedDocs(response.items);
      await notifyTaskDetailUpdated(onUpdate);
    } catch (error) {
      setSaveError(
        getTaskDetailMutationErrorMessage(
          error,
          t('pms.taskDetail.errors.promoteDescriptionFailed'),
        ),
      );
    } finally {
      setPromotingDescription(false);
    }
  }, [
    canEdit,
    descriptionBlocksRef,
    issue.description_blocks,
    issue.id,
    issue.title,
    onUpdate,
    promotingDescription,
    setLinkedDocs,
    setSaveError,
    spaceId,
    t,
    token,
    workspaceSlug,
  ]);

  const handleLinkDoc = useCallback(
    async (docId: string) => {
      if (!token || !canEdit) return;
      try {
        const response = await attachTaskDoc(
          token,
          issue.id,
          docId,
          workspaceSlug,
        );
        setLinkedDocs(response.items);
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        const message = getTaskDetailMutationErrorMessage(
          error,
          t('pms.taskDetail.errors.linkDocFailed'),
        );
        setSaveError(message);
        throw new Error(message);
      }
    },
    [
      canEdit,
      issue.id,
      onUpdate,
      setLinkedDocs,
      setSaveError,
      t,
      token,
      workspaceSlug,
    ],
  );

  const handleUnlinkDoc = useCallback(
    async (docId: string) => {
      if (!token || !canEdit) return;
      try {
        const response = await detachTaskDoc(
          token,
          issue.id,
          docId,
          workspaceSlug,
        );
        setLinkedDocs(response.items);
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.unlinkDocFailed'),
          ),
        );
      }
    },
    [
      canEdit,
      issue.id,
      onUpdate,
      setLinkedDocs,
      setSaveError,
      t,
      token,
      workspaceSlug,
    ],
  );

  return {
    buildDocPath,
    docPickerOpen,
    handleLinkDoc,
    handlePromoteDescriptionToDoc,
    handleUnlinkDoc,
    promotingDescription,
    setDocPickerOpen,
  };
}
