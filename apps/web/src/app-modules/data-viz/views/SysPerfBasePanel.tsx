import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { SysPerfBaseCars } from './SysPerfBaseCars';
import { SysPerfBaseColumns } from './SysPerfBaseColumns';
import { SysPerfPartsCatalog } from './SysPerfPartsCatalog';

const BASE_SUBTABS = [
  { id: 'columns', labelKey: 'columns' },
  { id: 'cars', labelKey: 'cars' },
  { id: 'parts', labelKey: 'parts' },
] as const;
type BaseSub = (typeof BASE_SUBTABS)[number]['id'];

export function SysPerfBasePanel() {
  const { t } = useTranslation('apps');
  const [sub, setSub] = useState<BaseSub>('columns');
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5">
        {BASE_SUBTABS.map((it) => (
          <button
            key={it.id}
            type="button"
            onClick={() => setSub(it.id)}
            className={cn(
              'app-text-control-sm rounded-md border px-3 py-1.5 transition-colors',
              sub === it.id
                ? 'border-app-accent bg-app-accent/10 text-app-accent'
                : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover',
            )}
          >
            {t(`ai.dataViz.sysPerf.baseTabs.${it.labelKey}`)}
          </button>
        ))}
      </div>
      {sub === 'columns' ? <SysPerfBaseColumns /> : null}
      {sub === 'cars' ? <SysPerfBaseCars /> : null}
      {sub === 'parts' ? <SysPerfPartsCatalog /> : null}
    </div>
  );
}
