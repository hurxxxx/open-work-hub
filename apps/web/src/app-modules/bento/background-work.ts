import type { BackgroundWorkSource } from '@/src/platform/background-work/background-work-session';
import { cancelBentoAiJob, listBentoAiJobs } from './api/bento-api';
import {
  buildBentoHubPath,
  buildBentoPresentationPath,
} from './bento-route-paths';

export const bentoAiBackgroundWorkSource: Omit<BackgroundWorkSource, 'appId'> =
  {
    id: 'bento-ai',
    requiredNavItemId: 'bento-all',
    pollIntervalMs: 3000,
    idlePollIntervalMs: 20000,
    async list({ token, workspaceSlug, t }) {
      const jobs = await listBentoAiJobs(token, workspaceSlug);
      return jobs.map((job) => ({
        id: job.id,
        sourceId: 'bento-ai',
        kind: `bento-${job.kind}`,
        title:
          job.kind === 'create'
            ? t('apps:bento.aiBackgroundCreate')
            : t('apps:bento.aiBackgroundEdit'),
        description:
          job.error_code ??
          (job.status === 'running'
            ? t('apps:bento.aiBackgroundProgress', {
                progress: job.progress_percent,
              })
            : job.status === 'queued'
              ? t('apps:bento.aiBackgroundQueued')
              : undefined),
        status: job.status,
        href: job.result_document_id
          ? buildBentoPresentationPath(workspaceSlug, job.result_document_id)
          : buildBentoHubPath(workspaceSlug),
        cancellable: job.cancellable,
        updatedAt: job.updated_at,
      }));
    },
    async cancel({ token, workspaceSlug, item }) {
      await cancelBentoAiJob(token, item.id, workspaceSlug);
    },
  };
