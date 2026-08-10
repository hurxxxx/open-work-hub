import { describe, expect, it } from 'vitest';

import { formatTaskDetailAttachmentSize } from './useTaskDetailAttachments';

describe('formatTaskDetailAttachmentSize', () => {
  it('formats byte, kilobyte, and megabyte sizes', () => {
    expect(formatTaskDetailAttachmentSize(512)).toBe('512 B');
    expect(formatTaskDetailAttachmentSize(1023)).toBe('1023 B');
    expect(formatTaskDetailAttachmentSize(1024)).toBe('1.0 KB');
    expect(formatTaskDetailAttachmentSize(2048)).toBe('2.0 KB');
    expect(formatTaskDetailAttachmentSize(1024 * 1024)).toBe('1.0 MB');
    expect(formatTaskDetailAttachmentSize(3145728)).toBe('3.0 MB');
  });
});
