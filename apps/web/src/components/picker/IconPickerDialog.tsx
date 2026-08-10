import { useEffect, useMemo, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Check, Search } from 'lucide-react';

import {
  Dialog,
  SearchField,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
} from '@ai-do/ui';

import {
  filterIconPickerKeys,
  iconPickerAllKeys,
  ICON_PICKER_ALL_GROUP_ID,
  type IconPickerGroup,
} from './icon-picker-model';

export type IconPickerDialogProps = {
  allLabel: string;
  closeLabel: string;
  emptyLabel: string;
  groups: readonly IconPickerGroup[];
  iconForKey: (iconKey: string) => LucideIcon;
  onClose: () => void;
  onSelect: (value: string) => void;
  open: boolean;
  searchLabel: string;
  searchPlaceholder: string;
  searchTextForKey?: (iconKey: string) => string;
  title: string;
  value: string;
};

export function IconPickerDialog({
  allLabel,
  closeLabel,
  emptyLabel,
  groups,
  iconForKey,
  onClose,
  onSelect,
  open,
  searchLabel,
  searchPlaceholder,
  searchTextForKey,
  title,
  value,
}: IconPickerDialogProps) {
  const [activeGroupId, setActiveGroupId] = useState(ICON_PICKER_ALL_GROUP_ID);
  const [query, setQuery] = useState('');
  const allIconKeys = useMemo(() => iconPickerAllKeys(groups), [groups]);
  const activeGroup = useMemo(
    () => groups.find((group) => group.id === activeGroupId),
    [activeGroupId, groups],
  );
  const tabValue =
    activeGroupId === ICON_PICKER_ALL_GROUP_ID || activeGroup
      ? activeGroupId
      : ICON_PICKER_ALL_GROUP_ID;
  const activeIconKeys = useMemo(
    () =>
      tabValue === ICON_PICKER_ALL_GROUP_ID
        ? allIconKeys
        : (activeGroup?.iconKeys ?? []),
    [activeGroup?.iconKeys, allIconKeys, tabValue],
  );
  const filteredIconKeys = useMemo(
    () => filterIconPickerKeys(activeIconKeys, query, searchTextForKey),
    [activeIconKeys, query, searchTextForKey],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveGroupId(ICON_PICKER_ALL_GROUP_ID);
    setQuery('');
  }, [open]);

  return (
    <Dialog
      closeLabel={closeLabel}
      contentClassName="max-h-[85vh]"
      layer="elevated"
      maxWidth="max-w-2xl"
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose();
        }
      }}
      open={open}
      title={title}
    >
      <div className="space-y-3">
        <SearchField
          aria-label={searchLabel}
          endAdornment={<Search size={14} className="text-app-ink/50" />}
          onChange={(event) => setQuery(event.currentTarget.value)}
          placeholder={searchPlaceholder}
          value={query}
        />
        <Tabs value={tabValue} onValueChange={setActiveGroupId}>
          <TabsList className="max-h-24 overflow-y-auto">
            <TabsTrigger value={ICON_PICKER_ALL_GROUP_ID}>
              {allLabel}
            </TabsTrigger>
            {groups.map((group) => (
              <TabsTrigger key={group.id} value={group.id}>
                {group.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div
          aria-label={title}
          className="grid h-[24rem] grid-cols-5 content-start justify-items-center gap-1.5 overflow-y-auto p-1 sm:grid-cols-7 md:grid-cols-8"
          role="radiogroup"
        >
          {filteredIconKeys.length === 0 ? (
            <div className="app-text-caption col-span-full rounded-md border border-dashed border-app-border px-4 py-8 text-center text-app-ink/50">
              {emptyLabel}
            </div>
          ) : (
            filteredIconKeys.map((iconKey) => {
              const Icon = iconForKey(iconKey);
              const selected = iconKey === value;
              return (
                <Tooltip content={iconKey} key={iconKey}>
                  <button
                    aria-checked={selected}
                    aria-label={iconKey}
                    className={`relative inline-flex size-10 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/30 ${
                      selected
                        ? 'bg-app-accent/10 text-app-accent ring-1 ring-app-accent/35'
                        : 'text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink'
                    }`}
                    onClick={() => onSelect(iconKey)}
                    role="radio"
                    type="button"
                  >
                    <Icon size={17} />
                    {selected ? (
                      <span className="absolute right-1 top-1 inline-flex size-3 items-center justify-center rounded-full bg-app-accent text-app-accent-fg">
                        <Check size={9} />
                      </span>
                    ) : null}
                  </button>
                </Tooltip>
              );
            })
          )}
        </div>
      </div>
    </Dialog>
  );
}
