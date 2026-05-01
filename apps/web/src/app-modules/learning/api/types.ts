import type { ApiSchema } from '@/src/platform/api/types';

export type LearningPageNoteVisibility = ApiSchema<'LearningPageNoteDetail'>['visibility'];
export type LearningPageNoteListItem = ApiSchema<'LearningPageNoteListItem'>;
export type LearningPageNoteListResponse = ApiSchema<'LearningPageNoteListResponse'>;
export type LearningPageNoteDetail = ApiSchema<'LearningPageNoteDetail'>;
export type LearningPageNoteUpsertPayload = Omit<
  ApiSchema<'LearningPageNoteUpsertRequest'>,
  'content_blocks'
> & {
  content_blocks: unknown[];
};
