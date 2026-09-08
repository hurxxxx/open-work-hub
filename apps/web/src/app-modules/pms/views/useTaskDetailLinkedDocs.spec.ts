import type { BlockContent } from '@open-work-hub/ui';
import { describe, expect, it } from 'vitest';

import {
  resolveTaskDetailDocPath,
  resolveTaskDetailPromotedDocContent,
} from './useTaskDetailLinkedDocs';

describe('task detail linked docs helpers', () => {
  it('prefers unsaved editor blocks when promoting a description', () => {
    const editorBlocks: BlockContent = [
      {
        id: 'draft-1',
        type: 'paragraph',
        props: {
          backgroundColor: 'default',
          textColor: 'default',
          textAlignment: 'left',
        },
        content: [{ type: 'text', text: 'Draft', styles: {} }],
        children: [],
      },
    ];
    const issueBlocks = [{ type: 'paragraph', content: 'Saved' }];

    expect(
      resolveTaskDetailPromotedDocContent({
        descriptionBlocks: editorBlocks,
        issueDescriptionBlocks: issueBlocks,
      }),
    ).toEqual(editorBlocks);
  });

  it('falls back to saved description blocks when the editor has no draft', () => {
    const issueBlocks = [{ type: 'paragraph', content: 'Saved' }];

    expect(
      resolveTaskDetailPromotedDocContent({
        descriptionBlocks: null,
        issueDescriptionBlocks: issueBlocks,
      }),
    ).toEqual(issueBlocks);
  });

  it('builds Docs document paths for linked resources', () => {
    expect(
      resolveTaskDetailDocPath({
        docId: 'doc-1',
      }),
    ).toBe('/apps/docs/documents/doc-1');
  });
});
