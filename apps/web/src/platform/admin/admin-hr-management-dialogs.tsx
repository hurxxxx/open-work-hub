import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Link2,
  Pencil,
  Plus,
  Search,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  Badge,
  Button,
  Dialog,
  InlineNotice,
  Input,
  SearchField,
} from '@open-alm/ui';

import { cn } from '@/src/lib/utils';

import {
  archiveAdminHrWorkforceCategory,
  createAdminHrManualMatch,
  createAdminHrWorkforceCategory,
  listAdminHrManualMatchCandidates,
  updateAdminHrWorkforceCategory,
  type AdminHrManualMatchDirectoryItem,
  type AdminHrManualMatchDirectoryResponse,
  type AdminHrManualMatchMutationResponse,
  type AdminHrWorkforceCategoryItem,
} from './admin-api';
import { getErrorMessage } from './admin-shared';

const MAPPING_PAGE_SIZE = 12;

function CandidateList({
  error,
  loading,
  onPageChange,
  onQueryChange,
  onSelect,
  page,
  query,
  response,
  selectedId,
  source,
}: {
  error: string | null;
  loading: boolean;
  onPageChange: (page: number) => void;
  onQueryChange: (query: string) => void;
  onSelect: (item: AdminHrManualMatchDirectoryItem) => void;
  page: number;
  query: string;
  response: AdminHrManualMatchDirectoryResponse | null;
  selectedId?: string;
  source: 'erp' | 'groupware';
}) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const total = response?.total ?? 0;
  const hasNext = page * MAPPING_PAGE_SIZE < total;

  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-app-border bg-app-surface">
      <div className="border-b border-app-border bg-app-surface-sidebar px-4 py-3">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge tone={source === 'erp' ? 'accent' : 'neutral'}>
              {t(`admin.console.hrMaster.sources.${source}`)}
            </Badge>
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.mapping.availableCount', {
                count: new Intl.NumberFormat(locale).format(total),
              })}
            </span>
          </div>
        </div>
        <SearchField
          aria-label={t(`admin.console.hrMaster.mapping.${source}SearchLabel`)}
          endAdornment={<Search aria-hidden="true" size={15} />}
          maxLength={120}
          onChange={(event) => {
            onQueryChange(event.target.value);
            onPageChange(1);
          }}
          placeholder={t(
            `admin.console.hrMaster.mapping.${source}SearchPlaceholder`,
          )}
          value={query}
        />
      </div>
      <div className="ui-scrollbar min-h-[310px] flex-1 overflow-y-auto p-2">
        {loading ? (
          <output className="block px-3 py-8 text-center app-text-body-sm text-app-ink/50">
            {t('admin.console.hrMaster.mapping.loading')}
          </output>
        ) : error ? (
          <div className="p-3">
            <InlineNotice role="alert" tone="danger">
              {error}
            </InlineNotice>
          </div>
        ) : response?.items.length ? (
          <div className="grid gap-1.5">
            {response.items.map((item) => {
              const selected = item.record_id === selectedId;
              return (
                <button
                  aria-pressed={selected}
                  className={cn(
                    'grid w-full gap-1 rounded-lg border px-3 py-2.5 text-left transition-colors',
                    selected
                      ? 'border-app-accent bg-app-accent/10'
                      : 'border-transparent hover:border-app-border hover:bg-app-surface-sidebar',
                  )}
                  key={item.record_id}
                  onClick={() => onSelect(item)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="app-text-control text-app-ink">
                      {item.name}
                    </span>
                    <span className="app-text-caption font-mono text-app-ink/60">
                      {item.employee_code}
                    </span>
                  </div>
                  <div className="app-text-caption truncate text-app-ink/50">
                    {[item.group_name, item.position, item.login_id, item.email]
                      .filter(Boolean)
                      .join(' · ') || '-'}
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="px-3 py-8 text-center app-text-body-sm text-app-ink/50">
            {t('admin.console.hrMaster.mapping.noCandidates')}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between border-t border-app-border px-3 py-2">
        <Button
          aria-label={t('admin.console.hrMaster.pagination.previous')}
          disabled={loading || page <= 1}
          onClick={() => onPageChange(Math.max(1, page - 1))}
          size="icon"
          variant="ghost"
        >
          <ArrowLeft aria-hidden="true" size={15} />
        </Button>
        <span className="app-text-caption text-app-ink/50">
          {t('admin.console.hrMaster.mapping.page', { page })}
        </span>
        <Button
          aria-label={t('admin.console.hrMaster.pagination.next')}
          disabled={loading || !hasNext}
          onClick={() => onPageChange(page + 1)}
          size="icon"
          variant="ghost"
        >
          <ArrowRight aria-hidden="true" size={15} />
        </Button>
      </div>
    </section>
  );
}

export function AdminHrMappingDialog({
  initialErp,
  initialGroupware,
  masterRunId,
  onCompleted,
  onOpenChange,
  open,
  token,
}: {
  initialErp?: AdminHrManualMatchDirectoryItem | null;
  initialGroupware?: AdminHrManualMatchDirectoryItem | null;
  masterRunId: string | null;
  onCompleted: (result: AdminHrManualMatchMutationResponse) => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const [erpQuery, setErpQuery] = useState('');
  const [groupwareQuery, setGroupwareQuery] = useState('');
  const [erpPage, setErpPage] = useState(1);
  const [groupwarePage, setGroupwarePage] = useState(1);
  const [erpResponse, setErpResponse] =
    useState<AdminHrManualMatchDirectoryResponse | null>(null);
  const [groupwareResponse, setGroupwareResponse] =
    useState<AdminHrManualMatchDirectoryResponse | null>(null);
  const [erpLoading, setErpLoading] = useState(false);
  const [groupwareLoading, setGroupwareLoading] = useState(false);
  const [selectedErp, setSelectedErp] =
    useState<AdminHrManualMatchDirectoryItem | null>(null);
  const [selectedGroupware, setSelectedGroupware] =
    useState<AdminHrManualMatchDirectoryItem | null>(null);
  const [reason, setReason] = useState('');
  const [erpLoadError, setErpLoadError] = useState<string | null>(null);
  const [groupwareLoadError, setGroupwareLoadError] = useState<string | null>(
    null,
  );
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSelectedErp(initialErp ?? null);
    setSelectedGroupware(initialGroupware ?? null);
    setErpQuery('');
    setGroupwareQuery('');
    setErpPage(1);
    setGroupwarePage(1);
    setErpResponse(null);
    setGroupwareResponse(null);
    setReason('');
    setErpLoadError(null);
    setGroupwareLoadError(null);
    setMutationError(null);
    setMessage(null);
    setSubmitted(false);
  }, [initialErp, initialGroupware, open]);

  useEffect(() => {
    if (!open || !masterRunId) {
      return;
    }
    let active = true;
    const timeoutId = window.setTimeout(() => {
      setErpLoading(true);
      setErpLoadError(null);
      void listAdminHrManualMatchCandidates(token, {
        source: 'erp',
        page: erpPage,
        page_size: MAPPING_PAGE_SIZE,
        q: erpQuery,
      })
        .then((response) => {
          if (active) {
            setErpResponse(response);
          }
        })
        .catch((caughtError: unknown) => {
          if (active) {
            setErpLoadError(
              getErrorMessage(
                caughtError,
                t('admin.console.hrMaster.mapping.loadFailed'),
              ),
            );
          }
        })
        .finally(() => {
          if (active) {
            setErpLoading(false);
          }
        });
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [erpPage, erpQuery, masterRunId, open, t, token]);

  useEffect(() => {
    if (!open || !masterRunId) {
      return;
    }
    let active = true;
    const timeoutId = window.setTimeout(() => {
      setGroupwareLoading(true);
      setGroupwareLoadError(null);
      void listAdminHrManualMatchCandidates(token, {
        source: 'groupware',
        page: groupwarePage,
        page_size: MAPPING_PAGE_SIZE,
        q: groupwareQuery,
      })
        .then((response) => {
          if (active) {
            setGroupwareResponse(response);
          }
        })
        .catch((caughtError: unknown) => {
          if (active) {
            setGroupwareLoadError(
              getErrorMessage(
                caughtError,
                t('admin.console.hrMaster.mapping.loadFailed'),
              ),
            );
          }
        })
        .finally(() => {
          if (active) {
            setGroupwareLoading(false);
          }
        });
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [groupwarePage, groupwareQuery, masterRunId, open, t, token]);

  const namesDiffer =
    selectedErp &&
    selectedGroupware &&
    selectedErp.name.trim() !== selectedGroupware.name.trim();
  const canSubmit =
    Boolean(masterRunId && selectedErp && selectedGroupware) &&
    (!namesDiffer || Boolean(reason.trim())) &&
    !submitting &&
    !submitted;

  const handleSubmit = async () => {
    if (!masterRunId || !selectedErp || !selectedGroupware || !canSubmit) {
      return;
    }
    setSubmitting(true);
    setMutationError(null);
    setMessage(null);
    try {
      const result = await createAdminHrManualMatch(token, {
        master_run_id: masterRunId,
        groupware_record_id: selectedGroupware.record_id,
        erp_record_id: selectedErp.record_id,
        reason: reason.trim() || undefined,
      });
      setSubmitted(true);
      setMessage(
        t(
          result.rebuild_queued
            ? 'admin.console.hrMaster.mapping.savedQueued'
            : 'admin.console.hrMaster.mapping.savedNotQueued',
        ),
      );
      onCompleted(result);
    } catch (caughtError) {
      setMutationError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.mapping.saveFailed'),
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      actions={
        <>
          <Button onClick={() => onOpenChange(false)}>
            {t('common:actions.close')}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={() => {
              void handleSubmit();
            }}
            variant="primary"
          >
            <Link2 aria-hidden="true" size={15} />
            {t('admin.console.hrMaster.mapping.create')}
          </Button>
        </>
      }
      closeLabel={t('common:actions.close')}
      contentClassName="h-[88vh]"
      description={t('admin.console.hrMaster.mapping.description')}
      layer="elevated"
      maxWidth="max-w-[1280px]"
      onOpenChange={onOpenChange}
      open={open}
      title={t('admin.console.hrMaster.mapping.title')}
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        <InlineNotice tone="info">
          {t('admin.console.hrMaster.mapping.sourceNotice')}
        </InlineNotice>
        {mutationError ? (
          <InlineNotice role="alert" tone="danger">
            {mutationError}
          </InlineNotice>
        ) : null}
        {message ? (
          <InlineNotice tone={submitted ? 'success' : 'info'}>
            {message}
          </InlineNotice>
        ) : null}
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
          <CandidateList
            error={groupwareLoadError}
            loading={groupwareLoading}
            onPageChange={setGroupwarePage}
            onQueryChange={setGroupwareQuery}
            onSelect={setSelectedGroupware}
            page={groupwarePage}
            query={groupwareQuery}
            response={groupwareResponse}
            selectedId={selectedGroupware?.record_id}
            source="groupware"
          />
          <CandidateList
            error={erpLoadError}
            loading={erpLoading}
            onPageChange={setErpPage}
            onQueryChange={setErpQuery}
            onSelect={setSelectedErp}
            page={erpPage}
            query={erpQuery}
            response={erpResponse}
            selectedId={selectedErp?.record_id}
            source="erp"
          />
        </div>
        <section className="grid gap-3 rounded-xl border border-app-border bg-app-surface-sidebar p-4 lg:grid-cols-[1fr_auto_1fr] lg:items-center">
          <div>
            <div className="app-text-caption text-app-ink/50">
              {t('admin.console.hrMaster.sources.groupware')}
            </div>
            <div className="app-text-control mt-1 text-app-ink">
              {selectedGroupware
                ? `${selectedGroupware.name} · ${selectedGroupware.employee_code}`
                : t('admin.console.hrMaster.mapping.notSelected')}
            </div>
          </div>
          <Link2 aria-hidden="true" className="text-app-accent" size={20} />
          <div>
            <div className="app-text-caption text-app-ink/50">
              {t('admin.console.hrMaster.sources.erp')}
            </div>
            <div className="app-text-control mt-1 text-app-ink">
              {selectedErp
                ? `${selectedErp.name} · ${selectedErp.employee_code}`
                : t('admin.console.hrMaster.mapping.notSelected')}
            </div>
          </div>
          <label className="grid gap-1 lg:col-span-3">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.mapping.reasonLabel')}
            </span>
            <textarea
              className="min-h-20 w-full resize-y rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-body-sm text-app-ink outline-none focus:border-app-accent focus:ring-2 focus:ring-app-accent/10"
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t(
                namesDiffer
                  ? 'admin.console.hrMaster.mapping.reasonRequiredPlaceholder'
                  : 'admin.console.hrMaster.mapping.reasonPlaceholder',
              )}
              value={reason}
            />
          </label>
          {namesDiffer && !reason.trim() ? (
            <p className="app-text-caption text-app-danger lg:col-span-3">
              {t('admin.console.hrMaster.mapping.differentNameReason')}
            </p>
          ) : null}
        </section>
      </div>
    </Dialog>
  );
}

export function AdminHrCategoryManagerDialog({
  categories,
  onChanged,
  onOpenChange,
  open,
  token,
}: {
  categories: AdminHrWorkforceCategoryItem[];
  onChanged: () => Promise<void>;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const sortedCategories = useMemo(
    () =>
      [...categories].sort(
        (left, right) =>
          left.sort_order - right.sort_order ||
          left.name.localeCompare(right.name),
      ),
    [categories],
  );

  const refreshAfterMutation = async () => {
    try {
      await onChanged();
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.categoryManager.refreshFailed'),
        ),
      );
    }
  };

  const handleCreate = async () => {
    if (!createName.trim()) {
      return;
    }
    setMutating(true);
    setError(null);
    setMessage(null);
    try {
      await createAdminHrWorkforceCategory(token, {
        name: createName.trim(),
        description: createDescription.trim() || undefined,
      });
      setCreateName('');
      setCreateDescription('');
      setMessage(t('admin.console.hrMaster.categoryManager.created'));
      await refreshAfterMutation();
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.categoryManager.createFailed'),
        ),
      );
    } finally {
      setMutating(false);
    }
  };

  const handleUpdate = async (category: AdminHrWorkforceCategoryItem) => {
    if (!editName.trim()) {
      return;
    }
    setMutating(true);
    setError(null);
    setMessage(null);
    try {
      await updateAdminHrWorkforceCategory(token, category.code, {
        name: editName.trim(),
        description: editDescription.trim() || null,
      });
      setEditingCode(null);
      setMessage(t('admin.console.hrMaster.categoryManager.updated'));
      await refreshAfterMutation();
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.categoryManager.updateFailed'),
        ),
      );
    } finally {
      setMutating(false);
    }
  };

  const handleToggleActive = async (category: AdminHrWorkforceCategoryItem) => {
    setMutating(true);
    setError(null);
    setMessage(null);
    try {
      if (category.is_active) {
        await archiveAdminHrWorkforceCategory(token, category.code);
      } else {
        await updateAdminHrWorkforceCategory(token, category.code, {
          is_active: true,
        });
      }
      setMessage(
        t(
          category.is_active
            ? 'admin.console.hrMaster.categoryManager.archivedSuccess'
            : 'admin.console.hrMaster.categoryManager.restoredSuccess',
        ),
      );
      await refreshAfterMutation();
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.categoryManager.archiveFailed'),
        ),
      );
    } finally {
      setMutating(false);
    }
  };

  return (
    <Dialog
      actions={
        <Button onClick={() => onOpenChange(false)}>
          {t('common:actions.close')}
        </Button>
      }
      closeLabel={t('common:actions.close')}
      description={t('admin.console.hrMaster.categoryManager.description')}
      maxWidth="max-w-4xl"
      onOpenChange={onOpenChange}
      open={open}
      title={t('admin.console.hrMaster.categoryManager.title')}
    >
      <div className="space-y-4">
        {error ? (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        ) : null}
        {message ? <InlineNotice tone="success">{message}</InlineNotice> : null}
        <section className="grid gap-3 rounded-xl border border-app-border bg-app-surface-sidebar p-4 md:grid-cols-[220px_minmax(0,1fr)_auto] md:items-end">
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.categoryManager.nameLabel')}
            </span>
            <Input
              maxLength={120}
              onChange={(event) => setCreateName(event.target.value)}
              placeholder={t(
                'admin.console.hrMaster.categoryManager.namePlaceholder',
              )}
              value={createName}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.categoryManager.descriptionLabel')}
            </span>
            <Input
              maxLength={500}
              onChange={(event) => setCreateDescription(event.target.value)}
              placeholder={t(
                'admin.console.hrMaster.categoryManager.descriptionPlaceholder',
              )}
              value={createDescription}
            />
          </label>
          <Button
            disabled={mutating || !createName.trim()}
            onClick={() => {
              void handleCreate();
            }}
            variant="primary"
          >
            <Plus aria-hidden="true" size={15} />
            {t('admin.console.hrMaster.categoryManager.add')}
          </Button>
        </section>
        <div
          className="overflow-x-auto rounded-xl border border-app-border"
          role="table"
        >
          <div className="min-w-[680px]">
            <div
              className="grid grid-cols-[minmax(150px,220px)_minmax(180px,1fr)_110px_150px] gap-3 border-b border-app-border bg-app-surface-sidebar px-4 py-2 app-text-caption text-app-ink/50"
              role="row"
            >
              <span role="columnheader">
                {t('admin.console.hrMaster.categoryManager.nameLabel')}
              </span>
              <span role="columnheader">
                {t('admin.console.hrMaster.categoryManager.descriptionLabel')}
              </span>
              <span role="columnheader">
                {t('admin.console.hrMaster.categoryManager.statusLabel')}
              </span>
              <span className="text-right" role="columnheader">
                {t('admin.console.hrMaster.categoryManager.actionsLabel')}
              </span>
            </div>
            <div className="divide-y divide-app-border" role="rowgroup">
              {sortedCategories.map((category) => {
                const editing = editingCode === category.code;
                return (
                  <div
                    className="grid grid-cols-[minmax(150px,220px)_minmax(180px,1fr)_110px_150px] items-center gap-3 px-4 py-2.5"
                    key={category.code}
                    role="row"
                  >
                    <div role="cell">
                      {editing ? (
                        <Input
                          maxLength={120}
                          onChange={(event) => setEditName(event.target.value)}
                          value={editName}
                        />
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="app-text-control text-app-ink">
                            {category.name}
                          </span>
                          {category.is_system ? (
                            <Badge tone="neutral">
                              {t(
                                'admin.console.hrMaster.categoryManager.system',
                              )}
                            </Badge>
                          ) : null}
                        </div>
                      )}
                    </div>
                    <div role="cell">
                      {editing ? (
                        <Input
                          maxLength={500}
                          onChange={(event) =>
                            setEditDescription(event.target.value)
                          }
                          value={editDescription}
                        />
                      ) : (
                        <span className="app-text-body-sm text-app-ink/55">
                          {category.description || '-'}
                        </span>
                      )}
                    </div>
                    <div role="cell">
                      <Badge tone={category.is_active ? 'success' : 'neutral'}>
                        {t(
                          category.is_active
                            ? 'admin.console.hrMaster.categoryManager.active'
                            : 'admin.console.hrMaster.categoryManager.archived',
                        )}
                      </Badge>
                    </div>
                    <div className="flex justify-end gap-1" role="cell">
                      {editing ? (
                        <>
                          <Button
                            disabled={mutating}
                            onClick={() => setEditingCode(null)}
                            variant="ghost"
                          >
                            {t('common:actions.cancel')}
                          </Button>
                          <Button
                            disabled={mutating || !editName.trim()}
                            onClick={() => {
                              void handleUpdate(category);
                            }}
                            variant="primary"
                          >
                            {t('common:actions.save')}
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            aria-label={t(
                              'admin.console.hrMaster.categoryManager.edit',
                              { name: category.name },
                            )}
                            disabled={mutating}
                            onClick={() => {
                              setEditingCode(category.code);
                              setEditName(category.name);
                              setEditDescription(category.description ?? '');
                            }}
                            size="icon"
                            variant="ghost"
                          >
                            <Pencil aria-hidden="true" size={14} />
                          </Button>
                          {!category.is_system ? (
                            <Button
                              disabled={mutating}
                              onClick={() => {
                                void handleToggleActive(category);
                              }}
                              variant="subtle"
                            >
                              {t(
                                category.is_active
                                  ? 'admin.console.hrMaster.categoryManager.archive'
                                  : 'admin.console.hrMaster.categoryManager.restore',
                              )}
                            </Button>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
