import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { Tabs, TabsList, TabsTrigger } from '@open-alm/ui';

import { AdminAiModelSettingsSection } from './admin-ai-model-settings-section';
import { AdminImageModelSettingsSection } from './admin-image-model-settings-section';
import { AdminLlmProviderSettingsSection } from './admin-llm-provider-settings-section';
import { AdminLlmRoutingOverview } from './admin-llm-routing-overview';
import { SurfaceCard } from './admin-shared';

export const LLM_MANAGEMENT_TABS = [
  'routing',
  'providers',
  'models',
  'images',
] as const;

export type LlmManagementTab = (typeof LLM_MANAGEMENT_TABS)[number];

export function resolveLlmManagementTab(
  value: string | null,
): LlmManagementTab {
  return LLM_MANAGEMENT_TABS.includes(value as LlmManagementTab)
    ? (value as LlmManagementTab)
    : 'routing';
}

export function withLlmManagementTab(
  searchParams: URLSearchParams,
  tab: LlmManagementTab,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set('tab', tab);
  return next;
}

export function AdminLlmManagementSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = resolveLlmManagementTab(searchParams.get('tab'));
  const requestedTabRef = useRef<LlmManagementTab>(tab);

  useEffect(() => {
    requestedTabRef.current = tab;
  }, [tab]);

  const setTab = (nextTab: LlmManagementTab) => {
    if (requestedTabRef.current === nextTab) {
      return;
    }
    requestedTabRef.current = nextTab;
    setSearchParams(withLlmManagementTab(searchParams, nextTab), {
      replace: false,
    });
  };

  return (
    <div className="space-y-3">
      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as LlmManagementTab)}
      >
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 md:grid-cols-4">
          {LLM_MANAGEMENT_TABS.map((item) => (
            <TabsTrigger
              className="min-w-0 justify-center whitespace-nowrap px-2"
              key={item}
              value={item}
            >
              {t(`admin.console.llmManagement.tabs.${item}`)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tab === 'routing' ? (
        <SurfaceCard
          description={t('admin.console.llmManagement.routing.description')}
          title={t('admin.console.llmManagement.routing.title')}
        >
          <AdminLlmRoutingOverview token={token} />
        </SurfaceCard>
      ) : null}
      {tab === 'providers' ? (
        <AdminLlmProviderSettingsSection token={token} />
      ) : null}
      {tab === 'models' ? <AdminAiModelSettingsSection token={token} /> : null}
      {tab === 'images' ? (
        <AdminImageModelSettingsSection token={token} />
      ) : null}
    </div>
  );
}
