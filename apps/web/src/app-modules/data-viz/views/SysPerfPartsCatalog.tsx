import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { InlineNotice, useConfirm } from '@ai-do/ui';

import {
  COMP_DRIVE_LABELS,
  COMP_SUBS,
  NONE_OPTION,
  PART_CAT_LABELS,
  PART_CAT_ORDER,
  type CatalogItem,
  partItems,
  rebuildPartCatalog,
} from './sysperf-parts';
import {
  deleteSysPerfPartsCatalogItem,
  isSysPerfPartsCatalogNameSubmittable,
  loadSysPerfPartsCatalogRows,
  saveSysPerfPartsCatalogItem,
  type SysPerfPartsCatalogItem,
} from './sysperf-parts-catalog-loader';
import { formatSysPerfErrorMessage, type SysPerfNotice } from './sysperf-error';
import { useSysPerfWorkspace } from './sysperf-workspace';
import { SYSPERF_PARTS_CATALOG_COLORS } from './data-viz-colors';

export function SysPerfPartsCatalog() {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const { confirm, confirmDialog } = useConfirm();
  const [rows, setRows] = useState<SysPerfPartsCatalogItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<SysPerfNotice | null>(null);

  const load = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setBusy(true);
    try {
      const nextRows = await loadSysPerfPartsCatalogRows({
        token,
        workspaceSlug,
      });
      setRows(nextRows);
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.parts.loadFailed'),
        ),
      });
    } finally {
      setBusy(false);
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const tree = useMemo(() => rebuildPartCatalog(rows), [rows]);

  const add = async (
    category: string,
    drive_type: string,
    sub_type: string,
    key: string,
  ) => {
    if (!token || !workspaceSlug) return;
    const name = drafts[key] || '';
    if (!isSysPerfPartsCatalogNameSubmittable(name)) return;
    setNotice(null);
    try {
      const r = await saveSysPerfPartsCatalogItem({
        token,
        workspaceSlug,
        draft: {
          category,
          drive_type,
          sub_type,
          name,
        },
      });
      if (r.status !== 'ok') return;
      setDrafts((d) => ({ ...d, [key]: '' }));
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.parts.saveFailed'),
        ),
      });
    }
  };

  const del = async (id: number) => {
    if (!token || !workspaceSlug) return;
    const ok = await confirm({
      title: t('ai.dataViz.sysPerf.parts.deleteConfirmTitle'),
      description: t('ai.dataViz.sysPerf.parts.deleteConfirm'),
      confirmLabel: t('ai.dataViz.sysPerf.parts.deleteAction'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setNotice(null);
    try {
      await deleteSysPerfPartsCatalogItem({ token, workspaceSlug, id });
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.parts.deleteFailed'),
        ),
      });
    }
  };

  // Keep this as a JSX-returning helper, not an inner component. Making it a
  // component type remounts every input keystroke and drops focus.
  const catChip = (item: CatalogItem) => (
    <span
      key={item.id}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '4px 4px 4px 10px',
        background: SYSPERF_PARTS_CATALOG_COLORS.chipBg,
        color: SYSPERF_PARTS_CATALOG_COLORS.chipText,
        border: SYSPERF_PARTS_CATALOG_COLORS.chipBorder,
        borderRadius: 14,
        fontSize: 13,
        fontWeight: 600,
      }}
    >
      {item.name}
      <button
        type="button"
        onClick={() => del(item.id)}
        title={t('ai.dataViz.sysPerf.parts.deleteAction')}
        style={{
          background: 'none',
          border: 'none',
          color: SYSPERF_PARTS_CATALOG_COLORS.deleteText,
          fontWeight: 700,
          fontSize: 14,
          cursor: 'pointer',
          padding: '0 4px',
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </span>
  );

  const newInput = (ckey: string) => (
    <input
      key={`new-${ckey}`}
      type="text"
      value={drafts[ckey] || ''}
      onChange={(e) => setDrafts((d) => ({ ...d, [ckey]: e.target.value }))}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const [category, drive_type = '', sub_type = ''] = ckey.split('|');
          void add(category, drive_type, sub_type, ckey);
        }
      }}
      placeholder={t('ai.dataViz.sysPerf.parts.namePlaceholder')}
      className="app-text-caption rounded-md border border-app-border bg-app-bg px-2.5 py-1.5 text-app-ink outline-none focus:border-app-accent"
      style={{ minWidth: 160 }}
    />
  );

  return (
    <>
      {confirmDialog}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="app-text-body-sm mb-3 flex items-center gap-2 font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.parts.catalogTitle')}
          {busy ? (
            <Loader2 size={14} className="animate-spin text-app-accent" />
          ) : null}
        </div>
        {notice ? (
          <div className="mb-3">
            <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
          </div>
        ) : null}
        <div className="flex flex-col gap-3">
          {PART_CAT_ORDER.map((c) => (
            <div
              key={c}
              className="overflow-hidden rounded-xl border border-app-border"
            >
              <div className="app-text-body-sm bg-app-surface-raised px-3.5 py-2.5 font-semibold text-app-ink">
                {PART_CAT_LABELS[c]}
              </div>
              {c === 'comp' ? (
                <div className="flex flex-col gap-2.5 p-3">
                  {(['belt', 'electric'] as const).map((dt) => (
                    <div
                      key={dt}
                      className="rounded-lg border border-app-border bg-app-bg p-3"
                    >
                      <div
                        className="app-text-caption mb-2 font-bold"
                        style={{ color: SYSPERF_PARTS_CATALOG_COLORS.chipText }}
                      >
                        {COMP_DRIVE_LABELS[dt]}
                      </div>
                      <div className="flex flex-col gap-2">
                        {COMP_SUBS[dt].map((st) => {
                          const ckey = `comp|${dt}|${st}`;
                          const list = tree.comp[dt]?.[st] || [];
                          return (
                            <div
                              key={st}
                              className="flex items-start gap-2.5 py-1"
                            >
                              <span className="app-text-caption w-20 shrink-0 pt-1.5 font-bold text-app-ink/75">
                                {st}
                              </span>
                              <div className="flex flex-1 flex-wrap items-center gap-1.5">
                                {list.map((it) => catChip(it))}
                                {newInput(ckey)}
                                <button
                                  type="button"
                                  onClick={() => add('comp', dt, st, ckey)}
                                  className="app-text-caption rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink/80 hover:bg-app-surface-hover"
                                >
                                  {t('ai.dataViz.sysPerf.parts.addAction')}
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-1.5 p-3">
                  <span
                    title={t('ai.dataViz.sysPerf.parts.noneHint')}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '4px 10px',
                      background: SYSPERF_PARTS_CATALOG_COLORS.noneBg,
                      color: SYSPERF_PARTS_CATALOG_COLORS.noneText,
                      border: SYSPERF_PARTS_CATALOG_COLORS.noneBorder,
                      borderRadius: 14,
                      fontSize: 13,
                      fontStyle: 'italic',
                    }}
                  >
                    {NONE_OPTION}
                  </span>
                  {partItems(tree, c).map((it) => catChip(it))}
                  {newInput(c)}
                  <button
                    type="button"
                    onClick={() => add(c, '', '', c)}
                    className="app-text-caption rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink/80 hover:bg-app-surface-hover"
                  >
                    {t('ai.dataViz.sysPerf.parts.addAction')}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
