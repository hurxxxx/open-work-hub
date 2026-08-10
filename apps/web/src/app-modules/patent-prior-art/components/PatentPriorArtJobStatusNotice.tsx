import { useTranslation } from 'react-i18next';

import { InlineNotice } from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';

import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import {
  patentPriorArtFailureMessageKey,
  patentPriorArtJobDisplayStatus,
} from '../model/patent-prior-art-view-model';

export function PatentPriorArtJobStatusNotice({
  job,
}: {
  job: PatentPriorArtJob;
}) {
  const { t } = useTranslation('apps');
  const displayStatus = patentPriorArtJobDisplayStatus(job);

  if (displayStatus === 'retry_waiting') {
    return (
      <InlineNotice className="mt-4" role="status" tone="warning">
        <div className="space-y-1">
          <p>
            {t('ai.patentPriorArt.job.retryWaiting', {
              attemptCount: Math.max(1, job.execution_attempts ?? 0),
              restartCount: Math.max(1, job.automatic_restart_count ?? 0),
            })}
          </p>
          {job.next_attempt_at ? (
            <p className="flex flex-wrap items-center gap-1.5 app-text-caption">
              <span>{t('ai.patentPriorArt.job.nextAttempt')}</span>
              <UserDateTime display="datetime" value={job.next_attempt_at} />
            </p>
          ) : null}
        </div>
      </InlineNotice>
    );
  }

  if (job.status === 'failed') {
    return (
      <InlineNotice className="mt-4" role="alert" tone="danger">
        {t(patentPriorArtFailureMessageKey(job.failure_code))}
      </InlineNotice>
    );
  }

  if (displayStatus === 'cleanup_pending') {
    return (
      <InlineNotice className="mt-4" tone="warning">
        {t('ai.patentPriorArt.job.cleanupPending')}
      </InlineNotice>
    );
  }

  if (job.status === 'cancelled') {
    return (
      <InlineNotice className="mt-4" tone="info">
        {t('ai.patentPriorArt.job.cancelled')}
      </InlineNotice>
    );
  }

  return null;
}
