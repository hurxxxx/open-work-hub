import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';

const GENERATED_IMAGE_ASSET_LOAD_CONCURRENCY = 4;

export interface GeneratedImageAssetPort {
  downloadBlob: (generationId: string) => Promise<Blob>;
  createObjectUrl: (blob: Blob) => string;
  revokeObjectUrl: (objectUrl: string) => void;
}

export interface LoadedGeneratedImageAsset {
  generationId: string;
  url: string;
  dispose: () => void;
}

export interface GeneratedImageAssetResult {
  generationId: string;
  url: string | null;
  error: unknown | null;
}

export interface LoadedGeneratedImageAssetBatch {
  results: GeneratedImageAssetResult[];
  dispose: () => void;
}

export async function loadGeneratedImageAsset(
  generationId: string,
  port: GeneratedImageAssetPort,
): Promise<LoadedGeneratedImageAsset> {
  const blob = await port.downloadBlob(generationId);
  const objectUrl = port.createObjectUrl(blob);
  return {
    generationId,
    url: objectUrl,
    dispose: createObjectUrlDisposer(port, [objectUrl]),
  };
}

export async function loadGeneratedImageAssets(
  generationIds: readonly string[],
  port: GeneratedImageAssetPort,
): Promise<LoadedGeneratedImageAssetBatch> {
  const objectUrls: string[] = [];
  const results = await runRequestsWithConcurrency(
    generationIds,
    GENERATED_IMAGE_ASSET_LOAD_CONCURRENCY,
    async (generationId): Promise<GeneratedImageAssetResult> => {
      try {
        const blob = await port.downloadBlob(generationId);
        const objectUrl = port.createObjectUrl(blob);
        objectUrls.push(objectUrl);
        return {
          generationId,
          url: objectUrl,
          error: null,
        };
      } catch (error) {
        return {
          generationId,
          url: null,
          error,
        };
      }
    },
  );
  return {
    results,
    dispose: createObjectUrlDisposer(port, objectUrls),
  };
}

function createObjectUrlDisposer(
  port: GeneratedImageAssetPort,
  objectUrls: string[],
): () => void {
  let disposed = false;
  return () => {
    if (disposed) return;
    disposed = true;
    for (const objectUrl of objectUrls) {
      port.revokeObjectUrl(objectUrl);
    }
  };
}
