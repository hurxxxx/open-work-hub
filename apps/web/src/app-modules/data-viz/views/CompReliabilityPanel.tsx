import { useCallback, useMemo, useRef, useState } from 'react';
import { Loader2, Upload } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState, InlineNotice, Select } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  getDurabilityGraph,
  getDurabilityGraphElec,
  uploadDurabilityWithProgress,
  type DurabilityColSeries,
  type DurabilityGraphResponse,
} from '../api/dataviz-api';
import {
  ELEC_GRAPH_CONFIG,
  SIMPLE_FIELDS,
  SIMPLE_LABELS,
  type ElectricGraphZoomResult,
  type SimpleField,
} from './comp-reliability-graph-config';
import {
  ElectricReliabilityGraphs,
  SimpleReliabilityGraph,
  VarReliabilityGraphs,
} from './CompReliabilityGraphs';

// ── 레거시 comp_reliability.js 상수 (그대로) ──
type CompType = '가변' | '전동'; // i18n-exempt-line: legacy durability API compressor type values
const SIMPLE_BENCH_TYPE = '간이벤치'; // i18n-exempt-line: legacy durability API test type value
const TEST_ITEMS: Record<CompType, string[]> = {
  가변: [ // i18n-exempt-line: legacy durability API compressor type value
    '고압연속', // i18n-exempt-line: legacy durability API test item value
    '고속연속', // i18n-exempt-line: legacy durability API test item value
    '고속단속', // i18n-exempt-line: legacy durability API test item value
    '액압축', // i18n-exempt-line: legacy durability API test item value
    '고압저냉매', // i18n-exempt-line: legacy durability API test item value
    '복합내구', // i18n-exempt-line: legacy durability API test item value
    '저오일', // i18n-exempt-line: legacy durability API test item value
    '냉매부족', // i18n-exempt-line: legacy durability API test item value
    '초고단', // i18n-exempt-line: legacy durability API test item value
    '사판내구', // i18n-exempt-line: legacy durability API test item value
    '무오일내구', // i18n-exempt-line: legacy durability API test item value
  ], // i18n-exempt-line: legacy durability API test item values
  전동: [ // i18n-exempt-line: legacy durability API compressor type value
    '고온연속', // i18n-exempt-line: legacy durability API test item value
    '저온연속', // i18n-exempt-line: legacy durability API test item value
    '고차압기동', // i18n-exempt-line: legacy durability API test item value
    'RPM RAMP RATE',
    '온도 Cycle', // i18n-exempt-line: legacy durability API test item value
    '인버터 저전압 ON/OFF',
  ], // i18n-exempt-line: legacy durability API test item values
};

// ── 메인 패널 ──
type Screen = 'subtype' | 'durability' | 'simple';

export function CompReliabilityPanel() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [screen, setScreen] = useState<Screen>('subtype');
  const [compType, setCompType] = useState<CompType>('가변');
  const [machine, setMachine] = useState('1');
  const [testItem, setTestItem] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [tab, setTab] = useState<'upload' | 'graph'>('upload');
  const [loading, setLoading] = useState<'upload' | 'graph' | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [varResp, setVarResp] = useState<DurabilityGraphResponse | null>(null);
  const [elecResp, setElecResp] = useState<DurabilityGraphResponse | null>(
    null,
  );
  const [elecZoom, setElecZoom] = useState<ElectricGraphZoomResult[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const machineOptions = useMemo(
    () =>
      compType === '전동'
        ? [
            { value: 'CAN', label: 'CAN' },
            {
              value: 'LIN_ERR_O',
              label: t('ai.dataViz.reliability.linErrorCodeO'),
            },
            {
              value: 'LIN_ERR_X',
              label: t('ai.dataViz.reliability.linErrorCodeX'),
            },
          ]
        : [
            {
              value: '1',
              label: t('ai.dataViz.reliability.machineNumber', {
                number: 1,
              }),
            },
            {
              value: '2',
              label: t('ai.dataViz.reliability.machineNumber', {
                number: 2,
              }),
            },
          ],
    [compType, t],
  );

  const switchCompType = (next: CompType) => {
    setCompType(next);
    setMachine(next === '전동' ? 'CAN' : '1');
    setTestItem('');
    setVarResp(null);
    setElecResp(null);
    setElecZoom([]);
  };

  const handleUpload = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    if (files.length === 0) {
      setError(t('ai.dataViz.reliability.selectFileError'));
      return;
    }
    if (!testItem) {
      setError(t('ai.dataViz.reliability.selectTestItemError'));
      return;
    }
    setLoading('upload');
    setError(null);
    setStatus(null);
    setProgress(0);
    try {
      const res = await uploadDurabilityWithProgress(
        token,
        workspaceSlug,
        files,
        { type: compType, machine, testItem },
        (p) => setProgress(p),
      );
      if (res.status === 'ok') {
        setStatus(
          t('ai.dataViz.reliability.uploadComplete', {
            files: res.file_count,
            rows: res.total_rows,
            columns: res.columns,
          }),
        );
      } else {
        setError(res.error || t('ai.dataViz.reliability.uploadFailed'));
      }
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : t('ai.dataViz.reliability.uploadError'),
      );
    } finally {
      setLoading(null);
      setProgress(null);
    }
  }, [token, workspaceSlug, files, compType, machine, testItem, t]);

  const loadGraphs = useCallback(async () => {
    if (!token || !workspaceSlug || !testItem) return;
    setLoading('graph');
    setError(null);
    setVarResp(null);
    setElecResp(null);
    setElecZoom([]);
    try {
      if (compType === '전동') {
        const cfg = ELEC_GRAPH_CONFIG[testItem];
        if (!cfg) {
          setError(
            t('ai.dataViz.reliability.itemConfigMissing', { item: testItem }),
          );
          return;
        }
        const cols = cfg.traces.map((t) => t.col).join(',');
        const xParam = Array.isArray(cfg.xParam)
          ? cfg.xParam.join(',')
          : String(cfg.xParam);
        const resp = await getDurabilityGraphElec(token, workspaceSlug, {
          type: compType,
          machine,
          testItem,
          cols,
          xMode: cfg.xMode,
          xParam,
        });
        if (resp.error) {
          setError(resp.error);
          return;
        }
        if (testItem === 'RPM RAMP RATE' || testItem === '온도 Cycle')
          divideCompSpeed(resp.data);
        setElecResp(resp);
        if (cfg.zoomGraphs?.length) {
          const zs = await Promise.all(
            cfg.zoomGraphs.map(async (z) => {
              const zr = await getDurabilityGraphElec(token, workspaceSlug, {
                type: compType,
                machine,
                testItem,
                cols,
                xMode: z.xMode,
                xParam: z.xParam.join(','),
              });
              if (
                zr &&
                !zr.error &&
                (testItem === 'RPM RAMP RATE' || testItem === '온도 Cycle')
              )
                divideCompSpeed(zr.data);
              return { z, resp: zr && !zr.error ? zr : null };
            }),
          );
          setElecZoom(zs);
        }
      } else {
        const resp = await getDurabilityGraph(token, workspaceSlug, {
          type: compType,
          machine,
          testItem,
        });
        if (resp.error) {
          setError(resp.error);
          return;
        }
        setVarResp(resp);
      }
    } catch (e) {
      setError(
        e instanceof Error ? e.message : t('ai.dataViz.reliability.graphError'),
      );
    } finally {
      setLoading(null);
    }
  }, [token, workspaceSlug, compType, machine, testItem, t]);

  // 서브타입 선택 화면
  if (screen === 'subtype') {
    return (
      <div className="grid gap-4 sm:grid-cols-2">
        {[
          {
            key: 'simple' as Screen,
            title: t('ai.dataViz.reliability.simpleBench'),
            desc: t('ai.dataViz.reliability.simpleBenchDescription'),
          },
          {
            key: 'durability' as Screen,
            title: t('ai.dataViz.reliability.durabilityBench'),
            desc: t('ai.dataViz.reliability.durabilityBenchDescription'),
          },
        ].map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => setScreen(c.key)}
            className="rounded-2xl border border-app-border bg-app-surface p-6 text-left transition-colors hover:border-app-accent hover:bg-app-surface-hover"
          >
            <div className="app-text-title-md font-semibold text-app-ink">
              {c.title}
            </div>
            <div className="app-text-body-sm mt-1 text-app-ink/55">
              {c.desc}
            </div>
          </button>
        ))}
      </div>
    );
  }

  if (screen === 'simple') {
    return <SimpleBenchScreen onBack={() => setScreen('subtype')} />;
  }

  // 복합내구벤치
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 border-b border-app-border pb-3">
        <button
          type="button"
          onClick={() => setScreen('subtype')}
          className="app-text-control-sm inline-flex h-7 items-center rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover"
        >
          {t('ai.dataViz.reliability.back')}
        </button>
        <div className="flex items-center gap-1.5">
          {(['가변', '전동'] as CompType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => switchCompType(t)}
              className={cn(
                'app-text-control-sm rounded-full border px-2.5 py-0.5 transition-colors',
                compType === t
                  ? 'border-app-accent bg-app-accent text-app-accent-fg'
                  : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {(['upload', 'graph'] as const).map((tk) => (
            <button
              key={tk}
              type="button"
              onClick={() => {
                setTab(tk);
                if (tk === 'graph') void loadGraphs();
              }}
              className={cn(
                'app-text-control-sm rounded-md px-3 py-1 transition-colors',
                tab === tk
                  ? 'bg-app-accent text-app-accent-fg'
                  : 'text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {tk === 'upload'
                ? t('ai.dataViz.reliability.tabs.upload')
                : t('ai.dataViz.reliability.tabs.graph')}
            </button>
          ))}
        </div>
      </div>

      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      {tab === 'upload' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
            <div className="app-text-body-sm mb-3 font-semibold text-app-ink">
              {t('ai.dataViz.reliability.fileUpload')}
            </div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <label className="app-text-control-sm shrink-0 text-app-ink/65">
                {t('ai.dataViz.reliability.testItem')}
              </label>
              <Select
                className="!h-7 min-w-[180px]"
                value={testItem}
                onValueChange={setTestItem}
                placeholder={t('ai.dataViz.reliability.selectPlaceholder')}
                options={TEST_ITEMS[compType].map((it) => ({
                  value: it,
                  label: it,
                }))}
              />
            </div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <label className="app-text-control-sm shrink-0 text-app-ink/65">
                {compType === '전동'
                  ? t('ai.dataViz.reliability.communication')
                  : t('ai.dataViz.reliability.machine')}
              </label>
              <Select
                className="!h-7 min-w-[140px]"
                value={machine}
                onValueChange={setMachine}
                options={machineOptions}
              />
            </div>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed border-app-border bg-app-bg p-5 transition-colors hover:border-app-accent"
            >
              <Upload size={20} className="text-app-ink/55" />
              <div>
                <div className="app-text-body-sm font-medium text-app-ink/75">
                  {files.length > 0
                    ? t('ai.dataViz.reliability.filesSelected', {
                        count: files.length,
                      })
                    : t('ai.dataViz.reliability.clickToSelectFiles')}
                </div>
                <div className="app-text-caption text-app-ink/45">
                  {t('ai.dataViz.reliability.acceptedFilesHint')}
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.xlsx,.xls,.tsv"
                className="hidden"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </div>
            <button
              type="button"
              disabled={loading === 'upload'}
              onClick={() => void handleUpload()}
              className="app-text-control-sm mt-3 inline-flex h-8 items-center gap-1.5 rounded-md bg-app-accent px-3 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
            >
              {loading === 'upload' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              {loading === 'upload'
                ? t('ai.dataViz.reliability.uploading')
                : t('ai.dataViz.reliability.uploadAndMerge')}
            </button>
            {progress != null ? (
              <div className="mt-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-app-surface-hover">
                  <div
                    className="h-full rounded-full bg-app-accent transition-[width] duration-200"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="app-text-caption mt-1 text-app-ink/65">
                  {progress < 40
                    ? t('ai.dataViz.reliability.uploadProgress', { progress })
                    : progress < 100
                      ? t('ai.dataViz.reliability.mergeProgress', {
                          files: files.length,
                          progress,
                        })
                      : t('ai.dataViz.reliability.progressComplete')}
                </div>
              </div>
            ) : null}
            {status ? (
              <div className="mt-2">
                <InlineNotice tone="success">{status}</InlineNotice>
              </div>
            ) : null}
          </div>
          <div className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
            <div className="app-text-body-sm mb-3 font-semibold text-app-ink">
              {t('ai.dataViz.reliability.testInfo')}
            </div>
            <table className="w-full app-text-body-sm">
              <tbody>
                <tr>
                  <td className="py-1.5 font-semibold text-app-ink/75">
                    {t('ai.dataViz.reliability.testPurpose')}
                  </td>
                  <td className="text-app-ink">{testItem || '—'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 font-semibold text-app-ink/75">
                    {t('ai.dataViz.reliability.compType')}
                  </td>
                  <td className="text-app-ink">{compType}</td>
                </tr>
                <tr>
                  <td className="py-1.5 font-semibold text-app-ink/75">
                    {compType === '전동'
                      ? t('ai.dataViz.reliability.communication')
                      : t('ai.dataViz.reliability.machine')}
                  </td>
                  <td className="text-app-ink">
                    {machineOptions.find((m) => m.value === machine)?.label ??
                      machine}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div>
          {loading === 'graph' ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 size={22} className="animate-spin text-app-accent" />
            </div>
          ) : compType === '전동' && elecResp ? (
            <ElectricReliabilityGraphs
              resp={elecResp}
              cfg={ELEC_GRAPH_CONFIG[testItem]}
              zoomResps={elecZoom}
            />
          ) : compType === '가변' && varResp ? (
            <VarReliabilityGraphs resp={varResp} />
          ) : (
            <EmptyState
              title={t('ai.dataViz.reliability.openGraphAfterUpload')}
            />
          )}
        </div>
      )}
    </div>
  );
}

function divideCompSpeed(data: Record<string, DurabilityColSeries>) {
  if (data?.['Comp.Speed']?.y) {
    data['Comp.Speed'].y = data['Comp.Speed'].y.map((v) =>
      v != null ? v / 100 : null,
    );
  }
}

// ── 간이벤치 ──
interface SimplePreset {
  name: string;
  pd: string;
  ps: string;
  crank: string;
  td: string;
  ts: string;
  surface: string;
  rpm: string;
  fixRow1: number;
  fixRow2: number;
}
const SIMPLE_PRESETS_KEY = 'dv_simple_presets';
const DEFAULT_SIMPLE_PRESETS: SimplePreset[] = [
  {
    name: '1호기', // i18n-exempt-line: default persisted legacy preset name
    pd: 'D',
    ps: 'E',
    crank: 'H',
    td: 'I',
    ts: 'J',
    surface: 'K',
    rpm: 'R',
    fixRow1: 39,
    fixRow2: 40,
  },
  {
    name: '2호기', // i18n-exempt-line: default persisted legacy preset name
    pd: 'D',
    ps: 'E',
    crank: 'H',
    td: 'I',
    ts: 'J',
    surface: 'K',
    rpm: 'R',
    fixRow1: 39,
    fixRow2: 40,
  },
  {
    name: '3호기', // i18n-exempt-line: default persisted legacy preset name
    pd: 'D',
    ps: 'E',
    crank: 'H',
    td: 'I',
    ts: 'J',
    surface: 'K',
    rpm: 'N',
    fixRow1: 30,
    fixRow2: 31,
  },
  {
    name: '4호기', // i18n-exempt-line: default persisted legacy preset name
    pd: 'D',
    ps: 'E',
    crank: 'H',
    td: 'I',
    ts: 'J',
    surface: 'K',
    rpm: 'N',
    fixRow1: 30,
    fixRow2: 31,
  },
];

function SimpleBenchScreen({ onBack }: { onBack: () => void }) {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [tab, setTab] = useState<'upload' | 'graph'>('upload');
  const [testItem, setTestItem] = useState('');
  const [machine, setMachine] = useState('1');
  const [files, setFiles] = useState<File[]>([]);
  const [colMap, setColMap] = useState<Record<SimpleField, string>>({
    pd: 'D',
    ps: 'E',
    crank: 'H',
    td: 'I',
    ts: 'J',
    surface: 'K',
    rpm: 'R',
  });
  const [fixRow1, setFixRow1] = useState('39');
  const [fixRow2, setFixRow2] = useState('40');
  const [presets, setPresets] = useState<SimplePreset[]>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(SIMPLE_PRESETS_KEY) || '');
      if (Array.isArray(p) && p.length >= 4) return p;
    } catch {
      /* ignore */
    }
    return DEFAULT_SIMPLE_PRESETS;
  });
  const [curPreset, setCurPreset] = useState(0);
  const [loading, setLoading] = useState<'upload' | 'graph' | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<DurabilityGraphResponse | null>(null);
  const [graphColMap, setGraphColMap] =
    useState<Record<SimpleField, string>>(colMap);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const loadPreset = (idx: number) => {
    const p = presets[idx] ?? DEFAULT_SIMPLE_PRESETS[idx];
    setCurPreset(idx);
    setColMap({
      pd: p.pd,
      ps: p.ps,
      crank: p.crank,
      td: p.td,
      ts: p.ts,
      surface: p.surface,
      rpm: p.rpm,
    });
    setFixRow1(String(p.fixRow1));
    setFixRow2(String(p.fixRow2));
  };
  const savePreset = () => {
    const next = presets.slice();
    next[curPreset] = {
      name:
        presets[curPreset]?.name ??
        t('ai.dataViz.reliability.machineNumber', {
          number: curPreset + 1,
        }),
      ...colMap,
      fixRow1: parseInt(fixRow1, 10) || 0,
      fixRow2: parseInt(fixRow2, 10) || 0,
    };
    setPresets(next);
    try {
      localStorage.setItem(SIMPLE_PRESETS_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
    setStatus(
      t('ai.dataViz.reliability.presetSaved', { name: next[curPreset].name }),
    );
  };

  const handleUpload = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    if (files.length === 0) {
      setError(t('ai.dataViz.reliability.selectFileError'));
      return;
    }
    if (!testItem) {
      setError(t('ai.dataViz.reliability.selectTestItemError'));
      return;
    }
    const fr1 = parseInt(fixRow1, 10) || 0;
    const fr2 = parseInt(fixRow2, 10) || 0;
    setLoading('upload');
    setError(null);
    setStatus(null);
    setProgress(0);
    try {
      const res = await uploadDurabilityWithProgress(
        token,
        workspaceSlug,
        files,
        {
          type: SIMPLE_BENCH_TYPE,
          machine,
          testItem,
          fixRow1: fr1,
          fixRow2: fr2,
          autoDetect: fr1 === 0 || fr2 === 0,
        },
        (p) => setProgress(p),
      );
      if (res.status === 'ok') {
        if (res.fix_row1) setFixRow1(String(res.fix_row1));
        if (res.fix_row2) setFixRow2(String(res.fix_row2));
        const detected =
          res.fix_row1 && res.fix_row2
            ? t('ai.dataViz.reliability.headerDetected', {
                row1: res.fix_row1,
                row2: res.fix_row2,
              })
            : '';
        setStatus(
          t('ai.dataViz.reliability.uploadCompleteWithDetail', {
            files: res.file_count,
            rows: res.total_rows,
            columns: res.columns,
            detail: detected,
          }),
        );
      } else {
        setError(res.error || t('ai.dataViz.reliability.uploadFailed'));
      }
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : t('ai.dataViz.reliability.uploadError'),
      );
    } finally {
      setLoading(null);
      setProgress(null);
    }
  }, [token, workspaceSlug, files, machine, testItem, fixRow1, fixRow2, t]);

  const loadGraph = useCallback(async () => {
    if (!token || !workspaceSlug || !testItem) return;
    setLoading('graph');
    setError(null);
    setResp(null);
    setGraphColMap(colMap);
    try {
      const r = await getDurabilityGraph(token, workspaceSlug, {
        type: SIMPLE_BENCH_TYPE,
        machine,
        testItem,
      });
      if (r.error) {
        setError(r.error);
        return;
      }
      setResp(r);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : t('ai.dataViz.reliability.graphError'),
      );
    } finally {
      setLoading(null);
    }
  }, [token, workspaceSlug, machine, testItem, colMap, t]);

  const cellInput =
    'app-text-control-sm h-7 w-14 rounded-md border border-app-border bg-app-surface px-2 text-center uppercase text-app-ink outline-none focus:border-app-accent';

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 border-b border-app-border pb-3">
        <button
          type="button"
          onClick={onBack}
          className="app-text-control-sm inline-flex h-7 items-center rounded-md border border-app-border bg-app-surface px-2.5 text-app-ink/75 transition-colors hover:bg-app-surface-hover"
        >
          {t('ai.dataViz.reliability.back')}
        </button>
        <span className="app-text-body-sm font-semibold text-app-ink">
          {t('ai.dataViz.reliability.simpleBench')}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          {(['upload', 'graph'] as const).map((tk) => (
            <button
              key={tk}
              type="button"
              onClick={() => {
                setTab(tk);
                if (tk === 'graph') void loadGraph();
              }}
              className={cn(
                'app-text-control-sm rounded-md px-3 py-1 transition-colors',
                tab === tk
                  ? 'bg-app-accent text-app-accent-fg'
                  : 'text-app-ink/65 hover:bg-app-surface-hover',
              )}
            >
              {tk === 'upload'
                ? t('ai.dataViz.reliability.tabs.upload')
                : t('ai.dataViz.reliability.tabs.graph')}
            </button>
          ))}
        </div>
      </div>

      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      {tab === 'upload' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="flex flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
            <div className="app-text-body-sm font-semibold text-app-ink">
              {t('ai.dataViz.reliability.fileUpload')}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="app-text-control-sm shrink-0 text-app-ink/65">
                {t('ai.dataViz.reliability.testItem')}
              </label>
              <Select
                className="!h-7 min-w-[180px]"
                value={testItem}
                onValueChange={setTestItem}
                placeholder={t('ai.dataViz.reliability.selectItemPlaceholder')}
                options={TEST_ITEMS['가변'].map((it) => ({
                  value: it,
                  label: it,
                }))}
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <label className="app-text-control-sm shrink-0 text-app-ink/65">
                {t('ai.dataViz.reliability.machine')}
              </label>
              {['1', '2', '3', '4'].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMachine(m)}
                  className={cn(
                    'app-text-control-sm rounded-full border px-2.5 py-0.5 transition-colors',
                    machine === m
                      ? 'border-app-accent bg-app-accent text-app-accent-fg'
                      : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
                  )}
                >
                  {t('ai.dataViz.reliability.machineNumber', { number: m })}
                </button>
              ))}
            </div>
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed border-app-border bg-app-bg p-5 transition-colors hover:border-app-accent"
            >
              <Upload size={20} className="text-app-ink/55" />
              <div>
                <div className="app-text-body-sm font-medium text-app-ink/75">
                  {files.length > 0
                    ? t('ai.dataViz.reliability.filesSelected', {
                        count: files.length,
                      })
                    : t('ai.dataViz.reliability.clickToSelectFiles')}
                </div>
                <div className="app-text-caption text-app-ink/45">
                  .csv, .xlsx, .xls
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </div>
            <button
              type="button"
              disabled={loading === 'upload'}
              onClick={() => void handleUpload()}
              className="app-text-control-sm inline-flex h-8 items-center gap-1.5 self-start rounded-md bg-app-accent px-3 font-medium text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:opacity-60"
            >
              {loading === 'upload' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Upload size={14} />
              )}
              {loading === 'upload'
                ? t('ai.dataViz.reliability.uploading')
                : t('ai.dataViz.reliability.uploadAndMerge')}
            </button>
            {progress != null ? (
              <div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-app-surface-hover">
                  <div
                    className="h-full rounded-full bg-app-accent transition-[width] duration-200"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="app-text-caption mt-1 text-app-ink/65">
                  {progress < 40
                    ? t('ai.dataViz.reliability.uploadProgress', { progress })
                    : progress < 100
                      ? t('ai.dataViz.reliability.mergeProgress', {
                          files: files.length,
                          progress,
                        })
                      : t('ai.dataViz.reliability.progressComplete')}
                </div>
              </div>
            ) : null}
            {status ? (
              <InlineNotice tone="success">{status}</InlineNotice>
            ) : null}
          </div>

          <div className="flex flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
            <div className="app-text-body-sm font-semibold text-app-ink">
              {t('ai.dataViz.reliability.mappingPreset')}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {presets.map((p, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => loadPreset(i)}
                  className={cn(
                    'app-text-control-sm rounded-md border px-2.5 py-0.5 transition-colors',
                    curPreset === i
                      ? 'border-app-accent bg-app-accent text-app-accent-fg'
                      : 'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover',
                  )}
                >
                  {p.name ||
                    t('ai.dataViz.reliability.machineNumber', {
                      number: i + 1,
                    })}
                </button>
              ))}
              <button
                type="button"
                onClick={savePreset}
                className="app-text-control-sm ml-2 rounded-md border border-app-border bg-app-surface px-2.5 py-0.5 text-app-ink/75 hover:bg-app-surface-hover"
              >
                {t('ai.dataViz.reliability.saveCurrentMapping')}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {SIMPLE_FIELDS.map((f) => (
                <label key={f} className="flex items-center gap-1">
                  <span
                    className="app-text-caption text-app-ink/65"
                    style={{ minWidth: 52 }}
                  >
                    {SIMPLE_LABELS[f]}
                  </span>
                  <input
                    type="text"
                    className={cellInput}
                    value={colMap[f]}
                    onChange={(e) =>
                      setColMap({
                        ...colMap,
                        [f]: e.target.value.toUpperCase().trim(),
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="app-text-control-sm text-app-ink/65">
                {t('ai.dataViz.reliability.headerRows')}
              </label>
              <input
                type="number"
                className={cellInput}
                value={fixRow1}
                onChange={(e) => setFixRow1(e.target.value)}
              />
              <input
                type="number"
                className={cellInput}
                value={fixRow2}
                onChange={(e) => setFixRow2(e.target.value)}
              />
              <span className="app-text-caption text-app-ink/45">
                {t('ai.dataViz.reliability.autoDetectHint')}
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div>
          {loading === 'graph' ? (
            <div className="flex h-40 items-center justify-center">
              <Loader2 size={22} className="animate-spin text-app-accent" />
            </div>
          ) : resp ? (
            <SimpleReliabilityGraph resp={resp} colMap={graphColMap} />
          ) : (
            <EmptyState
              title={t('ai.dataViz.reliability.openGraphAfterUpload')}
            />
          )}
        </div>
      )}
    </div>
  );
}
