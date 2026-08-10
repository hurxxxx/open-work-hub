import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { type OrgUnitItem, UNASSIGNED_ORG_UNIT_ID } from './admin-api';

interface OrgTreeRow {
  item: OrgUnitItem;
  depth: number;
  hasChildren: boolean;
  isExpanded: boolean;
}

export function isDecorativeOrgName(value: string): boolean {
  return /^[\s\-_]+$/.test(value.trim());
}

function orgUnitSortOrder(item: OrgUnitItem): number | null {
  return typeof item.hr_org_order === 'number' ? item.hr_org_order : null;
}

function compareOrgUnits(left: OrgUnitItem, right: OrgUnitItem): number {
  const leftOrder = orgUnitSortOrder(left);
  const rightOrder = orgUnitSortOrder(right);
  if (leftOrder !== null || rightOrder !== null) {
    if (leftOrder === null) return 1;
    if (rightOrder === null) return -1;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
  }

  const leftDecorative = isDecorativeOrgName(left.name);
  const rightDecorative = isDecorativeOrgName(right.name);
  if (leftDecorative !== rightDecorative) {
    return leftDecorative ? 1 : -1;
  }
  return left.name.localeCompare(right.name);
}

function buildOrgTreeRows(
  orgUnits: readonly OrgUnitItem[],
  expandedOrgUnitIds: ReadonlySet<string>,
): OrgTreeRow[] {
  const childrenByParent = new Map<string, OrgUnitItem[]>();
  for (const item of orgUnits) {
    const parentId = item.parent_id ?? '';
    childrenByParent.set(parentId, [
      ...(childrenByParent.get(parentId) ?? []),
      item,
    ]);
  }
  for (const children of childrenByParent.values()) {
    children.sort(compareOrgUnits);
  }

  const rows: OrgTreeRow[] = [];
  const visit = (items: OrgUnitItem[], depth: number) => {
    for (const item of items) {
      const children = childrenByParent.get(item.id) ?? [];
      const isExpanded = expandedOrgUnitIds.has(item.id);
      rows.push({
        item,
        depth,
        hasChildren: children.length > 0,
        isExpanded,
      });
      if (isExpanded) {
        visit(children, depth + 1);
      }
    }
  };
  visit(childrenByParent.get('') ?? [], 0);
  return rows;
}

export function OrgSourceBadge({
  sourceType,
}: {
  sourceType: OrgUnitItem['source_type'];
}) {
  const { t } = useTranslation('apps');
  if (sourceType === 'groupware') {
    return null;
  }

  return (
    <span className="app-text-caption shrink-0 rounded border border-app-border bg-app-surface-sidebar px-1.5 py-0.5 text-app-ink/50">
      {t('admin.console.people.source.manual')}
    </span>
  );
}

export function OrgTreePanel({
  includeDescendants,
  includeInactiveOrgUnits,
  onIncludeDescendantsChange,
  onIncludeInactiveOrgUnitsChange,
  onSelectOrgUnit,
  orgUnits,
  selectedOrgUnitId,
  totalUsers,
}: {
  includeDescendants: boolean;
  includeInactiveOrgUnits: boolean;
  onIncludeDescendantsChange: (includeDescendants: boolean) => void;
  onIncludeInactiveOrgUnitsChange: (includeInactiveOrgUnits: boolean) => void;
  onSelectOrgUnit: (orgUnitId: string) => void;
  orgUnits: readonly OrgUnitItem[];
  selectedOrgUnitId: string;
  totalUsers: number;
}) {
  const { t } = useTranslation('apps');
  const [expandedOrgUnitIds, setExpandedOrgUnitIds] = useState<Set<string>>(
    () => new Set(),
  );
  const hrRows = useMemo(
    () =>
      buildOrgTreeRows(
        orgUnits.filter((item) => item.source_type === 'groupware'),
        expandedOrgUnitIds,
      ),
    [expandedOrgUnitIds, orgUnits],
  );
  const internalRows = useMemo(
    () =>
      buildOrgTreeRows(
        orgUnits.filter((item) => item.source_type !== 'groupware'),
        expandedOrgUnitIds,
      ),
    [expandedOrgUnitIds, orgUnits],
  );
  const allOrgsSelected = !selectedOrgUnitId;
  const unassignedSelected = selectedOrgUnitId === UNASSIGNED_ORG_UNIT_ID;
  const toggleOrgExpanded = useCallback((orgUnitId: string) => {
    setExpandedOrgUnitIds((current) => {
      const next = new Set(current);
      if (next.has(orgUnitId)) {
        next.delete(orgUnitId);
      } else {
        next.add(orgUnitId);
      }
      return next;
    });
  }, []);
  const renderUnassignedRow = () => (
    <div
      className={`group relative flex items-center transition-colors ${
        unassignedSelected
          ? 'bg-app-accent/10 text-app-ink'
          : 'text-app-ink/85 hover:bg-app-surface-sidebar'
      }`}
    >
      {unassignedSelected ? (
        <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
      ) : null}
      <span className="ml-2 h-7 w-5 shrink-0" />
      <button
        className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-3 text-left"
        onClick={() => onSelectOrgUnit(UNASSIGNED_ORG_UNIT_ID)}
        type="button"
      >
        <span className="app-text-body-sm min-w-0 truncate font-medium text-app-ink">
          {t('admin.console.people.unassignedOrg')}
        </span>
      </button>
    </div>
  );
  const renderOrgRows = (rows: OrgTreeRow[]) =>
    rows.map(({ item, depth, hasChildren, isExpanded }) => {
      const rowSelected = selectedOrgUnitId === item.id;
      const isDecorative = isDecorativeOrgName(item.name);
      const orgName = isDecorative
        ? t('admin.console.people.orgTreeSeparator')
        : item.name;

      if (isDecorative) {
        return (
          <div
            aria-label={orgName}
            className="flex h-8 items-center pr-3"
            key={item.id}
            role="separator"
            style={{ paddingLeft: `${16 + depth * 14}px` }}
          >
            <span className="h-px flex-1 border-t border-dashed border-app-ink/30" />
          </div>
        );
      }

      return (
        <div
          className={`group relative flex items-center transition-colors ${
            rowSelected
              ? 'bg-app-accent/10 text-app-ink'
              : item.active
                ? 'text-app-ink/85 hover:bg-app-surface-sidebar'
                : 'text-app-ink/45 hover:bg-app-surface-sidebar'
          }`}
          key={item.id}
        >
          {rowSelected ? (
            <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
          ) : null}
          {hasChildren ? (
            <button
              aria-label={
                isExpanded
                  ? t('admin.console.people.collapseOrg', {
                      name: orgName,
                    })
                  : t('admin.console.people.expandOrg', {
                      name: orgName,
                    })
              }
              className="ml-2 flex h-7 w-5 shrink-0 items-center justify-center rounded text-app-ink/40 hover:text-app-ink"
              onClick={() => toggleOrgExpanded(item.id)}
              style={{ marginLeft: `${8 + depth * 14}px` }}
              type="button"
            >
              {isExpanded ? (
                <ChevronDown aria-hidden className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight aria-hidden className="h-3.5 w-3.5" />
              )}
            </button>
          ) : (
            <span
              className="ml-2 h-7 w-5 shrink-0"
              style={{ marginLeft: `${8 + depth * 14}px` }}
            />
          )}
          <button
            className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-3 text-left"
            onClick={() => onSelectOrgUnit(item.id)}
            type="button"
          >
            <span
              className={`app-text-body-sm min-w-0 truncate font-medium ${
                item.active ? 'text-app-ink' : 'text-app-ink/45'
              }`}
            >
              {orgName}
            </span>
            <OrgSourceBadge sourceType={item.source_type} />
            {!item.active ? (
              <span className="app-text-micro shrink-0 rounded border border-app-warning-border bg-app-warning/10 px-1.5 py-0.5 text-app-warning-text dark:text-app-warning-text">
                {t('admin.console.people.inactiveOrgUnit')}
              </span>
            ) : null}
          </button>
        </div>
      );
    });

  return (
    <aside className="flex h-[calc(100vh-210px)] min-h-[520px] min-w-0 flex-col overflow-hidden rounded-md border border-app-border bg-app-bg">
      <div className="flex items-center justify-between gap-2 border-b border-app-border px-3 py-2">
        <h2 className="app-text-overline uppercase tracking-wide text-app-ink/60">
          {t('admin.console.people.orgTree')} · {orgUnits.length}
        </h2>
      </div>
      <div className="space-y-1.5 px-3 py-2">
        <label className="app-text-body-sm flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/70">
          <input
            checked={includeDescendants}
            className="h-3 w-3 accent-app-accent"
            onChange={(event) =>
              onIncludeDescendantsChange(event.target.checked)
            }
            type="checkbox"
          />
          <span>{t('admin.console.people.includeDescendants')}</span>
        </label>
        <label className="app-text-body-sm flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/70">
          <input
            checked={includeInactiveOrgUnits}
            className="h-3 w-3 accent-app-accent"
            onChange={(event) =>
              onIncludeInactiveOrgUnitsChange(event.target.checked)
            }
            type="checkbox"
          />
          <span>{t('admin.console.people.includeInactiveOrgUnits')}</span>
        </label>
      </div>
      <button
        className={`relative flex w-full items-center justify-between gap-2 border-t border-app-border px-3 py-2 text-left transition-colors ${
          allOrgsSelected
            ? 'bg-app-accent/10 text-app-ink'
            : 'text-app-ink/80 hover:bg-app-surface-sidebar'
        }`}
        onClick={() => onSelectOrgUnit('')}
        type="button"
      >
        {allOrgsSelected ? (
          <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r bg-app-accent" />
        ) : null}
        <span className="app-text-body-sm font-medium">
          {t('admin.console.people.orgTreeAll')}
        </span>
        <span className="app-text-caption text-app-ink/50">{totalUsers}</span>
      </button>
      <div className="min-h-0 flex-1 overflow-y-auto pb-1">
        {hrRows.length > 0 ? (
          <div className="border-t border-app-border/70 pt-2">
            <div className="app-text-micro px-3 pb-1 text-app-ink/45">
              {t('admin.console.people.hrOrgSection')}
            </div>
            {renderOrgRows(hrRows)}
          </div>
        ) : null}
        <div className="mt-1 border-t border-app-border/70 pt-2">
          <div className="app-text-micro px-3 pb-1 text-app-ink/45">
            {t('admin.console.people.internalOrgSection')}
          </div>
          {renderUnassignedRow()}
          {renderOrgRows(internalRows)}
        </div>
      </div>
    </aside>
  );
}
