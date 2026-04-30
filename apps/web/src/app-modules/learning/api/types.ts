export type LearningPageNoteVisibility = 'public' | 'private';

export interface LearningPageNoteListItem {
  doc_id: string;
  course_slug: string;
  lesson_id: string;
  visibility: LearningPageNoteVisibility;
  author_id: string;
  author_name: string;
  is_mine: boolean;
  updated_at: string;
}

export interface LearningPageNoteListResponse {
  items: LearningPageNoteListItem[];
}

export interface LearningPageNoteDetail {
  doc_id: string;
  page_id: string;
  course_slug: string;
  lesson_id: string;
  visibility: LearningPageNoteVisibility;
  author_id: string;
  author_name: string;
  is_mine: boolean;
  title: string;
  content_blocks: unknown[];
  trashed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LearningPageNoteUpsertPayload {
  course_slug: string;
  lesson_id: string;
  lesson_title: string;
  visibility: LearningPageNoteVisibility;
  content_blocks: unknown[];
}
