import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { InlineNotice } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import { type SysPerfUploadedFile } from '../api/dataviz-api';
import { SysPerfPartsSelect } from './SysPerfPartsUI';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import { type PartCatalogTree } from './sysperf-parts';
import type { PartSel, PartsState } from './sysperf-parts-state';
import {
  EMPTY_FILE_INFO,
  type CommonInfo,
  type FileInfo,
} from './sysperf-testinfo';
import {
  loadSysPerfTestInfoPartsCatalog,
  saveSysPerfTestInfo,
} from './sysperf-testinfo-loader';
import { useSysPerfWorkspace } from './sysperf-workspace';

// 원본 sys_perf.js showTestInfoConfirm() — 공통 + 파일별(탭) 시험정보 + 부품사양.
// 상태는 패널이 보유(controlled). "시험정보 확인 완료" → /test-info. (DB화는 데이터 표 탭으로 이동.)

const COMMON_FIELDS: Array<[keyof CommonInfo, string, string]> = [
  ['car_code', 'carCode', ''],
  ['car_type', 'carType', 'ICE(GSL,DSL,LPG), HEV, EV'],
  ['engine', 'engine', 'Kappa, Gamma etc.'],
  ['stage', 'stage', 'P1, P2, MP etc.'],
  ['car_number', 'carNumber', ''],
];
const FILE_FIELDS: Array<[keyof FileInfo, string]> = [
  ['test_item', 'testItem'],
  ['test_date', 'testDate'],
  ['refrigerant_charge', 'refrigerantCharge'],
  ['lot_no', 'lotNo'],
];

export function SysPerfTestInfo({
  files,
  common,
  setCommon,
  perFile,
  setPerFile,
  parts,
  setParts,
}: {
  files: SysPerfUploadedFile[];
  common: CommonInfo;
  setCommon: React.Dispatch<React.SetStateAction<CommonInfo>>;
  perFile: Record<number, FileInfo>;
  setPerFile: React.Dispatch<React.SetStateAction<Record<number, FileInfo>>>;
  parts: Record<number, PartsState>;
  setParts: React.Dispatch<React.SetStateAction<Record<number, PartsState>>>;
}) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();
  const valid = useMemo(
    () => files.filter(isUsableSysPerfUploadedFile),
    [files],
  );

  const [activeIdx, setActiveIdx] = useState(0);
  const [catalog, setCatalog] = useState<PartCatalogTree | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{
    tone: 'success' | 'danger';
    msg: string;
  } | null>(null);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    void loadSysPerfTestInfoPartsCatalog({ token, workspaceSlug }).then(
      setCatalog,
    );
  }, [token, workspaceSlug]);

  const setFileField = (fid: number, k: keyof FileInfo, v: string) =>
    setPerFile((p) => ({
      ...p,
      [fid]: { ...(p[fid] || EMPTY_FILE_INFO), [k]: v },
    }));
  const onPartChange = (
    fid: number,
    partKey: string,
    patch: Partial<PartSel>,
  ) =>
    setParts((p) => ({
      ...p,
      [fid]: { ...p[fid], [partKey]: { ...p[fid][partKey], ...patch } },
    }));

  const onConfirmInfo = async () => {
    if (!token || !workspaceSlug || !valid.length) return;
    setBusy(true);
    setNotice(null);
    try {
      await saveSysPerfTestInfo({
        token,
        workspaceSlug,
        files: valid,
        common,
        perFile,
      });
      setNotice({
        tone: 'success',
        msg: t('ai.dataViz.sysPerf.testInfo.saveComplete'),
      });
    } catch (e) {
      setNotice({
        tone: 'danger',
        msg:
          e instanceof Error
            ? e.message
            : t('ai.dataViz.sysPerf.testInfo.saveFailed'),
      });
    } finally {
      setBusy(false);
    }
  };

  if (!valid.length) return null;
  const inputCls =
    'app-text-body-sm w-full rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent';

  return (
    <div className="flex flex-col gap-3">
      {/* 공통 시험정보 */}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="app-text-body-sm mb-3 font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.testInfo.commonTitle')}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {COMMON_FIELDS.map(([k, labelKey, ph]) => (
            <label key={k} className="flex flex-col gap-1">
              <span className="app-text-caption text-app-ink/65">
                {t(`ai.dataViz.sysPerf.testInfo.fields.${labelKey}`)}
              </span>
              <input
                value={common[k]}
                placeholder={ph}
                onChange={(e) =>
                  setCommon((c) => ({ ...c, [k]: e.target.value }))
                }
                className={inputCls}
              />
            </label>
          ))}
        </div>
      </div>

      {/* 파일별 시험정보 + 부품사양 */}
      <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
        <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
          {t('ai.dataViz.sysPerf.testInfo.perFileTitle')}
        </div>
        {valid.length > 1 ? (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {valid.map((f, i) => (
              <button
                key={f.file_id}
                type="button"
                title={f.filename}
                onClick={() => setActiveIdx(i)}
                className={cn(
                  'app-text-control-sm rounded-md border px-3 py-1.5 font-semibold transition-colors',
                  activeIdx === i
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
                )}
              >
                {t('ai.dataViz.sysPerf.fileTab', { index: i + 1 })}
              </button>
            ))}
          </div>
        ) : null}

        {valid.map((f, i) => {
          if (i !== activeIdx) return null;
          const fid = f.file_id;
          const fi = perFile[fid] || EMPTY_FILE_INFO;
          return (
            <div key={fid}>
              {f.sheets?.[0]?.info_text ? (
                <div className="app-text-caption mb-3 line-clamp-2 text-app-ink/45">
                  {f.sheets[0].info_text}
                </div>
              ) : null}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {FILE_FIELDS.map(([k, labelKey]) => (
                  <label key={k} className="flex flex-col gap-1">
                    <span className="app-text-caption text-app-ink/65">
                      {t(`ai.dataViz.sysPerf.testInfo.fields.${labelKey}`)}
                    </span>
                    <input
                      value={fi[k]}
                      onChange={(e) => setFileField(fid, k, e.target.value)}
                      className={inputCls}
                    />
                  </label>
                ))}
              </div>

              <div className="mt-4 border-t border-app-border pt-3 [border-top-style:dashed]">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <div className="app-text-body-sm font-semibold text-app-ink">
                    {t('ai.dataViz.sysPerf.testInfo.partsTitle', {
                      index: i + 1,
                    })}
                  </div>
                  <div className="app-text-caption rounded-md border border-ui-warning/50 bg-ui-warning/10 px-2.5 py-1 font-medium text-ui-warning">
                    {t('ai.dataViz.sysPerf.testInfo.partsMissingHint')}
                  </div>
                </div>
                {catalog && parts[fid] ? (
                  <SysPerfPartsSelect
                    catalog={catalog}
                    value={parts[fid]}
                    onChange={(partKey, patch) =>
                      onPartChange(fid, partKey, patch)
                    }
                  />
                ) : (
                  <div className="grid place-items-center py-6">
                    <Loader2
                      size={18}
                      className="animate-spin text-app-accent"
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onConfirmInfo}
            className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : null}
            {t('ai.dataViz.sysPerf.testInfo.confirm')}
          </button>
          <span className="app-text-caption text-app-ink/55">
            {t('ai.dataViz.sysPerf.testInfo.dbHint')}
          </span>
        </div>
        {notice ? (
          <div className="mt-3">
            <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
          </div>
        ) : null}
      </div>
    </div>
  );
}
