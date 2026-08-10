import type { BackgroundWorkSource } from '@/src/platform/background-work/background-work-provider';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

import {
  cancelImageGeneration,
  listImageGenerations,
  type ImageGeneration,
  type ImageGenerationStatus,
} from './api/image-wizard-api';

const BACKGROUND_STATUSES = new Set<ImageGenerationStatus>([
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
]);

type ImageBackgroundStatus = Exclude<ImageGenerationStatus, 'idle'>;

function isBackgroundStatus(
  status: ImageGenerationStatus,
): status is ImageBackgroundStatus {
  return BACKGROUND_STATUSES.has(status) && status !== 'idle';
}

function imageWizardHref(
  appId: string,
  workspaceSlug: string,
  item: ImageGeneration,
): string {
  const params = new URLSearchParams({
    gen: item.id,
    step: '4',
  });
  return buildWorkspaceAppPath(workspaceSlug, appId, `?${params.toString()}`);
}

export function createImageWizardBackgroundWorkSource(
  appId: string,
): Omit<BackgroundWorkSource, 'appId'> {
  return {
    id: 'image-wizard',
    pollIntervalMs: 3000,
    idlePollIntervalMs: 60000,
    async list({ token, workspaceSlug, t }) {
      const response = await listImageGenerations(token, workspaceSlug, {
        limit: 20,
        has_image_activity: true,
      });
      return response.items.flatMap((item) => {
        const status = item.image_status;
        if (!isBackgroundStatus(status)) return [];
        return [
          {
            id: item.id,
            sourceId: 'image-wizard',
            kind: 'image_generation',
            title: t('apps:ai.imageWizard.backgroundWork.title'),
            description: t(
              `apps:ai.imageWizard.backgroundWork.status.${status}`,
            ),
            status,
            href: imageWizardHref(appId, workspaceSlug, item),
            cancellable: status === 'queued' || status === 'running',
            updatedAt: item.updated_at,
          },
        ];
      });
    },
    async cancel({ token, workspaceSlug, item }) {
      await cancelImageGeneration(token, workspaceSlug, item.id);
    },
  };
}
