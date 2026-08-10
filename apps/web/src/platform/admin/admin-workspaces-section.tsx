import type { ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Plus, Search } from 'lucide-react';

import {
  Button,
  Dialog,
  InlineNotice,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@open-work-hub/ui';

import { createWorkspace, listWorkspaces, type WorkspaceItem } from './admin-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  filterAdminWorkspaces,
  replaceAdminWorkspace,
  selectWorkspaceIdAfterLoad,
  type WorkspaceFilter,
} from './admin-workspaces-model';
import { WorkspaceDetailPanel } from './workspace-detail-panel';
import {
  FORM_FIELD_CLASS as fieldClassName,
  SectionMessage,
  getErrorMessage,
} from './admin-shared';

function WorkspaceListItemMeta({
  className = '',
  t,
  workspace,
}: {
  className?: string;
  t: TFunction;
  workspace: Pick<WorkspaceItem, 'key' | 'member_count'>;
}) {
  const memberCountLabel = t('admin.console.workspaces.memberCount', {
    count: workspace.member_count,
  });
  return (
    <div
      className={`app-text-caption flex min-w-0 items-center gap-1 text-app-ink/50 ${className}`}
      title={`${workspace.key} · ${memberCountLabel}`}
    >
      <span className="min-w-0 truncate">{workspace.key}</span>
      <span aria-hidden="true" className="shrink-0 text-app-ink/35">
        ·
      </span>
      <span className="shrink-0 whitespace-nowrap">{memberCountLabel}</span>
    </div>
  );
}

function CreateWorkspaceModal({
  open,
  onOpenChange,
  onCreate,
  busy,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (payload: { name: string; description: string }) => Promise<void>;
  busy: boolean;
  error: string | null;
}) {
  const { t } = useTranslation('apps');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    await onCreate({ name: trimmed, description: description.trim() });
  };

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.console.workspaces.createTitle')}
      description={t('admin.console.workspaces.createDescription')}
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {t('common:actions.cancel')}
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="create-workspace-form"
            disabled={busy || !name.trim()}
          >
            {busy
              ? t('admin.console.workspaces.creating')
              : t('admin.console.workspaces.createAction')}
          </Button>
        </>
      }
    >
      <form
        id="create-workspace-form"
        className="grid gap-4"
        onSubmit={(e) => void handleSubmit(e)}
      >
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.workspace.nameLabel')}
          </span>
          <input
            className={fieldClassName}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('admin.console.workspaces.namePlaceholder')}
            maxLength={120}
          />
        </label>
        <label className="grid gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.console.workspaces.descriptionOptional')}
          </span>
          <textarea
            className={`${fieldClassName} min-h-[88px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={t('admin.console.workspaces.descriptionPlaceholder')}
            maxLength={1000}
          />
        </label>
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <p className="app-text-caption text-app-ink/60">
          {t('admin.console.workspaces.appToggleHint')}
        </p>
      </form>
    </Dialog>
  );
}

export function WorkspacesSection(props: { token: string }) {
  return <>{useWorkspacesSectionElement(props)}</>;
}

function useWorkspacesSectionElement({ token }: { token: string }): ReactNode {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const auth = useAuth();
  const currentUserId = auth.user?.id ?? '';
  const canCreateWorkspaces = auth.hasPermission('workspace.write');
  const canManage = canCreateWorkspaces;

  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [filter, setFilter] = useState<WorkspaceFilter>('active');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const flashSuccess = useCallback((text: string) => {
    setError(null);
    setMessage(text);
    window.setTimeout(() => setMessage(null), 3500);
  }, []);

  const flashError = useCallback((text: string) => {
    setMessage(null);
    setError(text);
  }, []);

  const reloadWorkspaces = useCallback(
    async (preserveSelection?: string | null) => {
      try {
        const items = await listWorkspaces(token, { includeArchived: true });
        setWorkspaces(items);
        setSelectedWorkspaceId((current) =>
          selectWorkspaceIdAfterLoad({
            currentWorkspaceId: current,
            preserveWorkspaceId: preserveSelection,
            workspaces: items,
          }),
        );
      } catch (caughtError) {
        flashError(
          getErrorMessage(
            caughtError,
            t('admin.console.workspaces.listLoadFailed'),
          ),
        );
      }
    },
    [token, flashError, t],
  );

  useEffect(() => {
    void (async () => {
      try {
        const workspaceItems = await listWorkspaces(token, {
          includeArchived: true,
        });
        setWorkspaces(workspaceItems);
        setSelectedWorkspaceId(
          selectWorkspaceIdAfterLoad({ workspaces: workspaceItems }),
        );
      } catch (caughtError) {
        flashError(
          getErrorMessage(
            caughtError,
            t('admin.console.workspaces.infoLoadFailed'),
          ),
        );
      }
    })();
  }, [token, flashError, t]);

  const selectedWorkspace = useMemo(
    () => workspaces.find((item) => item.id === selectedWorkspaceId) ?? null,
    [selectedWorkspaceId, workspaces],
  );

  const filteredWorkspaces = useMemo(() => {
    return filterAdminWorkspaces({
      filter,
      locale,
      searchQuery,
      workspaces,
    });
  }, [workspaces, filter, searchQuery, locale]);

  async function handleCreateWorkspace(payload: {
    name: string;
    description: string;
  }) {
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createWorkspace(token, payload);
      setCreateOpen(false);
      await reloadWorkspaces(created.id);
      flashSuccess(
        t('admin.console.workspaces.created', { name: created.name }),
      );
    } catch (caughtError) {
      setCreateError(
        getErrorMessage(
          caughtError,
          t('admin.console.workspaces.createFailed'),
        ),
      );
    } finally {
      setCreateBusy(false);
    }
  }

  const handleWorkspaceChanged = useCallback((next: WorkspaceItem) => {
    setWorkspaces((current) => replaceAdminWorkspace(current, next));
  }, []);

  return (
    <div className="space-y-3">
      <SectionMessage error={error} message={message} />

      <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
        <aside className="overflow-hidden rounded-md border border-app-border bg-app-bg">
          <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
            <h2 className="app-text-overline uppercase tracking-wide text-app-ink/60">
              {t('admin.console.sections.workspaces.title')} ·{' '}
              {workspaces.length}
            </h2>
            {canCreateWorkspaces ? (
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="rounded p-1 text-app-ink/60 transition-colors hover:bg-app-surface-sidebar hover:text-app-ink"
                aria-label={t('admin.console.workspaces.createTitle')}
              >
                <Plus size={14} />
              </button>
            ) : null}
          </div>
          <div className="space-y-1.5 px-3 py-2">
            <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1">
              <Search size={12} className="text-app-ink/50" />
              <input
                aria-label={t('admin.console.workspaces.searchPlaceholder')}
                className="app-text-body-sm flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
                placeholder={t('admin.console.workspaces.searchPlaceholder')}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <Tabs
              value={filter}
              onValueChange={(value) => setFilter(value as WorkspaceFilter)}
            >
              <TabsList className="w-full">
                <TabsTrigger className="flex-1" value="active">
                  {t('admin.console.workspaces.filterActive')}
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="archived">
                  {t('admin.console.workspaces.filterArchived')}
                </TabsTrigger>
                <TabsTrigger className="flex-1" value="all">
                  {t('admin.console.workspaces.filterAll')}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <div className="max-h-[640px] overflow-y-auto pb-1">
            {filteredWorkspaces.length === 0 ? (
              <div className="px-3 py-8 text-center text-app-ink/60">
                <p className="app-text-body-sm">
                  {t('admin.console.workspaces.empty')}
                </p>
              </div>
            ) : (
              filteredWorkspaces.map((workspace) => {
                const isSelected = workspace.id === selectedWorkspaceId;
                return (
                  <button
                    key={workspace.id}
                    type="button"
                    onClick={() => setSelectedWorkspaceId(workspace.id)}
                    className={`relative flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors ${
                      isSelected
                        ? 'bg-app-accent/10 text-app-ink'
                        : 'text-app-ink/85 hover:bg-app-surface-sidebar'
                    }`}
                  >
                    {isSelected ? (
                      <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
                    ) : null}
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        workspace.active ? 'bg-app-success' : 'bg-app-ink/30'
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="app-text-body-sm truncate font-medium text-app-ink">
                        {workspace.name}
                      </div>
                      <WorkspaceListItemMeta t={t} workspace={workspace} />
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
          <WorkspaceDetailPanel
            workspace={selectedWorkspace}
            token={token}
            currentUserId={currentUserId}
            capabilities={{
              canEditProfile: canManage,
              canManageMembers: canManage,
              canArchive: canManage,
              canBrowseDirectory: auth.hasPermission('user.read'),
            }}
            onWorkspaceChanged={handleWorkspaceChanged}
            flashSuccess={flashSuccess}
            flashError={flashError}
          />
        </section>
      </div>

      <CreateWorkspaceModal
        key={createOpen ? 'workspace-create-open' : 'workspace-create-closed'}
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleCreateWorkspace}
        busy={createBusy}
        error={createError}
      />
    </div>
  );
}
