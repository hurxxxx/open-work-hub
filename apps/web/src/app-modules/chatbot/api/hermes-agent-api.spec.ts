import { describe, expect, it } from 'vitest';

import {
  decodeHermesApprovalReference,
  encodeHermesApprovalReference,
  hermesApprovalToolName,
} from './hermes-agent-api';

describe('Hermes approval references', () => {
  it('round-trips request ids without exposing a separate mutable lookup key', () => {
    const reference = {
      runId: 'run-123',
      requestId: 'approval:tool/한글?choice=once',
      sequence: 17,
    };

    expect(
      decodeHermesApprovalReference(encodeHermesApprovalReference(reference)),
    ).toEqual(reference);
  });

  it('rejects malformed or foreign approval ids', () => {
    expect(decodeHermesApprovalReference('legacy-approval')).toBeNull();
    expect(decodeHermesApprovalReference('hermes:run:not-a-number:id')).toBeNull();
    expect(decodeHermesApprovalReference('hermes::1:id')).toBeNull();
  });

  it('extracts the exact tool from the official Hermes MCP trust prompt', () => {
    expect(
      hermesApprovalToolName({
        command:
          "MCP tool 'tasks.create' on UNTRUSTED server 'owh-mcp-0123456789abcdefabcd-internal' wants to run. This tool is write-capable.",
      }),
    ).toBe('tasks.create');
    expect(
      hermesApprovalToolName({
        command:
          "MCP tool 'tasks.create' on UNTRUSTED server 'other' wants to run.",
      }),
    ).toBe('tool');
  });
});
