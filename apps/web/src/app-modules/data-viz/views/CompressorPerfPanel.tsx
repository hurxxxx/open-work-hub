import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'motion/react';
import { Trash2 } from 'lucide-react';
import { InlineNotice, useConfirm } from '@ai-do/ui';

import { cn } from '@/src/lib/utils';
import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  apiCategory,
  capacitiesForCategory,
  deleteCompressorPerfRow,
  downloadCompressorPerfData,
  getCompressorPerfAnalysis,
  getTolerance,
  getToleranceAll,
  getToleranceProfile,
  getToleranceProfileAll,
  listCompressorPerfData,
  resetCompressorPerfData,
  saveTolerance,
  saveToleranceProfile,
  uploadCompressorPerfMaster,
  uploadCompressorPerfSources,
  uploadToleranceFile,
  type PerfAnalysisResult,
  type PerfCategory,
  type PerfRefrigerant,
  type PerfRow,
  type ToleranceAllResponse,
  type ToleranceResponse,
} from '../api/dataviz-api';
import { CompressorPerfAnalysisSection } from './CompressorPerfAnalysisSection';
import { CompressorPerfResultsSection } from './CompressorPerfResultsSection';
import { CompressorPerfToleranceEditor } from './CompressorPerfToleranceEditor';
import { CompressorPerfUploadSection } from './CompressorPerfUploadSection';
import {
  TEST_TOLERANCE_FIELD_KEYS,
  profileToleranceRowCount,
  type ProfileToleranceProfiles,
  type ProfileToleranceValues,
  type RefToleranceValues,
} from './compressor-perf-tolerance-model';
import { useCompressorPerfUploadSession } from './useCompressorPerfUploadSession';

type PerfTab = 'upload' | 'result' | 'analysis' | 'tolerance';
const MAIN_TABS: PerfTab[] = ['upload', 'result', 'analysis', 'tolerance'];
const CATEGORIES: PerfCategory[] = ['variable', 'electric'];
const REFRIGERANTS: PerfRefrigerant[] = ['new', 'old'];

export function CompressorPerfPanel() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const { confirm, confirmDialog } = useConfirm();

  const [tab, setTab] = useState<PerfTab>('upload');
  const [category, setCategory] = useState<PerfCategory>('variable');
  const [refrigerant, setRefrigerant] = useState<PerfRefrigerant>('new');
  const [capacity, setCapacity] = useState(
    capacitiesForCategory('variable')[0],
  );
  const [toleranceFile, setToleranceFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [uploadStatus, setUploadStatus] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const setSectionStatus = useCallback(
    (key: string, message: string | null) => {
      setUploadStatus((current) => {
        if (message === null) {
          if (!(key in current)) return current;
          const next = { ...current };
          delete next[key];
          return next;
        }
        return { ...current, [key]: message };
      });
    },
    [],
  );
  const [rows, setRows] = useState<PerfRow[]>([]);
  const [analysis, setAnalysis] = useState<PerfAnalysisResult | null>(null);
  const [tolerance, setTolerance] = useState<ToleranceResponse | null>(null);
  const [toleranceAll, setToleranceAll] = useState<ToleranceAllResponse | null>(
    null,
  );
  const [carModel, setCarModel] = useState('');
  const [refValues, setRefValues] = useState<RefToleranceValues>({});
  // 시험공차 — 사용자가 적는 카테고리(예: 'ES')가 프로필명이자 구분(ES1/2/3) 접두어.
  const [profileName, setProfileName] = useState('ES');
  const [tolValues, setTolValues] = useState<ProfileToleranceValues>({});
  // 시험공차 구분 행 개수(예: ES=3, GM TYPE C=4). +/- 로 조절하고, 저장된 프로필을
  // 불러오면 그 행 수에 맞춰진다.
  const [profileRowCount, setProfileRowCount] = useState(3);
  // 이 (카테고리·냉매·용량) 범위에 저장된 모든 시험공차 프로필(ES·GM…). 하단 표에
  // 함께 보여주고, 카테고리 입력/클릭 시 해당 프로필을 편집 그리드로 불러온다.
  const [allProfiles, setAllProfiles] = useState<ProfileToleranceProfiles>({});
  const uploadSession = useCompressorPerfUploadSession();
  const testTolFieldLabels = useMemo(
    () =>
      Object.fromEntries(
        TEST_TOLERANCE_FIELD_KEYS.map((key) => [
          key,
          t(`ai.dataViz.perf.testToleranceFields.${key}`),
        ]),
      ),
    [t],
  );

  const capacities = useMemo(() => capacitiesForCategory(category), [category]);
  const canCallApi = Boolean(token && workspaceSlug);

  useEffect(() => {
    // 카테고리(가변/전동) 전환 시에만 해당 카테고리의 첫 용량으로 맞춘다.
    // 용량은 자유 입력이 가능하므로 사용자가 타이핑한 목록 밖 값은 되돌리지 않는다.
    setCapacity((current) => {
      const next = capacitiesForCategory(category);
      return next.includes(current) ? current : next[0];
    });
  }, [category]);

  const refreshRows = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setLoading('rows');
    setError(null);
    try {
      const response = await listCompressorPerfData(
        token,
        workspaceSlug,
        category,
        refrigerant,
        capacity,
      );
      setRows(response.data);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.loadRows'),
      );
    } finally {
      setLoading(null);
    }
  }, [capacity, category, refrigerant, t, token, workspaceSlug]);

  const refreshAnalysis = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setLoading('analysis');
    setError(null);
    try {
      setAnalysis(
        await getCompressorPerfAnalysis(
          token,
          workspaceSlug,
          category,
          refrigerant,
          capacity,
        ),
      );
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.loadAnalysis'),
      );
    } finally {
      setLoading(null);
    }
  }, [capacity, category, refrigerant, t, token, workspaceSlug]);

  const refreshTolerance = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setLoading('tolerance');
    setError(null);
    try {
      const [response, allResponse] = await Promise.all([
        getTolerance(
          token,
          workspaceSlug,
          category,
          refrigerant,
          capacity,
          carModel,
        ),
        // 업로드 후 검증용 — 카테고리+냉매 전체(모든 용량/기종/ES) 평탄화 데이터.
        getToleranceAll(token, workspaceSlug, category, refrigerant),
      ]);
      setTolerance(response);
      setRefValues(response.ref_values);
      setToleranceAll(allResponse);
      if (!carModel && response.car_models[0])
        setCarModel(response.car_models[0]);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.loadTolerance'),
      );
    } finally {
      setLoading(null);
    }
  }, [capacity, carModel, category, refrigerant, t, token, workspaceSlug]);

  const refreshProfile = useCallback(async () => {
    if (!token || !workspaceSlug) return;
    setLoading('profile');
    setError(null);
    try {
      const [response, allResponse] = await Promise.all([
        getToleranceProfile(
          token,
          workspaceSlug,
          category,
          refrigerant,
          capacity,
          profileName,
        ),
        getToleranceProfileAll(
          token,
          workspaceSlug,
          category,
          refrigerant,
          capacity,
        ),
      ]);
      setTolValues(response.tol_data);
      setProfileRowCount(profileToleranceRowCount(response.tol_data));
      setAllProfiles(allResponse.profiles);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.loadProfile'),
      );
    } finally {
      setLoading(null);
    }
  }, [capacity, category, profileName, refrigerant, t, token, workspaceSlug]);

  useEffect(() => {
    if (tab === 'result') void refreshRows();
  }, [refreshRows, tab]);

  useEffect(() => {
    if (tab === 'analysis') void refreshAnalysis();
  }, [refreshAnalysis, tab]);

  useEffect(() => {
    if (tab === 'tolerance') {
      void refreshTolerance();
      void refreshProfile();
    }
  }, [refreshProfile, refreshTolerance, tab]);

  async function uploadMasterFor(
    cat: PerfCategory,
    file: File | null,
    clearFile: () => void,
  ) {
    if (!token || !workspaceSlug || !file) return;
    const statusKey = `master:${cat}`;
    setLoading(statusKey);
    setError(null);
    setSectionStatus(statusKey, null);
    try {
      const result = await uploadCompressorPerfMaster(
        token,
        workspaceSlug,
        file,
        cat,
      );
      setSectionStatus(
        statusKey,
        t('ai.dataViz.perf.masterImported', { count: result.row_count }),
      );
      clearFile();
      if (cat === category) {
        await refreshRows();
        await refreshAnalysis();
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.uploadMaster'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function uploadSourcesFor(
    cat: PerfCategory,
    files: File[],
    ref: PerfRefrigerant,
    cap: string,
    clearFiles: () => void,
  ) {
    if (!token || !workspaceSlug || files.length === 0) return;
    const statusKey = `sources:${cat}`;
    setLoading(statusKey);
    setError(null);
    setSectionStatus(statusKey, null);
    try {
      const result = await uploadCompressorPerfSources(
        token,
        workspaceSlug,
        files,
        cat,
        ref,
        cap,
      );
      uploadSession.setUploadResult(result);
      setSectionStatus(
        statusKey,
        t('ai.dataViz.perf.sourcesImported', { count: result.success_count }),
      );
      clearFiles();
      if (cat === category) {
        await refreshRows();
        await refreshAnalysis();
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.uploadSources'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleReset(nextCategory: PerfCategory | null) {
    if (!token || !workspaceSlug) return;
    const ok = await confirm({
      title: t(
        nextCategory
          ? 'ai.dataViz.perf.resetCategoryConfirmTitle'
          : 'ai.dataViz.perf.resetAllConfirmTitle',
      ),
      description: t(
        nextCategory
          ? 'ai.dataViz.perf.resetCategoryConfirm'
          : 'ai.dataViz.perf.resetAllConfirm',
        nextCategory
          ? { category: t(`ai.dataViz.perf.categories.${nextCategory}`) }
          : undefined,
      ),
      confirmLabel: t('ai.dataViz.perf.resetConfirmAction'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!ok) return;
    setLoading('reset');
    setError(null);
    try {
      await resetCompressorPerfData(token, workspaceSlug, nextCategory);
      setStatus(t('ai.dataViz.perf.resetDone'));
      await refreshRows();
      await refreshAnalysis();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.reset'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleDelete(rowId: string | undefined) {
    if (!token || !workspaceSlug || !rowId) return;
    setLoading(`delete:${rowId}`);
    setError(null);
    try {
      await deleteCompressorPerfRow(token, workspaceSlug, rowId);
      setRows((current) => current.filter((row) => row.id !== rowId));
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.deleteRow'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleDownload() {
    if (!token || !workspaceSlug) return;
    setLoading('download');
    setError(null);
    try {
      // 카테고리 전체(모든 용량 + 모든 냉매) 데이터를 하나의 워크북으로 묶어
      // 받는다. 탭 분리는 백엔드의 _group_download_sheets에서 capacity 단위로
      // 처리된다.
      const blob = await downloadCompressorPerfData(
        token,
        workspaceSlug,
        category,
        refrigerant,
        '',
        true,
      );
      const today = new Date();
      const yyyymmdd = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`;
      downloadBlobAsFile(
        blob,
        `${yyyymmdd}_${apiCategory(category)}_${t('ai.dataViz.perf.masterFileName')}.xlsx`,
      );
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.download'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleToleranceUpload(): Promise<boolean> {
    if (!token || !workspaceSlug || !toleranceFile) return false;
    setLoading('tolUpload');
    setError(null);
    try {
      const result = await uploadToleranceFile(
        token,
        workspaceSlug,
        toleranceFile,
        category,
        refrigerant,
      );
      setStatus(
        t('ai.dataViz.perf.toleranceImported', { count: result.inserted }),
      );
      setToleranceFile(null);
      await refreshTolerance();
      return true;
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.uploadTolerance'),
      );
      return false;
    } finally {
      setLoading(null);
    }
  }

  async function handleSaveTolerance() {
    if (!token || !workspaceSlug) return;
    setLoading('tolSave');
    setError(null);
    setSectionStatus('refSave', null);
    try {
      await saveTolerance(
        token,
        workspaceSlug,
        category,
        refrigerant,
        capacity,
        carModel,
        refValues,
      );
      setSectionStatus(
        'refSave',
        t('ai.dataViz.perf.toleranceSavedForCapacity', { capacity }),
      );
      await refreshTolerance();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.saveTolerance'),
      );
    } finally {
      setLoading(null);
    }
  }

  async function handleSaveProfile() {
    if (!token || !workspaceSlug) return;
    setLoading('profileSave');
    setError(null);
    setSectionStatus('profileSave', null);
    try {
      await saveToleranceProfile(
        token,
        workspaceSlug,
        category,
        refrigerant,
        capacity,
        profileName,
        tolValues,
        [],
      );
      setSectionStatus(
        'profileSave',
        t('ai.dataViz.perf.profileSavedForName', { name: profileName }),
      );
      await refreshProfile();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.dataViz.errors.saveProfile'),
      );
    } finally {
      setLoading(null);
    }
  }

  return (
    <>
      {confirmDialog}
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-app-border pb-3">
          {tab !== 'upload' ? (
            <FilterBar
              tab={tab}
              category={category}
              refrigerant={refrigerant}
              capacity={capacity}
              capacities={capacities}
              onCategory={setCategory}
              onRefrigerant={setRefrigerant}
              onCapacity={setCapacity}
            />
          ) : (
            <div />
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              style={{ fontSize: '12px' }}
              className="inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-app-ink/75 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              onClick={() => void handleReset(category)}
            >
              <Trash2 size={14} />
              {t('ai.dataViz.perf.resetCategory')}
            </button>
            <button
              type="button"
              style={{ fontSize: '12px' }}
              className="inline-flex items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-2.5 py-1 text-ui-danger transition-colors hover:bg-app-surface-hover"
              onClick={() => void handleReset(null)}
            >
              <Trash2 size={14} />
              {t('ai.dataViz.perf.resetAll')}
            </button>
          </div>
        </div>

        <div className="flex items-center gap-6 border-b border-app-border">
          {MAIN_TABS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTab(item)}
              className={cn(
                'app-text-body-sm relative pb-3 font-medium transition-all',
                tab === item
                  ? 'text-app-ink'
                  : 'text-app-ink/55 hover:text-app-ink',
              )}
            >
              {t(`ai.dataViz.perf.tabs.${item}`)}
              {tab === item ? (
                <motion.div
                  layoutId="dataviz-perf-tab"
                  className="absolute bottom-0 left-0 right-0 h-0.5 bg-app-accent"
                />
              ) : null}
            </button>
          ))}
        </div>

        {!canCallApi ? (
          <InlineNotice tone="warning">
            {t('ai.dataViz.workspaceMissing')}
          </InlineNotice>
        ) : null}
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        {status ? <InlineNotice tone="success">{status}</InlineNotice> : null}

        {tab === 'upload' && (
          <CompressorPerfUploadSection
            session={uploadSession}
            loading={loading}
            uploadStatus={uploadStatus}
            onUploadMaster={uploadMasterFor}
            onUploadSources={uploadSourcesFor}
          />
        )}

        {tab === 'result' && (
          <CompressorPerfResultsSection
            rows={rows}
            category={category}
            refrigerant={refrigerant}
            capacity={capacity}
            loading={loading}
            onRefresh={refreshRows}
            onDownload={handleDownload}
            onDelete={handleDelete}
          />
        )}

        {tab === 'analysis' && (
          <CompressorPerfAnalysisSection
            analysis={analysis}
            loading={loading === 'analysis'}
            capacity={capacity}
          />
        )}

        {tab === 'tolerance' && (
          <CompressorPerfToleranceEditor
            allProfiles={allProfiles}
            capacity={capacity}
            carModel={carModel}
            fieldLabels={testTolFieldLabels}
            loading={loading}
            profileName={profileName}
            profileRowCount={profileRowCount}
            profileSaveStatus={uploadStatus['profileSave']}
            refSaveStatus={uploadStatus['refSave']}
            refValues={refValues}
            tolerance={tolerance}
            toleranceAll={toleranceAll}
            toleranceFile={toleranceFile}
            tolValues={tolValues}
            onCapacityChange={setCapacity}
            onCarModelChange={setCarModel}
            onProfileNameChange={setProfileName}
            onProfileRowCountChange={setProfileRowCount}
            onRefreshProfile={refreshProfile}
            onRefValuesChange={setRefValues}
            onSaveProfile={handleSaveProfile}
            onSaveTolerance={handleSaveTolerance}
            onToleranceFileChange={setToleranceFile}
            onToleranceUpload={handleToleranceUpload}
            onTolValuesChange={setTolValues}
          />
        )}
      </div>
    </>
  );
}

function FilterBar({
  tab,
  category,
  refrigerant,
  capacity,
  capacities,
  onCategory,
  onRefrigerant,
  onCapacity,
}: {
  tab: PerfTab;
  category: PerfCategory;
  refrigerant: PerfRefrigerant;
  capacity: string;
  capacities: readonly string[];
  onCategory: (category: PerfCategory) => void;
  onRefrigerant: (refrigerant: PerfRefrigerant) => void;
  onCapacity: (capacity: string) => void;
}) {
  const { t } = useTranslation('apps');
  const pillBase =
    'rounded-full border px-2 py-0.5 leading-tight transition-colors';
  const active = 'border-app-accent bg-app-accent text-app-accent-fg';
  const inactive =
    'border-app-border bg-app-surface text-app-ink/65 hover:bg-app-surface-hover';
  return (
    <div className="flex flex-col gap-2">
      <h3 className="app-text-body-sm border-l-4 border-app-accent pl-2 font-semibold text-app-ink">
        {t('ai.dataViz.perf.filterTitle', {
          tab: t(`ai.dataViz.perf.tabs.${tab}`),
        })}
      </h3>
      <div className="flex flex-wrap items-center gap-1.5">
        {CATEGORIES.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onCategory(item)}
            style={{ fontSize: '12px' }}
            className={cn(pillBase, category === item ? active : inactive)}
          >
            {t(`ai.dataViz.perf.categories.${item}`)}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {REFRIGERANTS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onRefrigerant(item)}
            style={{ fontSize: '12px' }}
            className={cn(pillBase, refrigerant === item ? active : inactive)}
          >
            {t(`ai.dataViz.perf.refrigerants.${item}`)}
          </button>
        ))}
      </div>
      {tab === 'tolerance' ? null : (
        <div className="flex flex-wrap items-center gap-1.5">
          {capacities.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onCapacity(item)}
              style={{ fontSize: '12px' }}
              className={cn(pillBase, capacity === item ? active : inactive)}
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
