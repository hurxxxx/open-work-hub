import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { NavItem } from '@/src/app/shell/navigation-types';

// A buffer qualifies as a slash command only when it's a single "/" followed
// by identifier-safe characters: no additional "/" and no whitespace.
const SLASH_COMMAND_PATTERN = /^\/[^/\s]*$/;
function isSlashCommandBuffer(input: string): boolean {
  return SLASH_COMMAND_PATTERN.test(input);
}

export function useSlashCommandItems(source: NavItem[], rawInput: string) {
  const { t } = useTranslation('shell');
  return useMemo(() => {
    if (!isSlashCommandBuffer(rawInput)) {
      return null;
    }
    const query = rawInput.slice(1).trim().toLowerCase();
    const commandItems = source.map((item) => {
      const description = t(`navDescriptions.${item.id}`, {
        defaultValue: item.description ?? '',
      });
      return {
        ...item,
        title: t(`nav.${item.id}`, { defaultValue: item.title }),
        description: description || undefined,
        category: t(`categories.${item.category}`, {
          defaultValue: item.category,
        }),
      };
    });
    if (!query) {
      return commandItems;
    }
    return commandItems.filter((item) => {
      const haystack =
        `${item.title} ${item.description ?? ''} ${item.id}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [source, rawInput, t]);
}
