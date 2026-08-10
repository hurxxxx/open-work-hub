import type { TFunction } from 'i18next';

import type { ImageGeneration } from '../../../api/image-wizard-api';
import type { Step4BriefAction } from './step4-brief-model';

export interface Step4BriefOperationApi {
  generateBrief: (
    token: string,
    workspaceSlug: string,
    generationId: string,
    options?: { editInstruction?: string },
  ) => Promise<unknown>;
  getGeneration: (
    token: string,
    workspaceSlug: string,
    generationId: string,
  ) => Promise<ImageGeneration>;
  approveGeneration: (
    token: string,
    workspaceSlug: string,
    generationId: string,
  ) => Promise<ImageGeneration>;
  cancelGeneration: (
    token: string,
    workspaceSlug: string,
    generationId: string,
  ) => Promise<ImageGeneration>;
  setTemplate: (
    token: string,
    workspaceSlug: string,
    generationId: string,
    nextIsTemplate: boolean,
  ) => Promise<ImageGeneration>;
}

export interface Step4BriefOperations {
  runGenerateBrief: (editInstruction?: string) => Promise<void>;
  runApprove: () => Promise<void>;
  runCancel: () => Promise<void>;
  runImageEdit: (instruction: string) => Promise<void>;
  runTemplateToggle: (nextIsTemplate: boolean) => Promise<void>;
}

export interface CreateStep4BriefOperationsInput {
  api: Step4BriefOperationApi;
  dispatch: (action: Step4BriefAction) => void;
  onImageEdit: (instruction: string) => Promise<void>;
  onRowReplaced: (next: ImageGeneration) => void;
  onTemplateChanged?: (next: ImageGeneration) => void;
  row: ImageGeneration;
  t: TFunction<'apps'>;
  token: string | null | undefined;
  workspaceSlug: string;
}

export function createStep4BriefOperations({
  api,
  dispatch,
  onImageEdit,
  onRowReplaced,
  onTemplateChanged,
  row,
  t,
  token,
  workspaceSlug,
}: CreateStep4BriefOperationsInput): Step4BriefOperations {
  return {
    async runGenerateBrief(editInstruction?: string) {
      if (!token) return;
      dispatch({ type: 'operation:start', busy: 'brief' });
      try {
        await api.generateBrief(token, workspaceSlug, row.id, { editInstruction });
        const refreshed = await api.getGeneration(token, workspaceSlug, row.id);
        onRowReplaced(refreshed);
      } catch (err) {
        dispatch({
          type: 'operation:fail',
          message: err instanceof Error ? err.message : t('ai.imageWizard.errors.briefFailed'),
        });
      } finally {
        dispatch({ type: 'operation:finish' });
      }
    },

    async runApprove() {
      if (!token) return;
      dispatch({ type: 'operation:start', busy: 'approve' });
      try {
        const approved = await api.approveGeneration(token, workspaceSlug, row.id);
        onRowReplaced(approved);
      } catch (err) {
        dispatch({
          type: 'operation:fail',
          message: err instanceof Error ? err.message : t('ai.imageWizard.errors.approveFailed'),
        });
      } finally {
        dispatch({ type: 'operation:finish' });
      }
    },

    async runCancel() {
      if (!token) return;
      dispatch({ type: 'operation:start', busy: 'cancel' });
      try {
        const cancelled = await api.cancelGeneration(token, workspaceSlug, row.id);
        onRowReplaced(cancelled);
      } catch (err) {
        dispatch({
          type: 'operation:fail',
          message: err instanceof Error ? err.message : t('ai.imageWizard.errors.cancelFailed'),
        });
      } finally {
        dispatch({ type: 'operation:finish' });
      }
    },

    async runImageEdit(instruction: string) {
      dispatch({ type: 'operation:start', busy: 'image-edit' });
      try {
        await onImageEdit(instruction);
      } catch (err) {
        dispatch({
          type: 'operation:fail',
          message: err instanceof Error ? err.message : t('ai.imageWizard.errors.editImageFailed'),
        });
      } finally {
        dispatch({ type: 'operation:finish' });
      }
    },

    async runTemplateToggle(nextIsTemplate: boolean) {
      if (!token) return;
      dispatch({ type: 'template:start' });
      try {
        const updated = await api.setTemplate(token, workspaceSlug, row.id, nextIsTemplate);
        onRowReplaced(updated);
        onTemplateChanged?.(updated);
      } catch (err) {
        dispatch({
          type: 'template:fail',
          message: err instanceof Error ? err.message : t('ai.imageWizard.errors.saveFailed'),
        });
      } finally {
        dispatch({ type: 'template:finish' });
      }
    },
  };
}
