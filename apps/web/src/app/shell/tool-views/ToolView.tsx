import { LazyMotion, domAnimation, m } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { 
  Share2, 
  History, 
  FilePlus, 
  Mic, 
  Brain, 
  Activity, 
  FileText, 
  HelpCircle 
} from 'lucide-react';
import type { NavItem } from '@/src/app/shell/navigation-types';

export const ToolView = ({ item }: { item: NavItem }) => {
  const { t } = useTranslation(['apps', 'shell']);
  const title = t(`shell:nav.${item.id}`, { defaultValue: item.title });
  const description = item.description
    ? t(`shell:navDescriptions.${item.id}`, { defaultValue: item.description })
    : '';

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="p-8 max-w-5xl mx-auto"
      >
      <div className="card space-y-8">
        <header className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="p-4 bg-app-bg rounded-2xl border border-app-border">
              <item.icon size={32} className="text-app-accent" />
            </div>
            <div>
              <h1 className="app-text-title-lg mb-2 text-app-ink">{title}</h1>
              <p className="app-text-body text-app-ink/55 dark:text-app-ink/65">{description}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button type="button" aria-label={t('common:actions.share')} className="p-2 hover:bg-app-surface-hover rounded-md border border-app-border text-app-ink/55 dark:text-app-ink/65">
              <Share2 size={18} />
            </button>
            <button type="button" aria-label={t('apps:toolView.recentWork')} className="p-2 hover:bg-app-surface-hover rounded-md border border-app-border text-app-ink/55 dark:text-app-ink/65">
              <History size={18} />
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-6">
            <div className="space-y-4">
              <label className="app-text-control text-app-ink/55 dark:text-app-ink/65">{t('apps:toolView.inputContent')}</label>
              <textarea 
                aria-label={t('apps:toolView.inputContent')}
                className="app-text-body h-64 w-full resize-none rounded-xl border border-app-border bg-app-bg p-6 leading-relaxed text-app-ink transition-all focus:border-app-accent focus:outline-none"
                placeholder={t('apps:toolView.inputPlaceholder')}
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex gap-2">
                <button type="button" className="app-text-control flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-all hover:bg-app-surface-hover">
                  <FilePlus size={18} />
                  <span>{t('apps:toolView.uploadFile')}</span>
                </button>
                <button type="button" className="app-text-control flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-all hover:bg-app-surface-hover">
                  <Mic size={18} />
                  <span>{t('apps:toolView.voiceInput')}</span>
                </button>
              </div>
              <button type="button" className="app-text-control flex items-center gap-2 rounded-lg bg-app-accent px-8 py-2.5 font-semibold text-app-accent-fg shadow-sm transition-all hover:bg-opacity-90">
                <Brain size={18} />
                <span>{t('apps:toolView.runAi')}</span>
              </button>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card bg-app-bg/50 border-dashed">
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
                <Activity size={16} className="text-app-accent" />
                {t('apps:toolView.recentWork')}
              </h3>
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md transition-colors cursor-pointer group">
                    <div className="flex size-8 items-center justify-center rounded border border-app-border bg-app-surface-sidebar">
                      <FileText size={14} className="text-app-ink/55 group-hover:text-app-accent" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="app-text-caption truncate text-app-ink">{t('apps:toolView.recentDocument', { index: i })}</div>
                      <div className="app-text-micro text-app-ink/55">{t('apps:toolView.recentTime')}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card bg-app-bg/50 border-dashed">
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
                <HelpCircle size={16} className="text-app-accent" />
                {t('apps:toolView.help')}
              </h3>
              <p className="app-text-caption leading-relaxed text-app-ink/55">
                {t('apps:toolView.helpDescription')}
              </p>
            </div>
          </div>
        </div>
      </div>
      </m.div>
    </LazyMotion>
  );
};
