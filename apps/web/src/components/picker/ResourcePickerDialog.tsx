import { useId, type ReactNode } from 'react';
import { Button, Dialog, InlineNotice } from '@open-alm/ui';
import { Loader2 } from 'lucide-react';

type ResourcePickerSearch = {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
  inputId?: string;
};

export type ResourcePickerDialogProps<TItem> = {
  accessNotice?: ReactNode;
  canAccess?: boolean;
  closeLabel: string;
  controlsSlot?: ReactNode;
  contentClassName?: string;
  description: ReactNode;
  emptyLabel: ReactNode;
  error?: ReactNode;
  getItemId: (item: TItem) => string;
  isOpen: boolean;
  items: readonly TItem[];
  layer?: 'default' | 'elevated';
  listMaxHeightClassName?: string;
  loading?: boolean;
  maxWidth?: string;
  overlayClassName?: string;
  onClose: () => void;
  onPick: (item: TItem) => void;
  renderItem: (item: TItem) => ReactNode;
  search?: ResourcePickerSearch;
  submittingId?: string | null;
  title: ReactNode;
};

export function ResourcePickerDialog<TItem>({
  accessNotice,
  canAccess = true,
  closeLabel,
  controlsSlot,
  contentClassName,
  description,
  emptyLabel,
  error,
  getItemId,
  isOpen,
  items,
  layer,
  listMaxHeightClassName = 'max-h-72',
  loading = false,
  maxWidth = 'max-w-xl',
  overlayClassName,
  onClose,
  onPick,
  renderItem,
  search,
  submittingId = null,
  title,
}: ResourcePickerDialogProps<TItem>) {
  const generatedSearchInputId = useId();
  const searchInputId = search?.inputId ?? generatedSearchInputId;

  return (
    <Dialog
      closeLabel={closeLabel}
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={title}
      description={description}
      maxWidth={maxWidth}
      layer={layer}
      contentClassName={contentClassName}
      overlayClassName={overlayClassName}
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>
            {closeLabel}
          </Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {!canAccess ? accessNotice : null}

        {canAccess && error ? (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        ) : null}

        {canAccess ? (
          <>
            {controlsSlot}

            {search ? (
              <div className="space-y-1">
                <label
                  htmlFor={searchInputId}
                  className="app-text-control-sm text-app-ink/70"
                >
                  {search.label}
                </label>
                <input
                  id={searchInputId}
                  type="text"
                  value={search.value}
                  onChange={(event) => search.onChange(event.target.value)}
                  placeholder={search.placeholder}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
                />
              </div>
            ) : null}

            <div
              className={`${listMaxHeightClassName} overflow-y-auto rounded-md border border-app-border`}
            >
              {loading ? (
                <div className="flex h-24 items-center justify-center text-app-ink/40">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : items.length === 0 ? (
                <div className="app-text-caption px-4 py-6 text-center text-app-ink/50">
                  {emptyLabel}
                </div>
              ) : (
                <ul className="divide-y divide-app-border">
                  {items.map((item) => {
                    const itemId = getItemId(item);
                    return (
                      <li key={itemId}>
                        <button
                          type="button"
                          onClick={() => onPick(item)}
                          disabled={submittingId !== null}
                          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                        >
                          <div className="flex min-w-0 flex-1 items-center gap-3">
                            {renderItem(item)}
                          </div>
                          {submittingId === itemId ? (
                            <Loader2
                              size={14}
                              className="shrink-0 animate-spin text-app-ink/40"
                            />
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
