export type ImageResultMode = 'failed' | 'loading' | 'loadError' | 'empty' | 'ready';

export interface ImageResultModeArgs {
  failureReason: string | null;
  imageUrl: string | null;
  loadError: string | null;
  loading: boolean;
}

export interface ImageEditSubmitStateArgs {
  editText: string;
  editingImage: boolean;
}

export interface ImagePreviewDescriptor {
  altKey: string;
  altOptions?: Record<string, unknown>;
  downloadName: string;
  imageUrl: string;
  titleKey: string;
  titleOptions?: Record<string, unknown>;
}

export interface ResolvedImagePreviewDescriptor {
  alt: string;
  downloadName: string;
  imageUrl: string;
  title: string;
}

export type ImageResultTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export function getImageResultMode({
  failureReason,
  imageUrl,
  loadError,
  loading,
}: ImageResultModeArgs): ImageResultMode {
  if (failureReason) return 'failed';
  if (loading) return 'loading';
  if (loadError) return 'loadError';
  if (!imageUrl) return 'empty';
  return 'ready';
}

export function getTrimmedImageEditInstruction(editText: string): string {
  return editText.trim();
}

export function canSubmitImageEdit({
  editText,
  editingImage,
}: ImageEditSubmitStateArgs): boolean {
  return !editingImage && getTrimmedImageEditInstruction(editText).length > 0;
}

export function getImageTemplateToggleLabelKey(isTemplate: boolean): string {
  return isTemplate
    ? 'ai.imageWizard.step4.removeFromTemplates'
    : 'ai.imageWizard.step4.saveCurrentAsTemplate';
}

export function getNextImageTemplateState(isTemplate: boolean): boolean {
  return !isTemplate;
}

export function buildSourceImagePreviewDescriptor(imageUrl: string): ImagePreviewDescriptor {
  return {
    imageUrl,
    altKey: 'ai.imageWizard.step4.sourceImageAltText',
    titleKey: 'ai.imageWizard.step4.sourceImageLabel',
    downloadName: 'generated-image-source.png',
  };
}

export function buildEditedImagePreviewDescriptor(
  imageUrl: string,
  variant: 'comparison' | 'solo',
): ImagePreviewDescriptor {
  return {
    imageUrl,
    altKey: 'ai.imageWizard.step4.altText',
    titleKey:
      variant === 'comparison'
        ? 'ai.imageWizard.step4.editedImageLabel'
        : 'ai.imageWizard.step4.altText',
    downloadName: 'generated-image.png',
  };
}

export function buildRevisionImagePreviewDescriptor(
  imageUrl: string,
  index: number,
): ImagePreviewDescriptor {
  const displayIndex = index + 1;
  return {
    imageUrl,
    altKey: 'ai.imageWizard.step4.revisionImageAlt',
    altOptions: { index: displayIndex },
    titleKey: 'ai.imageWizard.step4.revisionLabel',
    titleOptions: { index: displayIndex },
    downloadName: getRevisionImageDownloadName(index),
  };
}

export function getRevisionImageDownloadName(index: number): string {
  return `generated-image-${index + 1}.png`;
}

export function resolveImagePreviewDescriptor(
  descriptor: ImagePreviewDescriptor,
  t: ImageResultTranslator,
): ResolvedImagePreviewDescriptor {
  return {
    imageUrl: descriptor.imageUrl,
    alt: t(descriptor.altKey, descriptor.altOptions),
    title: t(descriptor.titleKey, descriptor.titleOptions),
    downloadName: descriptor.downloadName,
  };
}
