import type { ImageGeneration } from '../../../api/image-wizard-api';
import {
  loadGeneratedImageAsset,
  loadGeneratedImageAssets,
  type LoadedGeneratedImageAsset,
} from '../generated-image-assets';
import {
  collectImageRevisionRows,
  type ImageRevisionGalleryItem,
} from './step4-brief-model';

export type { LoadedGeneratedImageAsset } from '../generated-image-assets';

export interface Step4GeneratedImageAssetApi {
  downloadBlob: (
    token: string,
    workspaceSlug: string,
    generationId: string,
  ) => Promise<Blob>;
  createObjectUrl: (blob: Blob) => string;
  revokeObjectUrl: (objectUrl: string) => void;
}

export interface LoadStep4GeneratedImageAssetInput {
  api: Step4GeneratedImageAssetApi;
  generationId: string;
  token: string;
  workspaceSlug: string;
}

export interface LoadStep4RevisionGalleryInput {
  api: Step4GeneratedImageAssetApi;
  current: ImageGeneration;
  candidates: readonly ImageGeneration[];
  revisionImageLoadFailed: string;
  token: string;
  workspaceSlug: string;
}

export interface LoadedStep4RevisionGallery {
  items: ImageRevisionGalleryItem[];
  dispose: () => void;
}

export function step4AssetLoadErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function createStep4BrowserGeneratedImageAssetApi(
  downloadBlob: Step4GeneratedImageAssetApi['downloadBlob'],
): Step4GeneratedImageAssetApi {
  return {
    downloadBlob,
    createObjectUrl: (blob) => URL.createObjectURL(blob),
    revokeObjectUrl: (objectUrl) => URL.revokeObjectURL(objectUrl),
  };
}

export function loadStep4GeneratedImageAsset({
  api,
  generationId,
  token,
  workspaceSlug,
}: LoadStep4GeneratedImageAssetInput): Promise<LoadedGeneratedImageAsset> {
  return loadGeneratedImageAsset(generationId, {
    downloadBlob: (nextGenerationId) =>
      api.downloadBlob(token, workspaceSlug, nextGenerationId),
    createObjectUrl: api.createObjectUrl,
    revokeObjectUrl: api.revokeObjectUrl,
  });
}

export async function loadStep4RevisionGallery({
  api,
  candidates,
  current,
  revisionImageLoadFailed,
  token,
  workspaceSlug,
}: LoadStep4RevisionGalleryInput): Promise<LoadedStep4RevisionGallery> {
  const revisions = collectImageRevisionRows(current, candidates);
  const loadedAssets = await loadGeneratedImageAssets(
    revisions.map((item) => item.id),
    {
      downloadBlob: (generationId) => api.downloadBlob(token, workspaceSlug, generationId),
      createObjectUrl: api.createObjectUrl,
      revokeObjectUrl: api.revokeObjectUrl,
    },
  );
  const byId = new Map(loadedAssets.results.map((item) => [item.generationId, item]));
  return {
    items: revisions.map((item) => {
      const result = byId.get(item.id);
      return {
        id: item.id,
        imageUrl: result?.url ?? null,
        loadError: result?.error
          ? step4AssetLoadErrorMessage(result.error, revisionImageLoadFailed)
          : null,
        createdAt: item.created_at,
        isCurrent: item.id === current.id,
      };
    }),
    dispose: loadedAssets.dispose,
  };
}
