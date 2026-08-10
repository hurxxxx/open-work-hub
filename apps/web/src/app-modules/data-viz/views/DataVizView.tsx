import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'motion/react';
import { ArrowLeft, BarChart3 } from 'lucide-react';

import { cn } from '@/src/lib/utils';
import { CompReliabilityPanel } from './CompReliabilityPanel';
import { CompressorPerfPanel } from './CompressorPerfPanel';
import { SysPerfPanel } from './SysPerfPanel';

type TestType = 'vehicle' | 'system' | 'compressor';
type CompTab = 'performance' | 'reliability';

const TEST_TYPES: Array<{
  id: TestType;
  ready: boolean;
}> = [
  { id: 'vehicle', ready: false },
  { id: 'system', ready: true },
  { id: 'compressor', ready: true },
];

const COMP_TABS: CompTab[] = ['performance', 'reliability'];

export function DataVizView() {
  const { t } = useTranslation('apps');
  const [testType, setTestType] = useState<TestType | null>(null);
  const [compTab, setCompTab] = useState<CompTab>('performance');

  return (
    <div className="relative flex h-full min-w-0 flex-col">
      <header className="border-b border-app-border bg-app-bg px-4 pt-4 transition-colors lg:px-6 lg:pt-3">
        {/* Row 1: breadcrumb */}
        <nav className="app-text-caption mb-1.5 hidden min-w-0 items-center gap-1.5 text-app-ink/50 lg:flex">
          <span className="shrink-0">{t('ai.dataViz.title')}</span>
          {testType ? (
            <>
              <span className="shrink-0 text-app-ink/35">/</span>
              <span className="truncate">
                {t(`ai.dataViz.testTypes.${testType}.title`)}
              </span>
            </>
          ) : null}
        </nav>

        {/* Row 2: title + actions */}
        <div className="mb-3 flex min-w-0 items-start justify-between gap-3 lg:items-center lg:gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-app-accent text-app-accent-fg lg:h-7 lg:w-7">
              <BarChart3 size={16} />
            </div>
            <div className="min-w-0">
              <h1 className="app-text-title-md min-w-0 truncate text-app-ink">
                {t('ai.dataViz.title')}
              </h1>
              {testType ? (
                <p className="app-text-caption mt-0.5 truncate text-app-ink/45">
                  {t(`ai.dataViz.testTypes.${testType}.title`)}
                </p>
              ) : null}
            </div>
            {testType ? (
              <button
                type="button"
                onClick={() => setTestType(null)}
                className="app-text-control-sm ml-1 inline-flex h-7 shrink-0 items-center gap-1 rounded text-app-ink/65 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              >
                <ArrowLeft size={14} />
                <span className="hidden sm:inline">
                  {t('ai.dataViz.changeTestType')}
                </span>
              </button>
            ) : null}
          </div>
        </div>

        {testType === 'compressor' ? (
          <div className="hidden items-center gap-6 lg:flex">
            {COMP_TABS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCompTab(item)}
                className={cn(
                  'app-text-body-sm relative pb-3 font-medium transition-all',
                  compTab === item
                    ? 'text-app-ink'
                    : 'text-app-ink/50 hover:text-app-ink',
                )}
              >
                {t(`ai.dataViz.compTabs.${item}`)}
                {compTab === item ? (
                  <motion.div
                    layoutId="dataviz-comp-tab"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-app-accent"
                  />
                ) : null}
              </button>
            ))}
          </div>
        ) : null}

        {testType === 'compressor' ? (
          <div className="flex items-center gap-1 overflow-x-auto pb-3 lg:hidden">
            {COMP_TABS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setCompTab(item)}
                className={cn(
                  'app-text-control-sm flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-2 transition-colors',
                  compTab === item
                    ? 'border-app-accent bg-app-accent/10 text-app-accent'
                    : 'border-app-border text-app-ink/65 hover:bg-app-surface-hover hover:text-app-ink',
                )}
              >
                {t(`ai.dataViz.compTabs.${item}`)}
              </button>
            ))}
          </div>
        ) : null}
      </header>

      <main className="custom-scrollbar flex-1 overflow-y-auto p-4 lg:p-8">
        {!testType ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:w-2/3 xl:grid-cols-3">
            {TEST_TYPES.map(({ id, ready }) => {
              if (id === 'compressor') {
                return (
                  <div
                    key={id}
                    className="flex flex-col gap-3 rounded-2xl border border-app-border bg-app-surface p-5 text-left"
                  >
                    <div>
                      <div className="app-text-body font-semibold text-app-ink">
                        {t(`ai.dataViz.testTypes.${id}.title`)}
                      </div>
                      <div className="app-text-body-sm text-app-ink/65">
                        {t(`ai.dataViz.testTypes.${id}.description`)}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {COMP_TABS.map((sub) => (
                        <button
                          key={sub}
                          type="button"
                          onClick={() => {
                            setCompTab(sub);
                            setTestType('compressor');
                          }}
                          className="app-text-body-sm flex flex-col items-start gap-0.5 rounded-xl border border-app-border bg-app-bg p-3 text-left font-medium text-app-ink transition-all hover:border-app-accent/60 hover:bg-app-accent/5 hover:shadow-sm"
                        >
                          {t(`ai.dataViz.compTabs.${sub}`)}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              }
              return (
                <button
                  key={id}
                  type="button"
                  disabled={!ready}
                  onClick={() => ready && setTestType(id)}
                  className={cn(
                    'flex flex-col items-start gap-2 rounded-2xl border border-app-border bg-app-surface p-5 text-left transition-all',
                    ready
                      ? 'hover:border-app-accent/60 hover:bg-app-accent/5 hover:shadow-sm'
                      : 'cursor-not-allowed opacity-60',
                  )}
                >
                  <div className="app-text-body font-semibold text-app-ink">
                    {t(`ai.dataViz.testTypes.${id}.title`)}
                  </div>
                  <div className="app-text-body-sm text-app-ink/65">
                    {t(`ai.dataViz.testTypes.${id}.description`)}
                  </div>
                  {!ready ? (
                    <span className="app-text-caption mt-1 inline-flex items-center rounded-full border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink/55">
                      {t('ai.dataViz.comingSoon')}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        ) : null}

        {testType === 'compressor' ? (
          compTab === 'performance' ? (
            <CompressorPerfPanel />
          ) : (
            <CompReliabilityPanel />
          )
        ) : null}

        {testType === 'system' ? <SysPerfPanel /> : null}

        {testType === 'vehicle' ? (
          <div className="grid min-h-[200px] place-items-center rounded-2xl border border-dashed border-app-border bg-app-surface p-10 text-center">
            <p className="app-text-body text-app-ink/60">
              {t('ai.dataViz.comingSoonSentence')}
            </p>
          </div>
        ) : null}
      </main>
    </div>
  );
}
