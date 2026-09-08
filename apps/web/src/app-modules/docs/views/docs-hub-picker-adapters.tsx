import type { TFunction } from 'i18next';
import { FileIcon } from 'lucide-react';

import { formatDateTime } from '@/src/platform/time/time-utils';
import type { DocsHubItem } from '../api/docs-api';
import {
  EMPTY_EXCLUDED_DOC_IDS,
  type DocsHubPickerSelection,
} from '../api/docs-hub-picker-model';
import type { DocsHubPickerAdapter } from './DocsHubPickerModal';

type DocsHubItemPickHandler = (doc: DocsHubItem) => Promise<void> | void;

const METADATA_SEPARATOR = ' \u00b7 ';

export const EMPTY_DOCS_HUB_PICKER_EXCLUDED_DOC_IDS = EMPTY_EXCLUDED_DOC_IDS;

export function resolveDocsHubPickerExcludeDocIds(
  excludeDocIds?: readonly string[] | null,
): readonly string[] {
  return excludeDocIds ?? EMPTY_DOCS_HUB_PICKER_EXCLUDED_DOC_IDS;
}

export function pickDocsHubSelectionItem(
  onPick: DocsHubItemPickHandler,
): (selection: DocsHubPickerSelection) => Promise<void> | void {
  return (selection) => onPick(selection.item);
}

export function buildMeetingDocsHubPickerAdapter({
  locale,
  t,
  timeZone,
}: {
  locale: string;
  t: TFunction;
  timeZone: string;
}): DocsHubPickerAdapter {
  return {
    searchMode: 'local',
    access: 'app-admission',
    copy: {
      title: t('meeting.docPicker.title'),
      description: t('meeting.docPicker.description'),
      searchPlaceholder: t('meeting.docPicker.searchPlaceholder'),
      empty: t('meeting.docPicker.empty'),
      loadFailed: t('meeting.docPicker.loadFailed'),
      attachFailed: t('meeting.docPicker.attachFailed'),
      noAccessAppLabel: t('meeting.docPicker.docsApp'),
      noAccessAction: t('meeting.docPicker.attachAction'),
    },
    getDocId: getSourceDocId,
    filterLoadedItems: filterNativeDocsHubItems,
    renderMeta: (item) => renderMeetingMetadata(item, locale, timeZone),
    listParams: { sort_by: 'updated_at', sort_dir: 'desc' },
    pageSize: 50,
    getLoadFailedMessage: buildErrorFallback(t('meeting.docPicker.loadFailed')),
    getAttachFailedMessage: buildErrorFallback(
      t('meeting.docPicker.attachFailed'),
    ),
  };
}

export function buildPmsTaskDocsHubPickerAdapter(
  t: TFunction,
): DocsHubPickerAdapter {
  return {
    searchMode: 'remote',
    access: 'token-only',
    copy: {
      title: t('pms.taskDetail.docPickerTitle'),
      description: t('pms.taskDetail.docPickerDescription'),
      searchPlaceholder: t('pms.taskDetail.docPickerSearchPlaceholder'),
      empty: t('common:empty.noResults'),
      loadFailed: t('pms.taskDetail.errors.loadDocsFailed'),
      attachFailed: t('pms.taskDetail.errors.linkDocFailed'),
      untitled: t('pms.taskDetail.docPickerUntitled'),
    },
    renderMeta: renderSourceMetadata,
    renderLeadingIcon: () => (
      <FileIcon size={16} className="shrink-0 text-app-ink/40" />
    ),
    layer: 'elevated',
    listMaxHeightClassName: 'max-h-80',
    getLoadFailedMessage: buildErrorFallback(
      t('pms.taskDetail.errors.loadDocsFailed'),
      { requireMessage: true },
    ),
    getAttachFailedMessage: buildErrorFallback(
      t('pms.taskDetail.errors.linkDocFailed'),
      { requireMessage: true },
    ),
  };
}

function renderSourceMetadata(item: DocsHubItem): string {
  return `${item.source_app}${METADATA_SEPARATOR}${item.source_kind}`;
}

function getSourceDocId(item: DocsHubItem): string {
  return item.source_id;
}

function filterNativeDocsHubItems(items: DocsHubItem[]): DocsHubItem[] {
  return items.filter((item) => item.source_type === 'native_doc');
}

function renderMeetingMetadata(
  item: DocsHubItem,
  locale: string,
  timeZone: string,
): string {
  return `${item.created_by_name}${METADATA_SEPARATOR}${formatDateTime(
    item.updated_at,
    {
      day: 'numeric',
      locale,
      month: 'short',
      timeZone,
    },
  )}`;
}

function buildErrorFallback(
  fallback: string,
  options: { requireMessage?: boolean } = {},
): (error: unknown) => string {
  return (error) => {
    if (error instanceof Error && (!options.requireMessage || error.message)) {
      return error.message;
    }
    return fallback;
  };
}
