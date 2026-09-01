import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, InlineNotice, useFeedback } from '@open-work-hub/ui';

import {
  AdminHermesToolsApiError,
  getAdminHermesInventory,
  getAdminHermesResearchSettings,
  getAdminHermesSummary,
  listAdminHermesProfiles,
  updateAdminHermesResearchSource,
  type AdminHermesInventory,
  type AdminHermesProfile,
  type AdminHermesResearchSettings,
  type AdminHermesResearchSourceId,
  type AdminHermesSummary,
} from './admin-hermes-tools-api';
import {
  Badge,
  BodyCell,
  EmptyPanel,
  EmptyRow,
  HeadCell,
  SurfaceCard,
} from './admin-shared';

function recordString(value: unknown, key: string): string {
  if (!value || typeof value !== 'object') return '';
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === 'string' ? candidate : '';
}

function recordBoolean(value: unknown, key: string, fallback = false): boolean {
  if (!value || typeof value !== 'object') return fallback;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === 'boolean' ? candidate : fallback;
}

function EffectiveStatus({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation('apps');
  return (
    <Badge tone={enabled ? 'green' : 'amber'}>
      {t(
        enabled
          ? 'admin.console.hermesTools.status.enabled'
          : 'admin.console.hermesTools.status.disabled',
      )}
    </Badge>
  );
}

function ResearchSourceTable({
  settings,
  savingSource,
  onToggle,
}: {
  settings: AdminHermesResearchSettings | null;
  savingSource: AdminHermesResearchSourceId | null;
  onToggle: (sourceId: AdminHermesResearchSourceId, enabled: boolean) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] border-collapse">
        <thead>
          <tr>
            <HeadCell dense>
              {t('admin.console.hermesTools.research.columns.source')}
            </HeadCell>
            <HeadCell dense>
              {t('admin.console.hermesTools.research.columns.domains')}
            </HeadCell>
            <HeadCell dense>
              {t('admin.console.hermesTools.research.columns.status')}
            </HeadCell>
            <HeadCell className="text-right" dense>
              {t('admin.console.hermesTools.research.columns.control')}
            </HeadCell>
          </tr>
        </thead>
        <tbody>
          {settings?.sources.map((source) => (
            <tr key={source.id}>
              <BodyCell className="font-medium" dense>
                {source.display_name}
              </BodyCell>
              <BodyCell dense>
                <span className="break-all font-mono text-app-ink/55">
                  {source.domains.join(', ')}
                </span>
              </BodyCell>
              <BodyCell dense>
                <EffectiveStatus enabled={source.enabled} />
              </BodyCell>
              <BodyCell className="text-right" dense>
                <input
                  aria-label={t(
                    'admin.console.hermesTools.research.toggleLabel',
                    { source: source.display_name },
                  )}
                  checked={source.enabled}
                  className="accent-app-accent"
                  disabled={savingSource !== null}
                  onChange={(event) =>
                    onToggle(source.id, event.target.checked)
                  }
                  role="switch"
                  type="checkbox"
                />
              </BodyCell>
            </tr>
          ))}
          {!settings ? (
            <EmptyRow
              colSpan={4}
              description={t(
                'admin.console.hermesTools.research.loadingDescription',
              )}
              title={t('admin.console.hermesTools.research.loadingTitle')}
            />
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function ToolsetTable({
  inventory,
}: {
  inventory: AdminHermesInventory | null;
}) {
  const { t } = useTranslation('apps');
  const toolsets = inventory?.toolsets ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse">
        <thead>
          <tr>
            <HeadCell dense>
              {t('admin.console.hermesTools.toolsets.columns.toolset')}
            </HeadCell>
            <HeadCell dense>
              {t('admin.console.hermesTools.toolsets.columns.enabled')}
            </HeadCell>
            <HeadCell dense>
              {t('admin.console.hermesTools.toolsets.columns.configured')}
            </HeadCell>
            <HeadCell dense>
              {t('admin.console.hermesTools.toolsets.columns.tools')}
            </HeadCell>
          </tr>
        </thead>
        <tbody>
          {toolsets.map((toolset) => {
            const tools = toolset.tools ?? [];
            return (
              <tr key={toolset.name}>
                <BodyCell dense>
                  <div className="font-medium">{toolset.label}</div>
                  <div className="app-text-caption mt-0.5 text-app-ink/50">
                    {toolset.name} · {toolset.description}
                  </div>
                </BodyCell>
                <BodyCell dense>
                  <EffectiveStatus enabled={toolset.enabled} />
                </BodyCell>
                <BodyCell dense>
                  <EffectiveStatus enabled={toolset.configured} />
                </BodyCell>
                <BodyCell dense>
                  <span className="break-words font-mono text-app-ink/60">
                    {tools.length > 0
                      ? tools.join(', ')
                      : t('admin.console.hermesTools.none')}
                  </span>
                </BodyCell>
              </tr>
            );
          })}
          {!inventory || toolsets.length === 0 ? (
            <EmptyRow
              colSpan={4}
              description={t(
                inventory
                  ? 'admin.console.hermesTools.toolsets.emptyDescription'
                  : 'admin.console.hermesTools.toolsets.loadingDescription',
              )}
              title={t(
                inventory
                  ? 'admin.console.hermesTools.toolsets.emptyTitle'
                  : 'admin.console.hermesTools.toolsets.loadingTitle',
              )}
            />
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function ExtensionTable({ title, rows }: { title: string; rows: unknown[] }) {
  const { t } = useTranslation('apps');
  if (rows.length === 0) {
    return (
      <EmptyPanel
        description={t('admin.console.hermesTools.extensions.emptyDescription')}
        title={title}
      />
    );
  }
  return (
    <section className="space-y-2">
      <h3 className="app-text-label text-app-ink">{title}</h3>
      <div className="divide-y divide-app-border border-y border-app-border">
        {rows.map((row, index) => {
          const name = recordString(row, 'name') || `#${index + 1}`;
          const enabled = recordBoolean(row, 'enabled', true);
          return (
            <div
              className="flex items-center justify-between gap-3 py-2"
              key={`${name}:${index}`}
            >
              <span className="app-text-body-sm break-all text-app-ink">
                {name}
              </span>
              <EffectiveStatus enabled={enabled} />
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function AdminHermesToolsSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [summary, setSummary] = useState<AdminHermesSummary | null>(null);
  const [profiles, setProfiles] = useState<AdminHermesProfile[]>([]);
  const [researchSettings, setResearchSettings] =
    useState<AdminHermesResearchSettings | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [inventory, setInventory] = useState<AdminHermesInventory | null>(null);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [savingSource, setSavingSource] =
    useState<AdminHermesResearchSourceId | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    void Promise.all([
      getAdminHermesSummary(token),
      listAdminHermesProfiles(token),
      getAdminHermesResearchSettings(token),
    ])
      .then(([nextSummary, profileList, nextResearchSettings]) => {
        if (cancelled) return;
        setSummary(nextSummary);
        setProfiles(profileList.data);
        setResearchSettings(nextResearchSettings);
        setSelectedProfileId((current) => {
          if (profileList.data.some((profile) => profile.id === current)) {
            return current;
          }
          return (
            profileList.data.find((profile) => profile.status === 'active')
              ?.id ??
            profileList.data[0]?.id ??
            ''
          );
        });
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshRevision, token]);

  useEffect(() => {
    if (!selectedProfileId) {
      setInventory(null);
      return;
    }
    let cancelled = false;
    setInventoryLoading(true);
    setInventory(null);
    void getAdminHermesInventory(token, selectedProfileId)
      .then((nextInventory) => {
        if (!cancelled) setInventory(nextInventory);
      })
      .catch(() => {
        if (!cancelled) {
          feedback.error(t('admin.console.hermesTools.inventoryLoadFailed'));
        }
      })
      .finally(() => {
        if (!cancelled) setInventoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [feedback, refreshRevision, selectedProfileId, t, token]);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedProfileId) ?? null,
    [profiles, selectedProfileId],
  );

  const toggleResearchSource = useCallback(
    async (sourceId: AdminHermesResearchSourceId, enabled: boolean) => {
      if (!researchSettings) return;
      setSavingSource(sourceId);
      try {
        const updated = await updateAdminHermesResearchSource(
          token,
          sourceId,
          enabled,
          researchSettings.revision,
        );
        setResearchSettings(updated);
        feedback.success(t('admin.console.hermesTools.research.saved'));
      } catch (error) {
        if (error instanceof AdminHermesToolsApiError && error.status === 409) {
          feedback.info(t('admin.console.hermesTools.research.conflict'));
          setResearchSettings(await getAdminHermesResearchSettings(token));
        } else {
          feedback.error(t('admin.console.hermesTools.research.saveFailed'));
        }
      } finally {
        setSavingSource(null);
      }
    },
    [feedback, researchSettings, t, token],
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-3">
        <p className="app-text-body-sm text-app-ink/55">
          {summary
            ? t('admin.console.hermesTools.runtimeSummary', {
                fallback: summary.fallback_model,
                model: summary.model,
                release: summary.release,
              })
            : t('admin.console.hermesTools.loading')}
        </p>
        <Button
          disabled={loading || inventoryLoading}
          onClick={() => setRefreshRevision((value) => value + 1)}
          size="dense"
          variant="secondary"
        >
          <RefreshCw
            className={loading || inventoryLoading ? 'animate-spin' : ''}
            size={14}
          />
          {t('admin.console.hermesTools.refresh')}
        </Button>
      </div>

      {loadError ? (
        <InlineNotice role="alert" tone="danger">
          {t('admin.console.hermesTools.loadFailed')}
        </InlineNotice>
      ) : null}

      <SurfaceCard
        description={t('admin.console.hermesTools.research.description')}
        title={t('admin.console.hermesTools.research.title')}
      >
        <div className="space-y-3">
          <InlineNotice tone="info">
            {t('admin.console.hermesTools.research.applicationNote')}
          </InlineNotice>
          <ResearchSourceTable
            onToggle={(sourceId, enabled) =>
              void toggleResearchSource(sourceId, enabled)
            }
            savingSource={savingSource}
            settings={researchSettings}
          />
        </div>
      </SurfaceCard>

      <SurfaceCard
        actions={
          profiles.length > 0 ? (
            <label className="flex items-center gap-2">
              <span className="app-text-caption text-app-ink/55">
                {t('admin.console.hermesTools.profile')}
              </span>
              <select
                aria-label={t('admin.console.hermesTools.profile')}
                className="h-8 max-w-[320px] rounded-md border border-app-border bg-app-surface px-2 app-text-body-sm text-app-ink"
                onChange={(event) => setSelectedProfileId(event.target.value)}
                value={selectedProfileId}
              >
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.profile_name} · {profile.status}
                  </option>
                ))}
              </select>
            </label>
          ) : null
        }
        description={t('admin.console.hermesTools.toolsets.description')}
        title={t('admin.console.hermesTools.toolsets.title')}
      >
        {profiles.length === 0 && !loading ? (
          <EmptyPanel
            description={t(
              'admin.console.hermesTools.profilesEmptyDescription',
            )}
            title={t('admin.console.hermesTools.profilesEmptyTitle')}
          />
        ) : (
          <div className="space-y-5">
            {selectedProfile ? (
              <div className="app-text-caption text-app-ink/50">
                {selectedProfile.profile_name} · {selectedProfile.provider}/
                {selectedProfile.model}
              </div>
            ) : null}
            <ToolsetTable inventory={inventory} />
            {inventory ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <ExtensionTable
                  rows={inventory.mcp_servers ?? []}
                  title={t('admin.console.hermesTools.extensions.mcp')}
                />
                <ExtensionTable
                  rows={inventory.skills ?? []}
                  title={t('admin.console.hermesTools.extensions.skills')}
                />
              </div>
            ) : null}
          </div>
        )}
      </SurfaceCard>
    </div>
  );
}
