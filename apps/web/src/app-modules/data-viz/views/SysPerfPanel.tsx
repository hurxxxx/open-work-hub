import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { SysPerfMatchTable } from './SysPerfMatchTable';
import { SysPerfTestInfo } from './SysPerfTestInfo';
import { SysPerfGraph } from './SysPerfGraph';
import { SysPerfDiagram } from './SysPerfDiagram';
import { SysPerfBasePanel } from './SysPerfBasePanel';
import { SysPerfDataTableTab } from './SysPerfDataTableTab';
import { SysPerfDbResultTab } from './SysPerfDbResultTab';
import { SysPerfUploadTab } from './SysPerfUploadTab';
import { useCanManageSysPerfBase } from './sysperf-workspace';
import { useSysPerfUploadSession } from './useSysPerfUploadSession';

const SP_TABS = [
  { id: 'upload', labelKey: 'upload' },
  { id: 'match', labelKey: 'match' },
  { id: 'table', labelKey: 'table' },
  { id: 'graph', labelKey: 'graph' },
  { id: 'diagram', labelKey: 'diagram' },
  { id: 'db', labelKey: 'db' },
  { id: 'base', labelKey: 'base' },
] as const;
type SpTab = (typeof SP_TABS)[number]['id'];

export function SysPerfPanel() {
  const { t } = useTranslation('apps');
  const [tab, setTab] = useState<SpTab>('upload');
  const canManageBase = useCanManageSysPerfBase();
  const visibleTabs = useMemo(
    () => SP_TABS.filter((item) => item.id !== 'base' || canManageBase),
    [canManageBase],
  );

  const uploadSession = useSysPerfUploadSession();

  useEffect(() => {
    if (tab === 'base' && !canManageBase) {
      setTab('upload');
    }
  }, [canManageBase, tab]);

  return (
    <div className="flex flex-col gap-4">
      {/* 서브탭 */}
      <div className="flex flex-wrap items-center gap-1.5">
        {visibleTabs.map((it) => (
          <button
            key={it.id}
            type="button"
            onClick={() => setTab(it.id)}
            className={cn(
              'app-text-control-sm rounded-md border px-3 py-1.5 transition-colors',
              tab === it.id
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
            )}
          >
            {t(`ai.dataViz.sysPerf.tabs.${it.labelKey}`)}
          </button>
        ))}
      </div>

      {tab === 'upload' ? (
        <>
          <SysPerfUploadTab
            uploaded={uploadSession.uploaded}
            setUploaded={uploadSession.setUploaded}
            selFileId={uploadSession.selFileId}
            setSelFileId={uploadSession.setSelFileId}
            selSheet={uploadSession.selSheet}
            setSelSheet={uploadSession.setSelSheet}
          />
          <SysPerfTestInfo
            files={uploadSession.uploaded}
            common={uploadSession.common}
            setCommon={uploadSession.setCommon}
            perFile={uploadSession.perFile}
            setPerFile={uploadSession.setPerFile}
            parts={uploadSession.parts}
            setParts={uploadSession.setParts}
          />
        </>
      ) : null}
      {tab === 'match' ? (
        <SysPerfMatchTable files={uploadSession.uploaded} />
      ) : null}
      {tab === 'table' ? (
        <SysPerfDataTableTab
          fileId={uploadSession.selFileId}
          sheet={uploadSession.selSheet}
          fileName={uploadSession.selectedFile?.filename}
          common={uploadSession.common}
          perFile={uploadSession.perFile}
          parts={uploadSession.parts}
        />
      ) : null}
      {tab === 'graph' ? <SysPerfGraph files={uploadSession.uploaded} /> : null}
      {tab === 'diagram' ? (
        <SysPerfDiagram files={uploadSession.uploaded} />
      ) : null}
      {tab === 'db' ? <SysPerfDbResultTab /> : null}
      {tab === 'base' && canManageBase ? <SysPerfBasePanel /> : null}
    </div>
  );
}
