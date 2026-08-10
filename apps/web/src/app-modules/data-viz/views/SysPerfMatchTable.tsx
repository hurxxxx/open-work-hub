import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, RefreshCw, Repeat2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { InlineNotice } from '@ai-do/ui';

import { type SysPerfUploadedFile } from '../api/dataviz-api';
import { MEASURE_ITEMS } from './sysperf-items';
import {
  applySysPerfRerunAutoMatch,
  buildInitialSysPerfMatchState,
  buildSysPerfConfirmPlan,
  buildSysPerfConfirmRequests,
  buildSysPerfConfirmWarningNotice,
  buildSysPerfItemCategoryMap,
  buildSysPerfMatchRows,
  collectHiddenSysPerfSubGroups,
  syncSysPerfMatchesFromFirstFile,
  toggleSysPerfAverageMode,
  type SysPerfAllMap,
  type SysPerfAvgMode,
  type SysPerfConfirmWarningNotice,
  type SysPerfFidMap,
  type SysPerfValueState,
} from './sysperf-match';
import {
  applyLoadedSysPerfMatchSheetDataProbesToState,
  areSysPerfFidMapsEqual,
  applySysPerfItemKeywordOverrides,
  confirmSysPerfMatchRequests,
  loadSysPerfItemKeywordOverrides,
  loadSysPerfMatchSheetDataProbePayload,
  type SysPerfMatchSheetDataProbePayload,
} from './sysperf-match-loader';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import { SysPerfMatchGrid } from './SysPerfMatchGrid';
import { useSysPerfWorkspace } from './sysperf-workspace';
import { SYSPERF_MATCH_TABLE_COLORS } from './data-viz-colors';

// 원본 sys_perf.js renderMatchArea() 의 역방향 그룹 매칭 테이블을 React 로 이식.
// 순수 매칭/확정 규칙은 sysperf-match.ts 에 두고, 여기서는 API 호출과 i18n/렌더링만 담당한다.
interface ConfirmModalState extends SysPerfConfirmWarningNotice {
  proceed: () => void;
}

const ITEM_CAT = buildSysPerfItemCategoryMap(MEASURE_ITEMS);

export function SysPerfMatchTable({
  files,
  onConfirmed,
}: {
  files: SysPerfUploadedFile[];
  onConfirmed?: () => void;
}) {
  const { t } = useTranslation('apps');
  const { token, workspaceSlug } = useSysPerfWorkspace();

  const validFiles = useMemo(
    () => files.filter(isUsableSysPerfUploadedFile),
    [files],
  );
  const nF = validFiles.length;

  // 파일별 헤더 / numeric 카운트
  const FH = useMemo<Record<number, string[]>>(() => {
    const out: Record<number, string[]> = {};
    validFiles.forEach((f) => {
      out[f.file_id] = f.sheets[0].headers ?? [];
    });
    return out;
  }, [validFiles]);
  const FNC = useMemo<Record<number, Record<string, number>>>(() => {
    const out: Record<number, Record<string, number>> = {};
    validFiles.forEach((f) => {
      out[f.file_id] = f.sheets[0].header_numeric_counts ?? {};
    });
    return out;
  }, [validFiles]);

  // ── 상태 (원본 autoMap / checked / alt / valueState / avgMode / collapsed) ──
  const [match, setMatch] = useState<SysPerfFidMap<string>>({});
  const [checked, setChecked] = useState<SysPerfFidMap<boolean>>({});
  const [valueState, setValueState] = useState<
    SysPerfFidMap<SysPerfValueState>
  >({});
  const [avgMode, setAvgMode] = useState<Record<number, SysPerfAvgMode>>({});
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [activeFid, setActiveFid] = useState<number | null>(null);
  const [targetTemp, setTargetTemp] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{
    tone: 'success' | 'warning' | 'danger';
    msg: string;
  } | null>(null);
  const [confirmModal, setConfirmModal] = useState<ConfirmModalState | null>(
    null,
  );
  const [probePayloads, setProbePayloads] = useState<
    Record<number, SysPerfMatchSheetDataProbePayload>
  >({});

  // ── 초기화: 자동매칭 + 체크 + avg 모드 ──
  useEffect(() => {
    if (!nF) return;
    const initial = buildInitialSysPerfMatchState({
      items: MEASURE_ITEMS,
      files: validFiles,
      headersByFileId: FH,
      numericCountsByFileId: FNC,
    });
    setMatch(initial.match);
    setChecked(initial.checked);
    setValueState(initial.valueState);
    setAvgMode(initial.avgMode);
    setCollapsed(new Set());
    setActiveFid(initial.activeFid);
    setNotice(null);
    setProbePayloads({});
  }, [FH, FNC, nF, validFiles]);

  // ── 데이터 유무 검사 payload 적재 (sheet-data max_rows=30) ──
  useEffect(() => {
    if (!token || !workspaceSlug || !nF) {
      setProbePayloads({});
      return;
    }
    let cancel = false;
    setProbePayloads({});
    validFiles.forEach((f) => {
      void loadSysPerfMatchSheetDataProbePayload({
        token,
        workspaceSlug,
        file: f,
      }).then((payload) => {
        if (cancel) return;
        setProbePayloads((prev) => ({ ...prev, [payload.fileId]: payload }));
      });
    });
    return () => {
      cancel = true;
    };
  }, [nF, token, workspaceSlug, validFiles]);

  // ── 적재된 payload를 최신 매칭 상태에 반영 ──
  useEffect(() => {
    const payloads = validFiles
      .map((file) => probePayloads[file.file_id])
      .filter(
        (payload): payload is SysPerfMatchSheetDataProbePayload => !!payload,
      );
    if (!payloads.length) return;
    const result = applyLoadedSysPerfMatchSheetDataProbesToState({
      items: MEASURE_ITEMS,
      match,
      valueState,
      checked,
      payloads,
    });
    if (!areSysPerfFidMapsEqual(valueState, result.valueState)) {
      setValueState(result.valueState);
    }
    if (!areSysPerfFidMapsEqual(checked, result.checked)) {
      setChecked(result.checked);
    }
  }, [checked, match, probePayloads, validFiles, valueState]);

  // ── 숨김(접힘) 계산 ──
  const hiddenSubgrps = useMemo(() => {
    return collectHiddenSysPerfSubGroups(MEASURE_ITEMS, collapsed);
  }, [collapsed]);
  const matchRows = useMemo(
    () =>
      buildSysPerfMatchRows({
        items: MEASURE_ITEMS,
        files: validFiles,
        activeFileId: activeFid,
        hiddenSubGroups: hiddenSubgrps,
        itemCategories: ITEM_CAT,
        match,
        checked,
        valueState,
        avgMode,
      }),
    [activeFid, avgMode, checked, hiddenSubgrps, match, validFiles, valueState],
  );

  // ── 핸들러 ──
  const onAltChange = (fid: number, n: number, v: string) => {
    setMatch((m) => ({ ...m, [fid]: { ...(m[fid] || {}), [n]: v } }));
    setChecked((c) => ({ ...c, [fid]: { ...(c[fid] || {}), [n]: !!v } }));
  };
  const onCheckChange = (fid: number, n: number, v: boolean) => {
    setChecked((c) => ({ ...c, [fid]: { ...(c[fid] || {}), [n]: v } }));
  };
  const onToggleCollapse = (grp: string) => {
    setCollapsed((s) => {
      const ns = new Set(s);
      if (ns.has(grp)) ns.delete(grp);
      else ns.add(grp);
      return ns;
    });
  };
  const onToggleAvgMode = (n: number) => {
    const result = toggleSysPerfAverageMode({
      files: validFiles,
      itemN: n,
      avgMode,
      checked,
      match,
    });
    setAvgMode(result.avgMode);
    setChecked(result.checked);
  };

  // ── 자동찾기 재실행 (BASE item-keywords 반영, 빈 항목만) ──
  const onRerun = async () => {
    if (!token || !workspaceSlug) return;
    const overrides = await loadSysPerfItemKeywordOverrides({
      token,
      workspaceSlug,
    });
    const items = applySysPerfItemKeywordOverrides(MEASURE_ITEMS, overrides);
    const result = applySysPerfRerunAutoMatch({
      items,
      files: validFiles,
      headersByFileId: FH,
      numericCountsByFileId: FNC,
      match,
      checked,
    });
    setMatch(result.match);
    setChecked(result.checked);
    setNotice({
      tone: 'success',
      msg: t('ai.dataViz.sysPerf.match.rerunComplete', { count: result.added }),
    });
  };

  // ── 항목매칭 통일 (1번 파일 → 나머지) ──
  const onSync = () => {
    if (nF < 2) return;
    const result = syncSysPerfMatchesFromFirstFile({
      items: MEASURE_ITEMS,
      files: validFiles,
      headersByFileId: FH,
      match,
      checked,
    });
    setMatch(result.match);
    setChecked(result.checked);
    setNotice({
      tone: 'success',
      msg: t('ai.dataViz.sysPerf.match.syncComplete', {
        copied: result.copied,
        skipped: result.skipped,
      }),
    });
  };

  // ── 매칭 확정 ──
  // confirm-match POST (파일별) — 경고 모달 통과 후 실행
  const doConfirm = async (
    m: SysPerfFidMap<string>,
    ck: SysPerfFidMap<boolean>,
    all: SysPerfAllMap,
  ) => {
    if (!token || !workspaceSlug) return;
    setConfirmModal(null);
    setBusy(true);
    setNotice(null);
    try {
      let total = 0;
      const perFile: string[] = [];
      const requests = buildSysPerfConfirmRequests({ files: validFiles, all });
      const results = await confirmSysPerfMatchRequests({
        token,
        workspaceSlug,
        requests,
      });
      for (const result of results) {
        total += result.count;
        perFile.push(
          t('ai.dataViz.sysPerf.match.fileMappingCount', {
            index: result.fileIndex + 1,
            count: result.count,
          }),
        );
      }
      setMatch(m);
      setChecked(ck);
      setNotice({
        tone: 'success',
        msg: t('ai.dataViz.sysPerf.match.confirmComplete', {
          files: perFile.join(' / '),
          total,
        }),
      });
      onConfirmed?.();
    } catch (e) {
      setNotice({
        tone: 'danger',
        msg:
          e instanceof Error
            ? e.message
            : t('ai.dataViz.sysPerf.match.confirmFailed'),
      });
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = () => {
    if (!token || !workspaceSlug || !nF) return;

    const plan = buildSysPerfConfirmPlan({
      items: MEASURE_ITEMS,
      files: validFiles,
      headersByFileId: FH,
      match,
      checked,
    });
    const warnings = buildSysPerfConfirmWarningNotice({
      plan,
      fileLabel: ({ fileNumber }) =>
        t('ai.dataViz.sysPerf.match.fileLabel', { index: fileNumber }),
      roomAverageWarning: ({ fileNumber }) =>
        t('ai.dataViz.sysPerf.match.roomAvgWarning', { index: fileNumber }),
    });

    if (warnings.dupes.length || warnings.roomWarn.length) {
      setConfirmModal({
        ...warnings,
        proceed: () => void doConfirm(plan.match, plan.checked, plan.all),
      });
      return;
    }
    void doConfirm(plan.match, plan.checked, plan.all);
  };

  if (!nF) return null;

  return (
    <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      {/* 액션 바 */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onConfirm}
          className="app-text-control-sm inline-flex items-center gap-1.5 rounded-md bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
        >
          {busy ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <CheckCircle2 size={14} />
          )}
          {t('ai.dataViz.sysPerf.match.confirmAction')}
        </button>
        <button
          type="button"
          onClick={onRerun}
          className="app-text-control-sm inline-flex items-center gap-1 rounded-md border border-app-border bg-app-surface px-3 py-1.5 text-app-ink/80 transition-colors hover:bg-app-surface-hover"
        >
          <RefreshCw size={14} />
          {t('ai.dataViz.sysPerf.match.rerunAction')}
        </button>
        {nF > 1 ? (
          <button
            type="button"
            onClick={onSync}
            className="app-text-control-sm inline-flex items-center gap-1 rounded-md border border-ui-warning/50 bg-ui-warning/10 px-3 py-1.5 text-ui-warning transition-colors hover:bg-ui-warning/20"
          >
            <Repeat2 size={14} />
            {t('ai.dataViz.sysPerf.match.syncAction')}
          </button>
        ) : null}
      </div>

      {notice ? (
        <div className="mb-3">
          <InlineNotice tone={notice.tone}>{notice.msg}</InlineNotice>
        </div>
      ) : null}

      {/* 파일 탭 */}
      {nF > 1 ? (
        <div
          className="mb-2 flex flex-wrap gap-1"
          style={{
            borderBottom: `2px solid ${SYSPERF_MATCH_TABLE_COLORS.active}`,
          }}
        >
          {validFiles.map((f, idx) => {
            const fid = f.file_id;
            const active = activeFid === fid;
            return (
              <button
                key={fid}
                type="button"
                title={f.filename}
                onClick={() => setActiveFid(fid)}
                style={{
                  padding: '8px 18px',
                  background: active
                    ? SYSPERF_MATCH_TABLE_COLORS.active
                    : SYSPERF_MATCH_TABLE_COLORS.inactiveBg,
                  color: active
                    ? SYSPERF_MATCH_TABLE_COLORS.white
                    : SYSPERF_MATCH_TABLE_COLORS.text,
                  border: `1px solid ${SYSPERF_MATCH_TABLE_COLORS.active}`,
                  borderBottom: 'none',
                  borderRadius: '6px 6px 0 0',
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {t('ai.dataViz.sysPerf.match.fileLabel', { index: idx + 1 })}
              </button>
            );
          })}
        </div>
      ) : null}

      <SysPerfMatchGrid
        files={validFiles}
        rows={matchRows}
        activeFileId={activeFid}
        headersByFileId={FH}
        collapsedGroups={collapsed}
        avgMode={avgMode}
        targetTemp={targetTemp}
        onTargetTempChange={setTargetTemp}
        onToggleCollapse={onToggleCollapse}
        onToggleAvgMode={onToggleAvgMode}
        onCheckChange={onCheckChange}
        onAltChange={onAltChange}
      />

      {/* 확정 전 경고 모달 (원본 _showDupeWarning 대응) */}
      {confirmModal ? (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setConfirmModal(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-app-surface p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="app-text-title-md mb-2 font-bold text-ui-warning">
              {t('ai.dataViz.sysPerf.match.confirmModal.title')}
            </div>
            {confirmModal.dupes.length ? (
              <div className="mb-4">
                <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
                  {t('ai.dataViz.sysPerf.match.confirmModal.duplicateTitle')}
                </div>
                <div className="flex flex-col gap-2">
                  {confirmModal.dupes.map((d, i) => (
                    <div
                      key={i}
                      className="rounded-lg border-l-4 border-app-accent bg-app-surface-raised px-3 py-2"
                    >
                      <span className="app-text-body-sm text-app-ink/55">
                        {d.file} ·{' '}
                      </span>
                      <span className="app-text-body-sm font-semibold text-ui-danger">
                        “{d.orig}”
                      </span>
                      <span className="app-text-body-sm text-app-ink">
                        {' '}
                        → {d.items}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {confirmModal.roomWarn.length ? (
              <div className="mb-4">
                <div className="app-text-body-sm mb-2 font-semibold text-app-ink">
                  {t('ai.dataViz.sysPerf.match.confirmModal.roomAvgTitle')}
                </div>
                <div className="flex flex-col gap-1.5">
                  {confirmModal.roomWarn.map((w, i) => (
                    <div
                      key={i}
                      className="app-text-body-sm rounded-lg border-l-4 border-ui-warning bg-app-surface-raised px-3 py-2 text-app-ink/80"
                    >
                      {w}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="app-text-body-sm mb-4 text-app-ink/65">
              {t('ai.dataViz.sysPerf.match.confirmModal.prompt')}
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="app-text-control-sm rounded-md border border-app-border bg-app-surface px-4 py-2 font-medium text-app-ink/80 transition-colors hover:bg-app-surface-hover"
              >
                {t('ai.dataViz.sysPerf.match.confirmModal.cancel')}
              </button>
              <button
                type="button"
                onClick={() => confirmModal.proceed()}
                className="app-text-control-sm rounded-md bg-app-accent px-4 py-2 font-semibold text-app-accent-fg transition-colors hover:bg-app-accent-hover"
              >
                {t('ai.dataViz.sysPerf.match.confirmModal.proceed')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
