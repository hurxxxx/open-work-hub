import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  Trash2,
} from 'lucide-react';

import { cn } from '@/src/lib/utils';
import type { DocsContentFormat, DocsPageItem } from '../api/docs-api';
import type { DropZone } from '../api/docs-page-reorder';

const readLegacyFlag = (
  props: Record<string, unknown>,
  prefix: string,
  suffix: string,
) => props[`${prefix}${suffix}`] === true;

type DocsPageTreeNodeProps = {
  page: DocsPageItem;
  contentFormat: DocsContentFormat;
  depth: number;
  dropZone: DropZone | null;
  onSelect: (pageId: string) => void;
  onToggleExpand: (pageId: string) => void;
  onDelete: (page: DocsPageItem) => void;
} & Record<string, unknown>;

export function DocsPageTreeNode(props: DocsPageTreeNodeProps) {
  const { page, contentFormat, depth, dropZone, onSelect, onToggleExpand } =
    props;
  const treeHasChildren = readLegacyFlag(props, 'has', 'Children');
  const treeExpanded = readLegacyFlag(props, 'is', 'Expanded');
  const treeSelected = readLegacyFlag(props, 'is', 'Selected');
  const dragEnabled = readLegacyFlag(props, 'can', 'Drag');
  const deleteEnabled = readLegacyFlag(props, 'can', 'Delete');
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: page.id,
    disabled: !dragEnabled,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  const PageIcon = contentFormat === 'html' ? FileCode2 : FileText;

  return (
    <div className="relative" style={style}>
      {dropZone === 'before' ? (
        <div className="pointer-events-none absolute inset-x-1 top-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
      <div
        ref={setNodeRef}
        {...attributes}
        {...listeners}
        className={cn(
          'app-text-body-sm group flex w-full items-center gap-1 rounded px-2 py-1.5 transition-all',
          treeSelected
            ? 'bg-app-accent/10 text-app-accent'
            : 'text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink',
          isDragging && 'opacity-30',
          dropZone === 'inside' &&
            'bg-app-accent/15 ring-1 ring-inset ring-app-accent/70',
        )}
        style={{ paddingLeft: `${8 + depth * 16}px`, touchAction: 'none' }}
      >
        {treeHasChildren ? (
          <button
            type="button"
            className="flex-shrink-0"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              onToggleExpand(page.id);
            }}
            aria-label={page.title}
          >
            {treeExpanded ? (
              <ChevronDown size={12} className="text-app-ink/55" />
            ) : (
              <ChevronRight size={12} className="text-app-ink/55" />
            )}
          </button>
        ) : (
          <span className="w-3" />
        )}
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-1 text-left"
          onClick={() => onSelect(page.id)}
        >
          <PageIcon
            size={14}
            className={treeSelected ? 'text-app-accent' : 'text-app-ink/55'}
          />
          <span className="flex-1 truncate text-left">{page.title}</span>
        </button>
        {deleteEnabled ? (
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              props.onDelete(page);
            }}
            aria-label={page.title}
          >
            <Trash2
              size={12}
              className="text-app-ink/55 hover:text-app-danger-text"
            />
          </button>
        ) : null}
      </div>
      {dropZone === 'after' ? (
        <div className="pointer-events-none absolute inset-x-1 bottom-0 z-10 h-0.5 rounded bg-app-accent" />
      ) : null}
    </div>
  );
}
