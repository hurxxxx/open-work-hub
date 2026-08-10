import { describe, expect, it } from 'vitest';

import {
  resolveTaskDetailDocPath,
  resolveTaskDetailPromotedDocContent,
} from './useTaskDetailLinkedDocs';

describe('task detail linked docs helpers', () => {
  it('prefers unsaved editor blocks when promoting a description', () => {
    const editorBlocks = [{ type: 'paragraph', content: 'Draft' }];
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

  it('builds workspace docs paths when a workspace slug is present', () => {
    expect(
      resolveTaskDetailDocPath({
        docId: 'doc-1',
        user: null,
        workspaceSlug: 'team space',
      }),
    ).toBe('/w/team%20space/docs/doc-1');
  });
});
