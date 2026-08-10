import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Database, Loader2 } from 'lucide-react';
import { EmptyState, InlineNotice, useConfirm } from '@ai-do/ui';

import type { PartsState } from './sysperf-parts-state';
import {
  loadSysPerfSheetPreview,
  saveSysPerfTableDb,
} from './sysperf-table-loader';
import {
  buildSysPerfSheetPreviewRows,
  type SysPerfSheetPreview,
} from './sysperf-table-preview';
import { type CommonInfo, type FileInfo } from './sysperf-testinfo';
import { useSysPerfWorkspace } from './sysperf-workspace';

interface SysPerfDataTableTabProps {
  fileId: number | null;
  sheet: string;
  fileName?: string;
  common: CommonInfo;
  perFile: Record<number, FileInfo>;
  parts: Record<number, PartsState>;
}

interface DbSaveMessage {
  tone: 'success' | 'danger';
  msg: string;
}

export function SysPerfDataTableTab({
  fileId,
  sheet,
  fileName,
  common,
  perFile,
  parts,
}: SysPerfDataTableTabProps) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const { confirm, confirmDialog } = useConfirm();
  const [data, setData] = useState<SysPerfSheetPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dbBusy, setDbBusy] = useState(false);
  const [dbMsg, setDbMsg] = useState<DbSaveMessage | null>(null);

  const onDbSave = async () => {
    if (!token || !workspaceSlug || fileId == null) return;
    const ok = await confirm({
      title: t('ai.dataViz.sysPerf.table.dbSaveTitle'),
      description: t('ai.dataViz.sysPerf.table.dbSaveConfirm'),
      confirmLabel: t('ai.dataViz.sysPerf.table.saveButton'),
      cancelLabel: t('common:actions.cancel'),
    });
    if (!ok) return;
    setDbBusy(true);
    setDbMsg(null);
    try {
      const r = await saveSysPerfTableDb({
        token,
        workspaceSlug,
        fileId,
        sheet,
        common,
        perFile,
        parts,
      });
      setDbMsg({
        tone: 'success',
        msg: t('ai.dataViz.sysPerf.table.saveComplete', {
          testId: r.test_id,
          rowCount: r.row_count.toLocaleString(),
          colCount: r.col_count,
          csv: r.csv,
        }),
      });
    } catch (e) {
      setDbMsg({
        tone: 'danger',
        msg:
          e instanceof Error
            ? e.message
            : t('ai.dataViz.sysPerf.table.networkError'),
      });
    } finally {
      setDbBusy(false);
    }
  };

  useEffect(() => {
    if (!token || !workspaceSlug || fileId == null) return;
    let cancel = false;
    (async () => {
      setBusy(true);
      setErr(null);
      const result = await loadSysPerfSheetPreview({
        token,
        workspaceSlug,
        fileId,
        sheet,
        fallbackError: t('ai.dataViz.sysPerf.table.loadFailed'),
      });
      if (cancel) return;
      setErr(result.error);
      setData(result.preview);
      setBusy(false);
    })();
    return () => {
      cancel = true;
    };
  }, [token, workspaceSlug, fileId, sheet, t]);

  if (fileId == null) {
    return <EmptyState title={t('ai.dataViz.sysPerf.table.emptySelection')} />;
  }
  if (busy) {
    return (
      <div className="grid place-items-center py-16">
        <Loader2 size={20} className="animate-spin text-app-accent" />
      </div>
    );
  }
  if (err) return <InlineNotice tone="danger">{err}</InlineNotice>;
  if (!data)
    return <EmptyState title={t('ai.dataViz.sysPerf.table.emptyData')} />;

  const previewRows = buildSysPerfSheetPreviewRows(data);

  return (
    <>
      {confirmDialog}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="app-text-body-sm font-semibold text-app-ink">
            {fileName} / {sheet}
            <span className="app-text-caption ml-2 text-app-ink/45">
              {t('ai.dataViz.sysPerf.table.rowSummary', {
                total: data.total_rows.toLocaleString(),
                shown: previewRows.length.toLocaleString(),
              })}
            </span>
          </div>
          <button
            type="button"
            disabled={dbBusy}
            onClick={onDbSave}
            className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {dbBusy ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Database size={14} />
            )}
            {t('ai.dataViz.sysPerf.table.saveButton')}
          </button>
        </div>
        {dbMsg ? (
          <div className="mb-3">
            <InlineNotice tone={dbMsg.tone}>{dbMsg.msg}</InlineNotice>
          </div>
        ) : null}
        <div className="custom-scrollbar max-h-[600px] overflow-auto">
          <table className="border-collapse">
            <thead className="sticky top-0 bg-app-surface">
              <tr className="border-b border-app-border">
                <th className="app-text-caption px-2 py-1.5 text-right font-medium text-app-ink/45">
                  #
                </th>
                {data.columns.map((c) => (
                  <th
                    key={c}
                    className="app-text-caption whitespace-nowrap px-2 py-1.5 text-right font-medium text-app-ink/65"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row) => (
                <tr
                  key={row.index}
                  className="border-b border-app-border [border-bottom-style:dashed]"
                >
                  <td className="app-text-caption px-2 py-1 text-right text-app-ink/45 tabular-nums">
                    {row.index}
                  </td>
                  {row.cells.map((cell) => (
                    <td
                      key={cell.column}
                      className="app-text-caption whitespace-nowrap px-2 py-1 text-right text-app-ink tabular-nums"
                    >
                      {cell.value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
