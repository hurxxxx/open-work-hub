import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, InlineNotice } from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';

import {
  getAdminModelRuntimeStatus,
  type AdminModelRuntimeStatusSnapshot,
  type ModelRuntimeStatus,
} from './admin-model-runtime-status-api';
import { BodyCell, EmptyRow, HeadCell } from './admin-shared';

function StatusBadge({ status }: { status: ModelRuntimeStatus }) {
  const { t } = useTranslation('apps');
  const toneClassName =
    status === 'online'
      ? 'border-app-success-border bg-app-success/10 text-app-success-text'
      : status === 'degraded'
        ? 'border-app-warning/20 bg-app-warning/10 text-app-warning-text'
        : status === 'not_configured'
          ? 'border-app-border bg-app-surface-sidebar text-app-ink/55'
          : 'border-app-danger-border bg-app-danger/10 text-app-danger-text';

  return (
    <span
      className={`app-text-label inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${toneClassName}`}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      {t(`admin.console.modelMonitoring.status.${status}`)}
    </span>
  );
}

export function AdminModelRuntimeStatusSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const [snapshot, setSnapshot] =
    useState<AdminModelRuntimeStatusSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setSnapshot(await getAdminModelRuntimeStatus(token));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-3">
        <p className="app-text-body-sm text-app-ink/55">
          {snapshot ? (
            <>
              {t('admin.console.modelMonitoring.lastChecked')}{' '}
              <UserDateTime display="datetime" value={snapshot.checked_at} />
            </>
          ) : (
            t('admin.console.modelMonitoring.notChecked')
          )}
        </p>
        <Button
          disabled={loading}
          onClick={() => void load()}
          size="dense"
          variant="secondary"
        >
          <RefreshCw className={loading ? 'animate-spin' : ''} size={14} />
          {t('admin.console.modelMonitoring.refresh')}
        </Button>
      </div>

      {error ? (
        <InlineNotice role="alert" tone="danger">
          {t('admin.console.modelMonitoring.loadFailed')}
        </InlineNotice>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <HeadCell dense>
                {t('admin.console.modelMonitoring.columns.target')}
              </HeadCell>
              <HeadCell dense>
                {t('admin.console.modelMonitoring.columns.status')}
              </HeadCell>
              <HeadCell dense>
                {t('admin.console.modelMonitoring.columns.models')}
              </HeadCell>
            </tr>
          </thead>
          <tbody>
            {snapshot?.targets.map((target) => (
              <tr key={target.id}>
                <BodyCell className="font-medium" dense>
                  {target.display_name}
                </BodyCell>
                <BodyCell dense>
                  <StatusBadge status={target.status} />
                </BodyCell>
                <BodyCell dense>
                  {target.models.length > 0 ? (
                    <ul className="space-y-1">
                      {target.models.map((model) => (
                        <li
                          className={model.loaded ? '' : 'text-app-ink/45'}
                          key={`${model.task ?? 'model'}:${model.name}`}
                        >
                          <span className="break-all">{model.name}</span>
                          {model.task ? (
                            <span className="app-text-caption ml-2 text-app-ink/45">
                              {t(
                                `admin.console.modelMonitoring.tasks.${model.task}`,
                                { defaultValue: model.task },
                              )}
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-app-ink/45">
                      {t('admin.console.modelMonitoring.noModels')}
                    </span>
                  )}
                </BodyCell>
              </tr>
            ))}
            {!snapshot || snapshot.targets.length === 0 ? (
              <EmptyRow
                colSpan={3}
                description={t(
                  loading
                    ? 'admin.console.modelMonitoring.loadingDescription'
                    : 'admin.console.modelMonitoring.emptyDescription',
                )}
                title={t(
                  loading
                    ? 'admin.console.modelMonitoring.loadingTitle'
                    : 'admin.console.modelMonitoring.emptyTitle',
                )}
              />
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
