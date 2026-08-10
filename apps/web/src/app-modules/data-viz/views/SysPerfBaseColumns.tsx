import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { InlineNotice } from '@ai-do/ui';

import {
  deleteSysPerfBaseColumn,
  isSysPerfBaseColumnDraftSubmittable,
  loadSysPerfBaseColumns,
  saveSysPerfBaseColumn,
  type SysPerfBaseColumnDraft,
  type SysPerfStandardColumn,
} from './sysperf-base-columns-loader';
import { formatSysPerfErrorMessage, type SysPerfNotice } from './sysperf-error';
import { useSysPerfWorkspace } from './sysperf-workspace';

const BASE_COLUMN_HEADER_KEYS = [
  'standardName',
  'keywords',
  'unit',
  'category',
  'actions',
] as const;

export function SysPerfBaseColumns() {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const [rows, setRows] = useState<SysPerfStandardColumn[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<SysPerfNotice | null>(null);
  const [draft, setDraft] = useState<SysPerfBaseColumnDraft>({
    standard_name: '',
    keywords: '',
    unit: '',
    category: 'general',
  });

  const load = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setBusy(true);
    try {
      const nextRows = await loadSysPerfBaseColumns({ token, workspaceSlug });
      setRows(nextRows);
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseColumns.loadFailed'),
        ),
      });
    } finally {
      setBusy(false);
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const onAdd = async () => {
    if (
      !token ||
      !workspaceSlug ||
      !isSysPerfBaseColumnDraftSubmittable(draft)
    ) {
      return;
    }
    setNotice(null);
    try {
      await saveSysPerfBaseColumn({
        token,
        workspaceSlug,
        draft,
      });
      setDraft({
        standard_name: '',
        keywords: '',
        unit: '',
        category: 'general',
      });
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseColumns.saveFailed'),
        ),
      });
    }
  };

  const onDelete = async (id: number) => {
    if (!token || !workspaceSlug) return;
    setNotice(null);
    try {
      await deleteSysPerfBaseColumn({ token, workspaceSlug, columnId: id });
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseColumns.deleteFailed'),
        ),
      });
    }
  };

  return (
    <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <div className="app-text-body-sm mb-3 flex items-center gap-2 font-semibold text-app-ink">
        {t('ai.dataViz.sysPerf.baseColumns.title', { count: rows.length })}
        {busy ? (
          <Loader2 size={14} className="animate-spin text-app-accent" />
        ) : null}
      </div>
      {notice ? (
        <div className="mb-3">
          <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
        </div>
      ) : null}
      <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-4">
        <input
          value={draft.standard_name}
          onChange={(e) =>
            setDraft((p) => ({ ...p, standard_name: e.target.value }))
          }
          placeholder={t(
            'ai.dataViz.sysPerf.baseColumns.standardNamePlaceholder',
          )}
          className="app-text-body-sm rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent"
        />
        <input
          value={draft.keywords}
          onChange={(e) =>
            setDraft((p) => ({ ...p, keywords: e.target.value }))
          }
          placeholder={t('ai.dataViz.sysPerf.baseColumns.keywordsPlaceholder')}
          className="app-text-body-sm rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent sm:col-span-2"
        />
        <div className="flex gap-2">
          <input
            value={draft.unit}
            onChange={(e) => setDraft((p) => ({ ...p, unit: e.target.value }))}
            placeholder={t('ai.dataViz.sysPerf.baseColumns.unitPlaceholder')}
            className="app-text-body-sm w-full rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent"
          />
          <button
            type="button"
            aria-label={t('ai.dataViz.sysPerf.baseColumns.addAction')}
            title={t('ai.dataViz.sysPerf.baseColumns.addAction')}
            onClick={onAdd}
            className="app-text-control-sm inline-flex shrink-0 items-center gap-1 rounded-md bg-app-accent px-2.5 py-1.5 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
      <div className="custom-scrollbar max-h-[460px] overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 bg-app-surface">
            <tr className="border-b border-app-border">
              {BASE_COLUMN_HEADER_KEYS.map((h) => (
                <th
                  key={h}
                  className="app-text-caption px-2 py-1.5 text-left font-medium text-app-ink/65"
                >
                  {h === 'actions'
                    ? ''
                    : t(`ai.dataViz.sysPerf.baseColumns.headers.${h}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                className="border-b border-app-border [border-bottom-style:dashed]"
              >
                <td className="app-text-body-sm px-2 py-1 text-app-ink">
                  {r.standard_name}
                </td>
                <td className="app-text-caption px-2 py-1 text-app-ink/65">
                  {r.keywords}
                </td>
                <td className="app-text-caption px-2 py-1 text-app-ink/75">
                  {r.unit}
                </td>
                <td className="app-text-caption px-2 py-1 text-app-ink/55">
                  {r.category}
                </td>
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    aria-label={t(
                      'ai.dataViz.sysPerf.baseColumns.deleteAction',
                    )}
                    title={t('ai.dataViz.sysPerf.baseColumns.deleteAction')}
                    onClick={() => onDelete(r.id)}
                    className="rounded p-1 text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-ui-danger"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
