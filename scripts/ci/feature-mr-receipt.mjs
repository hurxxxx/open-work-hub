import { createHash } from 'node:crypto';

const RECEIPT_PATTERN = /\n\n<!-- ai-do:pf:v1:([A-Za-z0-9_-]{43}) -->$/;

function canonicalDescription(description) {
  return description.trimEnd();
}

function receiptDigest({ description, label, sourceSha, targetSha }) {
  return createHash('sha256')
    .update(
      [
        'ai-do-feature-mr-preflight-v1',
        sourceSha,
        targetSha,
        label,
        canonicalDescription(description),
      ].join('\0'),
    )
    .digest('base64url');
}

export function attachLocalPreflightReceipt(context) {
  if (RECEIPT_PATTERN.test(context.description)) {
    throw new Error(
      'The source MR description must not contain a preflight receipt.',
    );
  }
  const receipt = receiptDigest(context);
  return `${canonicalDescription(context.description)}\n\n<!-- ai-do:pf:v1:${receipt} -->`;
}

export function verifyLocalPreflightReceipt(context) {
  const match = context.description.match(RECEIPT_PATTERN);
  if (!match) {
    return {
      ok: false,
      error:
        'Missing local preflight receipt. Publish feature MRs with pnpm mr:publish.',
    };
  }

  const description = context.description.slice(0, match.index);
  const expected = receiptDigest({ ...context, description });
  if (match[1] !== expected) {
    return {
      ok: false,
      error:
        'Local preflight receipt does not match the MR source, target, lane, or description.',
    };
  }
  return { ok: true, description };
}
