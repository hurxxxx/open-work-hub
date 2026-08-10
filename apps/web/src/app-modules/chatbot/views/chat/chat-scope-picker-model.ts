export interface ChatScopeOption {
  id: string;
  title: string;
}

/**
 * `null` means all available tools, while an empty array means text-only mode.
 */
export type ChatScopeSelection = string[] | null;

export type ChatScopeSummary =
  | { kind: 'all' }
  | { kind: 'none' }
  | { kind: 'single'; id: string; option: ChatScopeOption | null }
  | { kind: 'count'; count: number };

export interface ChatScopePickerModel {
  selection: ChatScopeSelection;
  summary: ChatScopeSummary;
}

export function sanitizeChatScopeSelection({
  options,
  selected,
}: {
  options: readonly ChatScopeOption[];
  selected: ChatScopeSelection;
}): ChatScopeSelection {
  if (selected === null) {
    return null;
  }

  const knownIds = new Set(options.map((item) => item.id));
  return selected.filter((id) => knownIds.has(id));
}

function summarizeChatScopeSelection({
  options,
  selection,
}: {
  options: readonly ChatScopeOption[];
  selection: ChatScopeSelection;
}): ChatScopeSummary {
  if (selection === null) {
    return { kind: 'all' };
  }

  if (selection.length === 0) {
    return { kind: 'none' };
  }

  if (selection.length === options.length) {
    return { kind: 'all' };
  }

  if (selection.length === 1) {
    const id = selection[0] as string;
    return {
      kind: 'single',
      id,
      option: options.find((item) => item.id === id) ?? null,
    };
  }

  return { kind: 'count', count: selection.length };
}

export function resolveChatScopePickerModel({
  options,
  selected,
}: {
  options: readonly ChatScopeOption[];
  selected: ChatScopeSelection;
}): ChatScopePickerModel {
  const selection = sanitizeChatScopeSelection({ options, selected });
  return {
    selection,
    summary: summarizeChatScopeSelection({ options, selection }),
  };
}

export function isChatScopeOptionSelected(
  selection: ChatScopeSelection,
  id: string,
): boolean {
  return selection === null || selection.includes(id);
}

export function toggleChatScopeSelection({
  id,
  options,
  selected,
}: {
  id: string;
  options: readonly ChatScopeOption[];
  selected: ChatScopeSelection;
}): ChatScopeSelection {
  const selection = sanitizeChatScopeSelection({ options, selected });
  const base = selection ?? options.map((item) => item.id);
  const next = base.includes(id)
    ? base.filter((item) => item !== id)
    : [...base, id];

  return next.length === options.length ? null : next;
}
