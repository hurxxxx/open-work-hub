import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { EmptyState, InlineNotice } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { type SysPerfDbTest } from '../api/dataviz-api';
import {
  deleteSysPerfDbResult,
  listSysPerfDbResults,
  prepareSysPerfDbCsvDownload,
} from './sysperf-db-result-loader';
import { formatSysPerfErrorMessage, type SysPerfNotice } from './sysperf-error';
import { useSysPerfWorkspace } from './sysperf-workspace';

const DB_COLS: { key: keyof SysPerfDbTest; labelKey: string }[] = [
  { key: 'id', labelKey: 'id' },
  { key: 'saved_at', labelKey: 'savedAt' },
  { key: 'filename', labelKey: 'filename' },
  { key: 'car_code', labelKey: 'carCode' },
  { key: 'car_type', labelKey: 'carType' },
  { key: 'engine', labelKey: 'engine' },
  { key: 'stage', labelKey: 'stage' },
  { key: 'car_number', labelKey: 'carNumber' },
  { key: 'test_item', labelKey: 'testItem' },
  { key: 'test_date', labelKey: 'testDate' },
  { key: 'refrigerant_charge', labelKey: 'refrigerantCharge' },
  { key: 'comp', labelKey: 'comp' },
  { key: 'indoor_condenser', labelKey: 'indoorCondenser' },
  { key: 'condenser', labelKey: 'condenser' },
  { key: 'cooling_fan', labelKey: 'coolingFan' },
  { key: 'radiator', labelKey: 'radiator' },
  { key: 'ihx', labelKey: 'ihx' },
  { key: 'txv', labelKey: 'txv' },
  { key: 'battery_chiller', labelKey: 'batteryChiller' },
  { key: 'eva', labelKey: 'eva' },
  { key: 'hvac', labelKey: 'hvac' },
  { key: 'heater_core', labelKey: 'heaterCore' },
  { key: 'ptc', labelKey: 'ptc' },
];

export function SysPerfDbResultTab() {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const [rows, setRows] = useState<SysPerfDbTest[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<SysPerfNotice | null>(null);

  const load = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setBusy(true);
    try {
      const r = await listSysPerfDbResults({ token, workspaceSlug });
      setRows(r.data);
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.db.loadFailed'),
        ),
      });
    } finally {
      setBusy(false);
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const onDownload = async (id: number, name: string) => {
    if (!token || !workspaceSlug) return;
    setNotice(null);
    try {
      const download = await prepareSysPerfDbCsvDownload({
        token,
        workspaceSlug,
        testId: id,
        name,
      });
      downloadBlobAsFile(download.blob, download.filename);
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.db.downloadFailed'),
        ),
      });
    }
  };

  const onDelete = async (id: number) => {
    if (!token || !workspaceSlug) return;
    setNotice(null);
    try {
      await deleteSysPerfDbResult({ token, workspaceSlug, testId: id });
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.db.deleteFailed'),
        ),
      });
    }
  };

  if (busy && !rows.length) {
    return (
      <div className="grid place-items-center py-16">
        <Loader2 size={20} className="animate-spin text-app-accent" />
      </div>
    );
  }
  if (!rows.length)
    return (
      <div className="flex flex-col gap-3">
        {notice ? (
          <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
        ) : null}
        <EmptyState title={t('ai.dataViz.sysPerf.db.empty')} />
      </div>
    );

  return (
    <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <div className="mb-3 flex items-center gap-2">
        <div className="app-text-body-sm font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.db.title', { count: rows.length })}
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="app-text-control-sm inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink/75 transition-colors hover:bg-app-surface-hover"
        >
          <RefreshCw size={14} />
          {t('ai.dataViz.sysPerf.db.refresh')}
        </button>
        <span className="app-text-caption text-app-ink/45">
          {t('ai.dataViz.sysPerf.db.hint')}
        </span>
      </div>
      {notice ? (
        <div className="mb-3">
          <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
        </div>
      ) : null}
      <div className="custom-scrollbar overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-app-border">
              {DB_COLS.map((c) => (
                <th
                  key={c.key}
                  className="app-text-caption whitespace-nowrap px-2 py-1.5 text-left font-medium text-app-ink/65"
                >
                  {t(`ai.dataViz.sysPerf.db.columns.${c.labelKey}`)}
                </th>
              ))}
              <th className="app-text-caption whitespace-nowrap px-2 py-1.5 text-right font-medium text-app-ink/65">
                {t('ai.dataViz.sysPerf.db.columns.rowCount')}
              </th>
              <th className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                className="border-b border-app-border [border-bottom-style:dashed]"
              >
                {DB_COLS.map((c) => (
                  <td
                    key={c.key}
                    className={cn(
                      'whitespace-nowrap px-2 py-1',
                      c.key === 'filename'
                        ? 'app-text-body-sm text-app-ink'
                        : c.key === 'id'
                          ? 'app-text-caption text-center font-bold text-app-ink/75'
                          : 'app-text-caption text-app-ink/75',
                    )}
                  >
                    {String(r[c.key] ?? '')}
                  </td>
                ))}
                <td className="app-text-caption whitespace-nowrap px-2 py-1 text-right text-app-ink/65 tabular-nums">
                  {(r.row_count || 0).toLocaleString()}
                </td>
                <td className="px-2 py-1">
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      title={t('ai.dataViz.sysPerf.db.downloadCsv')}
                      onClick={() => onDownload(r.id, r.filename)}
                      className="rounded p-1 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-app-accent"
                    >
                      <Download size={15} />
                    </button>
                    <button
                      type="button"
                      title={t('ai.dataViz.sysPerf.db.delete')}
                      onClick={() => onDelete(r.id)}
                      className="rounded p-1 text-app-ink/55 transition-colors hover:bg-app-surface-hover hover:text-ui-danger"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
