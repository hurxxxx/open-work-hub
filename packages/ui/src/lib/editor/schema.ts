import { BlockNoteSchema, defaultBlockSpecs, defaultInlineContentSpecs } from '@blocknote/core';
import { Callout } from './custom-blocks/callout';
import { Divider } from './custom-blocks/divider';
import { Mention } from './custom-inline/mention';
import { TaskRef } from './custom-inline/task-ref';

/** Full schema with all custom blocks and inline content. */
export const fullSchema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    callout: Callout(),
    divider: Divider(),
  },
  inlineContentSpecs: {
    ...defaultInlineContentSpecs,
    mention: Mention,
    taskRef: TaskRef,
  },
});

/** Compact schema for comments — no tables, code blocks, callouts, images, files. */
export const compactSchema = BlockNoteSchema.create({
  blockSpecs: {
    paragraph: defaultBlockSpecs.paragraph,
    heading: defaultBlockSpecs.heading,
    bulletListItem: defaultBlockSpecs.bulletListItem,
    numberedListItem: defaultBlockSpecs.numberedListItem,
    checkListItem: defaultBlockSpecs.checkListItem,
  },
  inlineContentSpecs: {
    ...defaultInlineContentSpecs,
    mention: Mention,
  },
});

export type FullSchema = typeof fullSchema;
export type CompactSchema = typeof compactSchema;
