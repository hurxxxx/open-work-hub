import { LazyMotion, domAnimation, m } from 'motion/react';
import { Construction } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { NavItem } from '@/src/app/shell/navigation-types';

type ComingSoonNavItem = Pick<NavItem, 'description' | 'icon' | 'id' | 'title'>;

export const ComingSoonView = ({ item }: { item: ComingSoonNavItem }) => {
  const { t } = useTranslation(['apps', 'shell']);
  const title = t(`shell:nav.${item.id}`, { defaultValue: item.title });
  const description = item.description
    ? t(`shell:navDescriptions.${item.id}`, { defaultValue: item.description })
    : null;

  return (
    <LazyMotion features={domAnimation}>
      <m.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-auto max-w-3xl p-8"
      >
        <div className="card space-y-6">
          <header className="flex items-start gap-4">
            <div className="rounded-2xl border border-app-border bg-app-bg p-4">
              <item.icon size={32} className="text-app-accent" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h1 className="app-text-title-lg text-app-ink">{title}</h1>
                <span className="rounded border border-app-border bg-app-bg px-2 py-0.5 text-[12px] uppercase tracking-wide text-app-ink/55">
                  {t('apps:toolView.comingSoon')}
                </span>
              </div>
              {description ? (
                <p className="mt-2 app-text-body text-app-ink/55 dark:text-app-ink/65">
                  {description}
                </p>
              ) : null}
            </div>
          </header>

          <div className="rounded-xl border border-dashed border-app-border bg-app-bg/40 p-6">
            <div className="flex items-start gap-3">
              <Construction
                size={20}
                className="mt-0.5 shrink-0 text-app-accent"
              />
              <div className="space-y-2">
                <p className="app-text-body text-app-ink">
                  {t('apps:toolView.comingSoonDescription')}
                </p>
                <p className="app-text-caption text-app-ink/55 dark:text-app-ink/65">
                  {t('apps:toolView.comingSoonHint')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </m.div>
    </LazyMotion>
  );
};
