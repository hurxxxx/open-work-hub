import type { Block } from '@blocknote/core';

/** JSON-serializable block content stored in the database. */
export type BlockContent = Block[];

export type MentionSuggestion = {
  id: string;
  name: string;
  avatar?: string;
};

export type TaskRefSuggestion = {
  id: string;
  key: string;
  title: string;
};
