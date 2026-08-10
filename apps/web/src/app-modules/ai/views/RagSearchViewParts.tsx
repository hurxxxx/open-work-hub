import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  CalendarDays,
  ExternalLink,
  FileText,
  FolderKanban,
  Search,
  Users,
} from 'lucide-react';

import type {
  KeywordSearchEntityType,
  KeywordSearchHit,
  KeywordSearchSnippet,
} from '@/src/platform/search/search-api';
import { formatDateOnly, formatDateTime } from '@/src/platform/time/time-utils';
import { cn } from '@/src/lib/utils';

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface SearchHitViewModelOptions {
  entityTypeLabels: ReadonlyMap<KeywordSearchEntityType, string>;
  locale: string;
  timeZone: string;
  t: Translate;
}

interface SearchHitViewModel {
  contextItems: SearchContextItem[];
  dateMarkerEntries: PreviewEntry[];
  metadataEntries: PreviewEntry[];
  meta: {
    entityLabel: string;
    statusLabel: string | null;
    visibilityLabel: string | null;
  };
  peopleFields: PreviewFieldViewModel[];
  positionFields: PreviewFieldViewModel[];
  updatedLabel: string;
}

interface SearchContextItem {
  key: string;
  value: string;
}

interface PreviewEntry {
  label: string;
  value: string;
}

interface PreviewFieldViewModel {
  label: string;
  values: string[];
}

export function SearchResultRow({
  entityTypeLabels,
  hit,
  isSelected,
  onSelect,
  timeZone,
}: {
  entityTypeLabels: ReadonlyMap<KeywordSearchEntityType, string>;
  hit: KeywordSearchHit;
  isSelected: boolean;
  onSelect: (hit: KeywordSearchHit) => void;
  timeZone: string;
}) {
  const { t, i18n } = useTranslation('apps');
  const openInNewTab = () => openSearchHitInNewTab(hit);
  const viewModel = buildSearchHitViewModel(hit, {
    entityTypeLabels,
    locale: i18n.language,
    timeZone,
    t,
  });
  const accessibleTitle = `${viewModel.meta.entityLabel} · ${hit.title}`;

  return (
    <div
      className={cn(
        'flex items-stretch gap-2 px-3 py-3 transition-colors',
        isSelected ? 'bg-app-accent/5' : 'hover:bg-app-surface-hover',
      )}
    >
      <button
        aria-label={t('ai.search.selectResult', {
          title: accessibleTitle,
        })}
        aria-pressed={isSelected}
        className="min-w-0 flex-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-app-accent/50"
        onClick={(event) => {
          if (event.metaKey || event.ctrlKey) {
            event.preventDefault();
            openInNewTab();
            return;
          }
          onSelect(hit);
        }}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
            event.preventDefault();
            openInNewTab();
          }
        }}
        type="button"
      >
        <div className="flex items-start gap-3">
          <SearchResultIcon entityType={hit.entity_type} active={isSelected} />
          <div className="min-w-0 flex-1">
            <SearchResultMetaLine meta={viewModel.meta} />
            <h2 className="app-text-title-md mt-1 truncate text-app-ink">
              {hit.title}
            </h2>
            <p className="app-text-body mt-1 line-clamp-2 text-app-ink/65">
              <HighlightedSnippet snippet={hit.snippet} />
            </p>
            <SearchResultContext items={viewModel.contextItems} />
          </div>
        </div>
      </button>
      <Link
        aria-label={t('ai.search.openResult', { title: accessibleTitle })}
        className="app-text-control-sm mt-1 inline-flex h-8 shrink-0 items-center gap-1 rounded-md border border-app-border bg-app-bg px-2.5 text-app-ink/65 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
        rel="noopener noreferrer"
        target="_blank"
        to={hit.deep_link}
      >
        <span className="hidden sm:inline">{t('ai.search.open')}</span>
        <ExternalLink size={13} />
      </Link>
    </div>
  );
}

export function SearchResultPreview({
  entityTypeLabels,
  hit,
  timeZone,
  variant,
}: {
  entityTypeLabels: ReadonlyMap<KeywordSearchEntityType, string>;
  hit: KeywordSearchHit;
  timeZone: string;
  variant: 'side' | 'inline';
}) {
  const { t, i18n } = useTranslation('apps');
  const viewModel = buildSearchHitViewModel(hit, {
    entityTypeLabels,
    locale: i18n.language,
    timeZone,
    t,
  });
  const accessibleTitle = `${viewModel.meta.entityLabel} · ${hit.title}`;

  return (
    <section
      aria-label={t('ai.search.preview', { title: accessibleTitle })}
      className={cn(
        'rounded-md border border-app-border bg-app-surface',
        variant === 'inline' && 'bg-app-surface',
      )}
    >
      <div className="border-b border-app-border p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <SearchResultMetaLine meta={viewModel.meta} />
            <h2 className="app-text-title-md mt-2 text-app-ink">{hit.title}</h2>
            <p className="app-text-caption mt-2 text-app-ink/50">
              {t('ai.search.updated', { date: viewModel.updatedLabel })}
            </p>
          </div>
          <SearchResultIcon entityType={hit.entity_type} active />
        </div>
        <Link
          aria-label={t('ai.search.openSelectedResult', {
            title: accessibleTitle,
          })}
          className="app-text-control-sm mt-4 inline-flex min-h-8 items-center gap-1.5 rounded-md bg-app-accent px-3 text-app-accent-fg transition-opacity hover:opacity-90"
          rel="noopener noreferrer"
          target="_blank"
          to={hit.deep_link}
        >
          {t('ai.search.open')}
          <ExternalLink size={13} />
        </Link>
      </div>

      <div className="space-y-4 p-4">
        <div>
          <h3 className="app-text-overline text-app-ink/45">
            {t('ai.search.content')}
          </h3>
          <p className="app-text-body mt-2 text-app-ink/70">
            <HighlightedSnippet snippet={hit.snippet} />
          </p>
        </div>

        {viewModel.peopleFields.length > 0 ||
        viewModel.positionFields.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {viewModel.peopleFields.map((field) => (
              <PreviewField
                key={field.label}
                label={field.label}
                values={field.values}
              />
            ))}
            {viewModel.positionFields.map((field) => (
              <PreviewField
                key={field.label}
                label={field.label}
                values={field.values}
              />
            ))}
          </div>
        ) : null}

        {viewModel.dateMarkerEntries.length > 0 ||
        viewModel.metadataEntries.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {viewModel.dateMarkerEntries.map((entry) => (
              <PreviewField
                key={entry.label}
                label={entry.label}
                values={[entry.value]}
              />
            ))}
            {viewModel.metadataEntries.map((entry) => (
              <PreviewField
                key={entry.label}
                label={entry.label}
                values={[entry.value]}
              />
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function SearchResultIcon({
  entityType,
  active = false,
}: {
  entityType: KeywordSearchEntityType;
  active?: boolean;
}) {
  return (
    <div
      className={cn(
        'mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border',
        active
          ? 'border-app-accent/30 bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/55',
      )}
    >
      <EntityIcon entityType={entityType} />
    </div>
  );
}

function SearchResultMetaLine({ meta }: { meta: SearchHitViewModel['meta'] }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="text-[0.72rem] font-semibold text-app-ink/45">
        {meta.entityLabel}
      </span>
      {meta.statusLabel ? (
        <span className="rounded-sm bg-app-bg px-1.5 py-0.5 text-[0.72rem] text-app-ink/55">
          {meta.statusLabel}
        </span>
      ) : null}
      {meta.visibilityLabel ? (
        <span className="text-[0.72rem] text-app-ink/40">
          {meta.visibilityLabel}
        </span>
      ) : null}
    </div>
  );
}

function SearchResultContext({ items }: { items: SearchContextItem[] }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[0.76rem] text-app-ink/45">
      {items.map((item) => (
        <span key={item.key}>{item.value}</span>
      ))}
    </div>
  );
}

function PreviewField({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <h3 className="app-text-overline text-app-ink/45">{label}</h3>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {values.map((value) => (
          <span
            key={value}
            className="rounded-sm bg-app-bg px-2 py-1 text-[0.76rem] text-app-ink/65"
          >
            {value}
          </span>
        ))}
      </div>
    </div>
  );
}

function HighlightedSnippet({ snippet }: { snippet: KeywordSearchSnippet }) {
  if (snippet.highlights.length === 0) {
    return snippet.text;
  }
  const [highlight] = snippet.highlights;
  return (
    <>
      {snippet.text.slice(0, highlight.start)}
      <mark className="rounded-sm bg-app-warning-bg px-0.5 text-app-ink">
        {snippet.text.slice(highlight.start, highlight.end)}
      </mark>
      {snippet.text.slice(highlight.end)}
    </>
  );
}

export function SortButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={cn(
        'min-h-7 rounded px-2.5 text-[0.78rem] font-medium',
        active
          ? 'bg-app-surface text-app-ink'
          : 'text-app-ink/50 hover:text-app-ink',
      )}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

export function SearchEntityFilterButton({
  active,
  count,
  entityType,
  label,
  onClick,
}: {
  active: boolean;
  count?: number;
  entityType: KeywordSearchEntityType | null;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-pressed={active}
      className={cn(
        'inline-flex min-h-8 items-center gap-1.5 rounded-md border px-3 text-[0.8rem] font-medium transition-colors',
        active
          ? 'border-app-accent bg-app-accent/10 text-app-accent'
          : 'border-app-border bg-app-bg text-app-ink/65 hover:bg-app-surface',
      )}
      onClick={onClick}
      type="button"
    >
      <EntityIcon entityType={entityType} />
      <span>{label}</span>
      {typeof count === 'number' ? (
        <span className="text-app-ink/40">{count}</span>
      ) : null}
    </button>
  );
}

function openSearchHitInNewTab(hit: KeywordSearchHit) {
  window.open(hit.deep_link, '_blank', 'noopener,noreferrer');
}

function buildSearchHitViewModel(
  hit: KeywordSearchHit,
  { entityTypeLabels, locale, timeZone, t }: SearchHitViewModelOptions,
): SearchHitViewModel {
  const updatedLabel = formatDate(hit.updated_at, timeZone, locale);
  return {
    contextItems: [
      { key: 'updated-at', value: updatedLabel },
      ...hit.people.slice(0, 2).map((person) => ({
        key: `person:${person.role}:${person.user_id}`,
        value: person.label,
      })),
      ...hit.targets.slice(0, 2).map((target) => ({
        key: `target:${target.type}:${target.id}`,
        value: target.label,
      })),
    ],
    dateMarkerEntries: getSearchHitDateMarkerEntries(hit, timeZone, locale, t),
    metadataEntries: getSearchHitMetadataEntries(hit, t),
    meta: {
      entityLabel:
        entityTypeLabels.get(hit.entity_type) ??
        humanizeEntityType(hit.entity_type),
      statusLabel: hit.status_label ?? null,
      visibilityLabel: hit.visibility
        ? visibilityLabel(hit.visibility, t)
        : null,
    },
    peopleFields:
      hit.people.length > 0
        ? [
            {
              label: t('ai.search.metadataPeople'),
              values: hit.people
                .slice(0, 4)
                .map(
                  (person) =>
                    `${personRoleLabel(person.role, t)} ${person.label}`,
                ),
            },
          ]
        : [],
    positionFields:
      hit.targets.length > 0
        ? [
            {
              label: t('ai.search.metadataPosition'),
              values: hit.targets.slice(0, 4).map((target) => target.label),
            },
          ]
        : [],
    updatedLabel,
  };
}

function getSearchHitDateMarkerEntries(
  hit: KeywordSearchHit,
  timeZone: string,
  locale: string,
  t: Translate,
): PreviewEntry[] {
  const entries: PreviewEntry[] = [];
  const labels: Record<string, string> = {
    due_date: t('ai.search.metadataDueDate'),
    start_date: t('ai.search.metadataStartDate'),
    event_start_at: t('ai.search.metadataEventStart'),
  };
  for (const key of ['due_date', 'start_date', 'event_start_at']) {
    const value = hit.date_markers[key];
    if (typeof value === 'string' && value) {
      entries.push({
        label: labels[key],
        value: formatDate(value, timeZone, locale),
      });
    }
  }
  return entries;
}

function getSearchHitMetadataEntries(hit: KeywordSearchHit, t: Translate) {
  const labels: Record<string, string> = {
    all_day: t('ai.search.metadataAllDay'),
    attendee_count: t('ai.search.metadataAttendeeCount'),
    task_number: t('ai.search.metadataIssueNumber'),
    location: t('ai.search.metadataLocation'),
    priority: t('ai.search.metadataPriority'),
    source_kind: t('ai.search.metadataSourceKind'),
    source_ref: t('ai.search.metadataSourceRef'),
  };
  return Object.entries(labels)
    .map(([key, label]) => {
      const value = hit.metadata[key];
      const formattedValue = formatMetadataValue(value, t);
      return formattedValue ? { label, value: formattedValue } : null;
    })
    .filter((entry): entry is { label: string; value: string } =>
      Boolean(entry),
    );
}

function formatMetadataValue(value: unknown, t: Translate): string | null {
  if (typeof value === 'string') {
    return value.trim() || null;
  }
  if (typeof value === 'number') {
    return String(value);
  }
  if (typeof value === 'boolean') {
    return value ? t('ai.search.yes') : t('ai.search.no');
  }
  return null;
}

function personRoleLabel(role: string, t: Translate): string {
  if (role === 'owner') return t('ai.search.metadataOwner');
  if (role === 'assignee') return t('ai.search.metadataAssignee');
  if (role === 'participant') return t('ai.search.metadataParticipant');
  return role;
}

export function EntityIcon({
  entityType,
}: {
  entityType: KeywordSearchEntityType | null;
}) {
  if (entityType === 'doc') {
    return <FileText size={13} />;
  }
  if (entityType === 'meeting') {
    return <Users size={13} />;
  }
  if (entityType === 'pms_task') {
    return <FolderKanban size={13} />;
  }
  if (entityType === 'planner_event') {
    return <CalendarDays size={13} />;
  }
  return <Search size={13} />;
}

function humanizeEntityType(entityType: string): string {
  return (
    entityType
      .split(/[_:.-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ') || entityType
  );
}

function visibilityLabel(value: string, t: Translate): string {
  if (value === 'private') return t('ai.search.visibilityPrivate');
  if (value === 'public') return t('ai.search.visibilityPublic');
  if (value === 'shared') return t('ai.search.visibilityShared');
  return value;
}

function formatDate(value: string, timeZone: string, locale: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatDateOnly(value, { fallback: value, locale });
  }
  return formatDateTime(value, {
    dateStyle: 'medium',
    fallback: value,
    locale,
    timeZone,
  });
}
