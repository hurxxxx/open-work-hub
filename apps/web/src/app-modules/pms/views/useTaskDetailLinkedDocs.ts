import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import { useConfirm, type BlockContent } from '@open-work-hub/ui';
import type { TFunction } from 'i18next';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefObject,
  type SetStateAction,
} from 'react';

import {
  createNativeDoc,
  listDocPages,
  updateDocPage,
} from '@/src/app-modules/docs/public-api';
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

export function resolveTaskDetailDocPath({ docId }: { docId: string }): string {
  return buildAppHref({
    routeId: 'docs.document',
    pathParams: { docId },
  });
}

export function useTaskDetailLinkedDocs({
  canEdit,
  canPublishDoc,
  descriptionBlocksRef,
  issue,
  onUpdate,
  setLinkedDocs,
  setSaveError,
  spaceId,
  token,
  t,
}: {
  canEdit: boolean;
  canPublishDoc: boolean;
  descriptionBlocksRef: RefObject<BlockContent | null>;
  issue: Pick<PmsTask, 'description_blocks' | 'id' | 'title'>;
  onUpdate?: () => void | Promise<void>;
  setLinkedDocs: (value: SetStateAction<PmsTaskDocLink[]>) => void;
  setSaveError: (message: string | null) => void;
  spaceId: string | null;
  token: string | null;
  t: TFunction;
}) {
  const [docPickerOpen, setDocPickerOpen] = useState(false);
  const [promotingDescription, setPromotingDescription] = useState(false);
  const { confirm, confirmDialog } = useConfirm();
  const publicationGeneration = useRef(0);
  useEffect(() => {
    setPromotingDescription(false);
    setDocPickerOpen(false);
    return () => {
      publicationGeneration.current += 1;
    };
  }, [token, issue.id, spaceId, canEdit, canPublishDoc]);

  const buildDocPath = useCallback(
    (docId: string) => resolveTaskDetailDocPath({ docId }),
    [],
  );

  const handlePromoteDescriptionToDoc = useCallback(async () => {
    if (
      !token ||
      !canEdit ||
      (spaceId && !canPublishDoc) ||
      promotingDescription
    )
      return;
    const generation = publicationGeneration.current;
    setPromotingDescription(true);
    setSaveError(null);

    try {
      const acknowledged = spaceId
        ? await confirm({
            title: t('shell:contentPublication.title'),
            description: t('shell:contentPublication.confirm'),
            confirmLabel: t('common:actions.confirm'),
            cancelLabel: t('common:actions.cancel'),
          })
        : false;
      if (
        generation !== publicationGeneration.current ||
        (spaceId && !acknowledged)
      )
        return;
      const contentBlocks = resolveTaskDetailPromotedDocContent({
        descriptionBlocks: descriptionBlocksRef.current,
        issueDescriptionBlocks: issue.description_blocks,
      });
      const doc = await createNativeDoc(token, {
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
              company_admin_read_acknowledged: acknowledged,
            }
          : null,
      });
      if (generation !== publicationGeneration.current) return;

      const pages = await listDocPages(token, doc.id, null);
      if (generation !== publicationGeneration.current) return;
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
        );
      }

      if (generation !== publicationGeneration.current) return;
      const response = await attachTaskDoc(token, issue.id, doc.id);
      if (generation !== publicationGeneration.current) return;
      setLinkedDocs(response.items);
      await notifyTaskDetailUpdated(onUpdate);
    } catch (error) {
      if (generation !== publicationGeneration.current) return;
      setSaveError(
        getTaskDetailMutationErrorMessage(
          error,
          t('pms.taskDetail.errors.promoteDescriptionFailed'),
        ),
      );
    } finally {
      if (generation === publicationGeneration.current)
        setPromotingDescription(false);
    }
  }, [
    canEdit,
    canPublishDoc,
    confirm,
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
  ]);

  const handleLinkDoc = useCallback(
    async (docId: string) => {
      if (!token || !canEdit) return;
      const generation = publicationGeneration.current;
      try {
        const response = await attachTaskDoc(token, issue.id, docId);
        if (generation !== publicationGeneration.current) return;
        setLinkedDocs(response.items);
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        if (generation !== publicationGeneration.current) return;
        const message = getTaskDetailMutationErrorMessage(
          error,
          t('pms.taskDetail.errors.linkDocFailed'),
        );
        setSaveError(message);
        throw new Error(message);
      }
    },
    [canEdit, issue.id, onUpdate, setLinkedDocs, setSaveError, t, token],
  );

  const handleUnlinkDoc = useCallback(
    async (docId: string) => {
      if (!token || !canEdit) return;
      const generation = publicationGeneration.current;
      try {
        const response = await detachTaskDoc(token, issue.id, docId);
        if (generation !== publicationGeneration.current) return;
        setLinkedDocs(response.items);
        await notifyTaskDetailUpdated(onUpdate);
      } catch (error) {
        if (generation !== publicationGeneration.current) return;
        setSaveError(
          getTaskDetailMutationErrorMessage(
            error,
            t('pms.taskDetail.errors.unlinkDocFailed'),
          ),
        );
      }
    },
    [canEdit, issue.id, onUpdate, setLinkedDocs, setSaveError, t, token],
  );

  return {
    confirmDialog,
    buildDocPath,
    docPickerOpen,
    handleLinkDoc,
    handlePromoteDescriptionToDoc,
    handleUnlinkDoc,
    promotingDescription,
    setDocPickerOpen,
  };
}
