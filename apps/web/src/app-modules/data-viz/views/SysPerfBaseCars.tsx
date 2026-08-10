import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { InlineNotice, Select, useConfirm } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import {
  SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
  SYS_PERF_BASE_CAR_BRANDS,
  SYS_PERF_BASE_CAR_BRAND_OPTIONS,
  SYS_PERF_BASE_CAR_ERA_OPTIONS,
  SYS_PERF_BASE_CAR_TABLE_HEADER_KEYS,
  buildSysPerfBaseCarSegments,
  createEmptySysPerfBaseCarDraft,
  filterSysPerfBaseCars,
  sysPerfBaseCarBrandLabelKey,
  updateSysPerfBaseCarDraft,
  type SysPerfBaseCarDraft,
} from './sysperf-base-cars';
import {
  deleteSysPerfBaseCarModel,
  isSysPerfBaseCarDraftSubmittable,
  loadSysPerfBaseCarModels,
  saveSysPerfBaseCarModel,
  type SysPerfCarModel,
} from './sysperf-base-cars-loader';
import { formatSysPerfErrorMessage, type SysPerfNotice } from './sysperf-error';
import { useSysPerfWorkspace } from './sysperf-workspace';
import { SYSPERF_BASE_CAR_BADGE_COLORS } from './data-viz-colors';

function carBrandStyle(brand: string): CSSProperties {
  if (brand === SYS_PERF_BASE_CAR_BRANDS.hyundai)
    return SYSPERF_BASE_CAR_BADGE_COLORS.hyundai;
  if (brand === SYS_PERF_BASE_CAR_BRANDS.kia)
    return SYSPERF_BASE_CAR_BADGE_COLORS.kia;
  return SYSPERF_BASE_CAR_BADGE_COLORS.defaultBrand;
}

function carEraStyle(era: string): CSSProperties {
  return era === '1'
    ? SYSPERF_BASE_CAR_BADGE_COLORS.firstEra
    : SYSPERF_BASE_CAR_BADGE_COLORS.secondEra;
}

function Badge({
  children,
  style,
}: {
  children: ReactNode;
  style: CSSProperties;
}) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '3px 12px',
        borderRadius: 20,
        fontWeight: 700,
        fontSize: 12,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

export function SysPerfBaseCars() {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const { confirm, confirmDialog } = useConfirm();
  const [rows, setRows] = useState<SysPerfCarModel[]>([]);
  const [q, setQ] = useState('');
  const [fBrand, setFBrand] = useState(SYS_PERF_BASE_CARS_ALL_FILTER_VALUE);
  const [fEra, setFEra] = useState(SYS_PERF_BASE_CARS_ALL_FILTER_VALUE);
  const [fSeg, setFSeg] = useState(SYS_PERF_BASE_CARS_ALL_FILTER_VALUE);
  const [draft, setDraft] = useState<SysPerfBaseCarDraft>(
    createEmptySysPerfBaseCarDraft,
  );
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<SysPerfNotice | null>(null);

  const load = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    try {
      const nextRows = await loadSysPerfBaseCarModels({ token, workspaceSlug });
      setRows(nextRows);
      setNotice(null);
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseCars.loadFailed'),
        ),
      });
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const segments = useMemo(() => buildSysPerfBaseCarSegments(rows), [rows]);
  const filtered = useMemo(
    () =>
      filterSysPerfBaseCars({
        rows,
        filter: {
          query: q,
          brand: fBrand,
          era: fEra,
          segment: fSeg,
        },
      }),
    [rows, q, fBrand, fEra, fSeg],
  );
  const brandOptions = useMemo(
    () => [
      {
        value: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
        label: t('ai.dataViz.sysPerf.baseCars.filters.allBrands'),
      },
      ...SYS_PERF_BASE_CAR_BRAND_OPTIONS.map((item) => ({
        value: item.value,
        label: t(`ai.dataViz.sysPerf.baseCars.brands.${item.labelKey}`),
      })),
    ],
    [t],
  );
  const draftBrandOptions = useMemo(
    () =>
      SYS_PERF_BASE_CAR_BRAND_OPTIONS.map((item) => ({
        value: item.value,
        label: t(`ai.dataViz.sysPerf.baseCars.brands.${item.labelKey}`),
      })),
    [t],
  );
  const eraOptions = useMemo(
    () => [
      {
        value: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
        label: t('ai.dataViz.sysPerf.baseCars.filters.allEras'),
      },
      ...SYS_PERF_BASE_CAR_ERA_OPTIONS.map((item) => ({
        value: item.value,
        label: t(`ai.dataViz.sysPerf.baseCars.eras.${item.labelKey}`),
      })),
    ],
    [t],
  );
  const draftEraOptions = useMemo(
    () =>
      SYS_PERF_BASE_CAR_ERA_OPTIONS.map((item) => ({
        value: item.value,
        label: t(`ai.dataViz.sysPerf.baseCars.eras.${item.labelKey}`),
      })),
    [t],
  );
  const segmentOptions = useMemo(
    () => [
      {
        value: SYS_PERF_BASE_CARS_ALL_FILTER_VALUE,
        label: t('ai.dataViz.sysPerf.baseCars.filters.allSegments'),
      },
      ...segments.map((segment) => ({ value: segment, label: segment })),
    ],
    [segments, t],
  );

  const onAdd = async () => {
    if (!token || !workspaceSlug || !isSysPerfBaseCarDraftSubmittable(draft)) {
      return;
    }
    setAdding(true);
    setNotice(null);
    try {
      await saveSysPerfBaseCarModel({ token, workspaceSlug, draft });
      setDraft(createEmptySysPerfBaseCarDraft());
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseCars.saveFailed'),
        ),
      });
    } finally {
      setAdding(false);
    }
  };

  const onDelete = async (id: number) => {
    if (!token || !workspaceSlug) return;
    const ok = await confirm({
      title: t('ai.dataViz.sysPerf.baseCars.deleteConfirmTitle'),
      description: t('ai.dataViz.sysPerf.baseCars.deleteConfirm'),
      confirmLabel: t('ai.dataViz.sysPerf.baseCars.deleteAction'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setNotice(null);
    try {
      await deleteSysPerfBaseCarModel({ token, workspaceSlug, modelId: id });
      await load();
    } catch (error) {
      setNotice({
        tone: 'danger',
        msg: formatSysPerfErrorMessage(
          error,
          t('ai.dataViz.sysPerf.baseCars.deleteFailed'),
        ),
      });
    }
  };

  const brandLabel = (brand: string) => {
    const labelKey = sysPerfBaseCarBrandLabelKey(brand);
    return labelKey
      ? t(`ai.dataViz.sysPerf.baseCars.brands.${labelKey}`)
      : brand;
  };
  const setDraftField = (field: keyof SysPerfBaseCarDraft, value: string) => {
    setDraft((prev) => updateSysPerfBaseCarDraft(prev, field, value));
  };

  const selCls =
    'app-text-body-sm rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent';

  return (
    <>
      {confirmDialog}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-app-border bg-app-surface-raised p-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('ai.dataViz.sysPerf.baseCars.searchPlaceholder')}
            className="app-text-body-sm min-w-[200px] flex-1 rounded-md border border-app-border bg-app-bg px-3 py-1.5 text-app-ink outline-none focus:border-app-accent"
          />
          <Select
            value={fBrand}
            onValueChange={setFBrand}
            options={brandOptions}
            className="min-w-[120px]"
          />
          <Select
            value={fEra}
            onValueChange={setFEra}
            options={eraOptions}
            className="min-w-[110px]"
          />
          <Select
            value={fSeg}
            onValueChange={setFSeg}
            options={segmentOptions}
            className="min-w-[140px]"
          />
          <span className="app-text-caption ml-auto font-semibold text-app-ink/55">
            {filtered.length !== rows.length
              ? t('ai.dataViz.sysPerf.baseCars.filteredCount', {
                  filtered: filtered.length,
                  total: rows.length,
                })
              : t('ai.dataViz.sysPerf.baseCars.totalCount', {
                  count: filtered.length,
                })}
          </span>
        </div>
        {notice ? (
          <div className="mb-3">
            <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
          </div>
        ) : null}

        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
          <Select
            value={draft.brand}
            onValueChange={(value) => setDraftField('brand', value)}
            options={draftBrandOptions}
            className="w-full"
          />
          <Select
            value={draft.era}
            onValueChange={(value) => setDraftField('era', value)}
            options={draftEraOptions}
            className="w-full"
          />
          <input
            value={draft.year}
            onChange={(e) => setDraftField('year', e.target.value)}
            placeholder={t('ai.dataViz.sysPerf.baseCars.placeholders.year')}
            className={selCls}
          />
          <input
            value={draft.car_name}
            onChange={(e) => setDraftField('car_name', e.target.value)}
            placeholder={t('ai.dataViz.sysPerf.baseCars.placeholders.carName')}
            className={selCls}
          />
          <input
            value={draft.model_code}
            onChange={(e) => setDraftField('model_code', e.target.value)}
            placeholder={t(
              'ai.dataViz.sysPerf.baseCars.placeholders.modelCode',
            )}
            className={selCls}
          />
          <input
            value={draft.segment_code}
            onChange={(e) => setDraftField('segment_code', e.target.value)}
            placeholder={t(
              'ai.dataViz.sysPerf.baseCars.placeholders.segmentCode',
            )}
            className={selCls}
          />
          <input
            value={draft.segment_name}
            onChange={(e) => setDraftField('segment_name', e.target.value)}
            placeholder={t(
              'ai.dataViz.sysPerf.baseCars.placeholders.segmentName',
            )}
            className={selCls}
          />
          <button
            type="button"
            disabled={adding}
            onClick={onAdd}
            className="app-text-control-sm inline-flex items-center justify-center gap-1 rounded-md bg-app-accent px-2.5 py-1.5 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {adding ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Plus size={14} />
            )}
            {t('ai.dataViz.sysPerf.baseCars.addAction')}
          </button>
        </div>

        <div className="custom-scrollbar max-h-[68vh] overflow-auto rounded-lg border border-app-border">
          <table
            className="w-full border-collapse"
            style={{ tableLayout: 'fixed' }}
          >
            <colgroup>
              <col style={{ width: 60 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 60 }} />
              <col />
              <col style={{ width: 110 }} />
              <col style={{ width: 70 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 44 }} />
            </colgroup>
            <thead className="sticky top-0 bg-app-surface-raised">
              <tr>
                {SYS_PERF_BASE_CAR_TABLE_HEADER_KEYS.map((h, index) => (
                  <th
                    key={h}
                    className="app-text-caption border-b-2 border-app-border px-2 py-2 font-medium text-app-ink/65"
                    style={{
                      textAlign: index === 3 || index === 6 ? 'left' : 'center',
                    }}
                  >
                    {h === 'actions'
                      ? ''
                      : t(`ai.dataViz.sysPerf.baseCars.headers.${h}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <tr
                  key={row.id}
                  className={cn(
                    'border-b border-app-border',
                    index % 2 === 1 ? 'bg-app-bg/40' : '',
                  )}
                >
                  <td className="px-2 py-1.5 text-center">
                    <Badge style={carEraStyle(row.era)}>
                      {t('ai.dataViz.sysPerf.baseCars.eraValue', {
                        era: row.era,
                      })}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <Badge style={carBrandStyle(row.brand)}>
                      {brandLabel(row.brand)}
                    </Badge>
                  </td>
                  <td className="app-text-caption px-2 py-1.5 text-center text-app-ink/65">
                    {row.year}
                  </td>
                  <td className="app-text-body-sm px-2 py-1.5 font-semibold text-app-ink">
                    {row.car_name}
                  </td>
                  <td className="app-text-caption px-2 py-1.5 text-center font-mono text-app-ink/55">
                    {row.model_code}
                  </td>
                  <td className="app-text-caption px-2 py-1.5 text-center text-app-ink/65">
                    {row.segment_code}
                  </td>
                  <td className="app-text-caption px-2 py-1.5 text-app-ink/65">
                    {row.segment_name}
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => onDelete(row.id)}
                      title={t('ai.dataViz.sysPerf.baseCars.deleteAction')}
                      className="rounded p-1 text-app-ink/40 transition-colors hover:bg-app-surface-hover hover:text-ui-danger"
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
    </>
  );
}
