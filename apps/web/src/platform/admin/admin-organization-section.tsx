import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  Button,
  ContentState,
  ContextNote,
  Dialog,
  FormMessage,
  useFeedback,
} from '@open-work-hub/ui';

import {
  createOrganizationUnit,
  listOrganizationUnits,
  updateOrganizationUnit,
  type OrganizationUnitItem,
} from './admin-api';
import {
  BodyCell,
  FORM_FIELD_CLASS as fieldClassName,
  HeadCell,
  getErrorMessage,
} from './admin-shared';

import { UserDateTime } from '@/src/components/date/UserDateTime';

interface OrganizationUnitRow {
  depth: number;
  item: OrganizationUnitItem;
}

export function buildOrganizationUnitRows(
  items: readonly OrganizationUnitItem[],
): OrganizationUnitRow[] {
  const children = new Map<string | null, OrganizationUnitItem[]>();
  const ids = new Set(items.map((item) => item.id));
  for (const item of items) {
    const parentId =
      item.parent_id && ids.has(item.parent_id) ? item.parent_id : null;
    const siblings = children.get(parentId) ?? [];
    siblings.push(item);
    children.set(parentId, siblings);
  }
  for (const siblings of children.values()) {
    siblings.sort((left, right) => left.name.localeCompare(right.name));
  }

  const rows: OrganizationUnitRow[] = [];
  const visited = new Set<string>();
  const visit = (item: OrganizationUnitItem, depth: number) => {
    if (visited.has(item.id)) return;
    visited.add(item.id);
    rows.push({ depth, item });
    for (const child of children.get(item.id) ?? []) visit(child, depth + 1);
  };
  for (const item of children.get(null) ?? []) visit(item, 0);
  for (const item of items) visit(item, 0);
  return rows;
}

function descendantIds(
  items: readonly OrganizationUnitItem[],
  organizationUnitId: string,
): Set<string> {
  const descendants = new Set<string>([organizationUnitId]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of items) {
      if (
        item.parent_id &&
        descendants.has(item.parent_id) &&
        !descendants.has(item.id)
      ) {
        descendants.add(item.id);
        changed = true;
      }
    }
  }
  return descendants;
}

export function AdminOrganizationSection({ token }: { token: string }) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [items, setItems] = useState<OrganizationUnitItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<OrganizationUnitItem | null>(null);
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [unitType, setUnitType] = useState('department');
  const [parentId, setParentId] = useState('');
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setItems(await listOrganizationUnits(token, { includeInactive: true }));
    } catch (error) {
      setLoadError(
        getErrorMessage(error, t('admin.console.organization.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => buildOrganizationUnitRows(items), [items]);
  const itemNames = useMemo(
    () => new Map(items.map((item) => [item.id, item.name])),
    [items],
  );
  const excludedParentIds = useMemo(
    () => (editing ? descendantIds(items, editing.id) : new Set<string>()),
    [editing, items],
  );
  const parentOptions = rows.filter(
    ({ item }) =>
      (item.active || item.id === editing?.parent_id) &&
      !excludedParentIds.has(item.id),
  );

  function openCreateDialog() {
    setEditing(null);
    setName('');
    setSlug('');
    setUnitType('department');
    setParentId('');
    setActive(true);
    setFormError(null);
    setDialogOpen(true);
  }

  function openEditDialog(item: OrganizationUnitItem) {
    setEditing(item);
    setName(item.name);
    setSlug(item.slug);
    setUnitType(item.unit_type);
    setParentId(item.parent_id ?? '');
    setActive(item.active);
    setFormError(null);
    setDialogOpen(true);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      if (editing) {
        await updateOrganizationUnit(token, editing.id, {
          active,
          name: name.trim(),
          parent_id: parentId || null,
          slug: slug.trim(),
          unit_type: unitType.trim(),
        });
        feedback.success(t('admin.console.organization.updated'));
      } else {
        await createOrganizationUnit(token, {
          active,
          name: name.trim(),
          parent_id: parentId || null,
          slug: slug.trim() || undefined,
          unit_type: unitType.trim(),
        });
        feedback.success(t('admin.console.organization.created'));
      }
      setDialogOpen(false);
      await load();
    } catch (error) {
      setFormError(
        getErrorMessage(error, t('admin.console.organization.saveFailed')),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <ContextNote
        title={t('admin.console.organization.boundaryTitle')}
        tone="info"
      >
        {t('admin.console.organization.boundaryDescription')}
      </ContextNote>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-app-border pb-4">
        <p className="app-text-body text-app-ink/55">
          {t('admin.console.organization.count', { count: items.length })}
        </p>
        <div className="flex items-center gap-2">
          <Button
            disabled={loading}
            onClick={() => void load()}
            variant="ghost"
          >
            <RefreshCw aria-hidden="true" size={14} />
            {t('common:actions.refresh')}
          </Button>
          <Button onClick={openCreateDialog} variant="primary">
            <Plus aria-hidden="true" size={14} />
            {t('admin.console.organization.create')}
          </Button>
        </div>
      </div>

      {loading ? (
        <ContentState
          kind="loading"
          title={t('admin.console.organization.loadingTitle')}
          description={t('admin.console.organization.loadingDescription')}
        />
      ) : loadError ? (
        <ContentState
          action={{
            label: t('common:actions.retry'),
            onClick: () => void load(),
          }}
          kind="error"
          title={t('admin.console.organization.loadFailed')}
          description={loadError}
        />
      ) : rows.length === 0 ? (
        <ContentState
          action={{
            label: t('admin.console.organization.create'),
            onClick: openCreateDialog,
          }}
          kind="empty"
          title={t('admin.console.organization.emptyTitle')}
          description={t('admin.console.organization.emptyDescription')}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-app-border">
          <table className="w-full border-collapse">
            <thead className="bg-app-surface-sidebar">
              <tr>
                <HeadCell>
                  {t('admin.console.organization.columns.name')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.organization.columns.type')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.organization.columns.slug')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.organization.columns.parent')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.organization.columns.status')}
                </HeadCell>
                <HeadCell>
                  {t('admin.console.organization.columns.updated')}
                </HeadCell>
                <HeadCell className="text-right">
                  {t('admin.console.organization.columns.actions')}
                </HeadCell>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ depth, item }) => (
                <tr className="border-t border-app-border" key={item.id}>
                  <BodyCell>
                    <span
                      className="font-medium text-app-ink"
                      style={{ paddingInlineStart: `${depth * 18}px` }}
                    >
                      {item.name}
                    </span>
                  </BodyCell>
                  <BodyCell className="text-app-ink/55">
                    {item.unit_type}
                  </BodyCell>
                  <BodyCell className="font-mono text-app-ink/55">
                    {item.slug}
                  </BodyCell>
                  <BodyCell className="text-app-ink/55">
                    {item.parent_id
                      ? (itemNames.get(item.parent_id) ??
                        t('admin.console.organization.unknownParent'))
                      : t('admin.console.organization.root')}
                  </BodyCell>
                  <BodyCell>
                    <span className="app-text-caption rounded border border-app-border px-1.5 py-0.5 text-app-ink/65">
                      {item.active
                        ? t('admin.shared.status.active')
                        : t('admin.console.organization.inactive')}
                    </span>
                  </BodyCell>
                  <BodyCell className="whitespace-nowrap text-app-ink/55">
                    <UserDateTime display="datetime" value={item.updated_at} />
                  </BodyCell>
                  <BodyCell className="text-right">
                    <Button
                      onClick={() => openEditDialog(item)}
                      variant="secondary"
                    >
                      {t('common:actions.edit')}
                    </Button>
                  </BodyCell>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog
        actions={
          <>
            <Button
              disabled={saving}
              onClick={() => setDialogOpen(false)}
              variant="secondary"
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              disabled={saving}
              form="organization-unit-form"
              type="submit"
              variant="primary"
            >
              {saving ? t('common:actions.saving') : t('common:actions.save')}
            </Button>
          </>
        }
        closeLabel={t('common:actions.close')}
        description={t('admin.console.organization.formDescription')}
        dismissOnInteractOutside={false}
        onOpenChange={(open) => !saving && setDialogOpen(open)}
        open={dialogOpen}
        title={
          editing
            ? t('admin.console.organization.editTitle')
            : t('admin.console.organization.createTitle')
        }
      >
        <form
          className="grid gap-3"
          id="organization-unit-form"
          onSubmit={(event) => void submit(event)}
        >
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.organization.fields.name')}
            </span>
            <input
              className={fieldClassName}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              required
              value={name}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.organization.fields.slug')}
            </span>
            <input
              className={fieldClassName}
              maxLength={80}
              onChange={(event) => setSlug(event.target.value)}
              placeholder={t('admin.console.organization.slugPlaceholder')}
              required={Boolean(editing)}
              value={slug}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.organization.fields.type')}
            </span>
            <input
              className={fieldClassName}
              maxLength={40}
              onChange={(event) => setUnitType(event.target.value)}
              required
              value={unitType}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.organization.fields.parent')}
            </span>
            <select
              className="app-field-input"
              onChange={(event) => setParentId(event.target.value)}
              value={parentId}
            >
              <option value="">{t('admin.console.organization.root')}</option>
              {parentOptions.map(({ depth, item }) => (
                <option
                  key={item.id}
                  value={item.id}
                >{`${'— '.repeat(depth)}${item.name}${
                  !item.active
                    ? ` (${t('admin.console.organization.inactive')})`
                    : ''
                }`}</option>
              ))}
            </select>
          </label>
          <label className="app-text-control flex items-center gap-2">
            <input
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
              type="checkbox"
            />
            {t('admin.console.organization.fields.active')}
          </label>
          <FormMessage
            id="organization-unit-form-error"
            message={formError}
            variant="form"
          />
        </form>
      </Dialog>
    </div>
  );
}
