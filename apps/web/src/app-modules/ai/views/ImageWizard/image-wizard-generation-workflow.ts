import type {
  ImageGeneration,
  ImageGenerationCreatePayload,
  ImageGenerationPatchPayload,
  ReferenceImageRole,
} from '../../api/image-wizard-api';
import type { StepId } from './wizard-state';
import type { TemplatePreset } from './templates/template-presets';
import {
  shouldReviewImageEditInstruction,
  shouldStartNewGenerationForTemplatePick,
} from './image-edit-policy';
import {
  buildBlankGenerationPayload,
  buildCloneGenerationPayload,
  buildImageEditGenerationPayload,
  buildTemplatePickGenerationPayload,
} from './image-wizard-flow-model';

export interface ImageWizardRouteTarget {
  gen?: string | null;
  step?: StepId;
}

export interface ImageWizardGenerationRoutePort {
  push(next: ImageWizardRouteTarget): void;
  replace(next: ImageWizardRouteTarget): void;
}

export interface ImageWizardGenerationDraftPort {
  applyServer(next: ImageGeneration): void;
  flush(): Promise<void>;
  readonly row: ImageGeneration | null;
  startNew(payload: ImageGenerationCreatePayload): Promise<ImageGeneration>;
  update(patch: ImageGenerationPatchPayload): void;
}

export interface ImageWizardGenerationApiPort {
  approve(generationId: string): Promise<ImageGeneration>;
  create(payload: ImageGenerationCreatePayload): Promise<ImageGeneration>;
  delete(generationId: string): Promise<void>;
  downloadBlob(generationId: string): Promise<Blob>;
  get(generationId: string): Promise<ImageGeneration>;
  uploadReference(
    generationId: string,
    file: File,
    role: ReferenceImageRole,
  ): Promise<unknown>;
}

export interface ImageWizardImageEditCopy {
  referenceText: string;
  requestText(instruction: string): string;
}

export interface ImageWizardGenerationWorkflowOptions {
  api: ImageWizardGenerationApiPort | null;
  canDeleteIdleRows: boolean;
  createSourceFile?: (blob: Blob, source: ImageGeneration) => File;
  draft: ImageWizardGenerationDraftPort;
  imageEditCopy: ImageWizardImageEditCopy;
  route: ImageWizardGenerationRoutePort;
}

export interface ImageWizardGenerationWorkflow {
  cloneCurrent(): Promise<void>;
  discardCurrent(): void;
  editCurrentImage(instruction: string): Promise<void>;
  pickBlank(): Promise<void>;
  pickTemplate(template: TemplatePreset): Promise<void>;
  startNewImage(): Promise<void>;
}

export function createImageEditSourceFile(
  blob: Blob,
  source: Pick<ImageGeneration, 'id'>,
): File {
  return new File([blob], `image-edit-source-${source.id}.png`, {
    type: blob.type || 'image/png',
  });
}

function deleteIdleRowIfPossible({
  api,
  canDeleteIdleRows,
  row,
}: {
  api: ImageWizardGenerationApiPort | null;
  canDeleteIdleRows: boolean;
  row: ImageGeneration | null;
}): Promise<void> | null {
  if (!api || !canDeleteIdleRows || row?.image_status !== 'idle') {
    return null;
  }
  return api.delete(row.id).catch(() => undefined);
}

export function createImageWizardGenerationWorkflow({
  api,
  canDeleteIdleRows,
  createSourceFile = createImageEditSourceFile,
  draft,
  imageEditCopy,
  route,
}: ImageWizardGenerationWorkflowOptions): ImageWizardGenerationWorkflow {
  return {
    async pickTemplate(template) {
      const payload = buildTemplatePickGenerationPayload(template);
      const row = draft.row;
      if (!row || shouldStartNewGenerationForTemplatePick(row)) {
        const created = await draft.startNew(payload);
        route.replace({ gen: created.id, step: 2 });
        return;
      }
      draft.update(payload);
      route.replace({ step: 2 });
    },

    async pickBlank() {
      if (!draft.row) {
        const created = await draft.startNew(buildBlankGenerationPayload());
        route.replace({ gen: created.id, step: 2 });
        return;
      }
      route.replace({ step: 2 });
    },

    async cloneCurrent() {
      const row = draft.row;
      if (!row) return;
      const created = await draft.startNew(buildCloneGenerationPayload(row));
      route.push({ gen: created.id, step: 4 });
    },

    async editCurrentImage(instruction) {
      if (!api || !draft.row) return;
      const source = draft.row;
      const trimmedInstruction = instruction.trim();
      const requiresPlan = shouldReviewImageEditInstruction(trimmedInstruction);
      const sourceBlob = await api.downloadBlob(source.id);
      let created: ImageGeneration | null = null;

      try {
        created = await api.create(
          buildImageEditGenerationPayload({
            editReferenceText: imageEditCopy.referenceText,
            editRequestText: imageEditCopy.requestText(trimmedInstruction),
            requiresPlan,
            source,
            trimmedInstruction,
          }),
        );
        const createdId = created.id;
        await api.uploadReference(
          createdId,
          createSourceFile(sourceBlob, source),
          'composition',
        );
        const next = requiresPlan
          ? await api.get(createdId)
          : await api.approve(createdId);
        draft.applyServer(next);
        route.push({ gen: createdId, step: 4 });
      } catch (error) {
        if (created) {
          await api.delete(created.id).catch(() => undefined);
        }
        throw error;
      }
    },

    async startNewImage() {
      const row = draft.row;
      const deletion = deleteIdleRowIfPossible({
        api,
        canDeleteIdleRows,
        row,
      });
      if (deletion) {
        await deletion;
      } else {
        await draft.flush();
      }
      route.push({ gen: null, step: 1 });
    },

    discardCurrent() {
      void deleteIdleRowIfPossible({
        api,
        canDeleteIdleRows,
        row: draft.row,
      });
      route.replace({ gen: null, step: 1 });
    },
  };
}
