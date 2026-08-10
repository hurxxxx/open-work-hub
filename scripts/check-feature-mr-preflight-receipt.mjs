#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

import { verifyLocalPreflightReceipt } from './ci/feature-mr-receipt.mjs';

function featureLane(labels) {
  const laneLabels = String(labels ?? '')
    .split(',')
    .map((label) => label.trim())
    .filter((label) => /^lane::/.test(label));
  return laneLabels.length === 1 ? laneLabels[0] : null;
}

export function evaluateFeatureMrPreflightReceipt(env = process.env) {
  const isMergeRequest =
    env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
    Boolean(env.CI_MERGE_REQUEST_IID);
  if (!isMergeRequest) {
    return { ok: true, skipped: true, reason: 'not a merge request pipeline' };
  }
  if (
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME !== 'dev' ||
    ['dev', 'main'].includes(env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME)
  ) {
    return { ok: true, skipped: true, reason: 'not a feature-to-dev MR' };
  }

  const required = {
    description: env.CI_MERGE_REQUEST_DESCRIPTION,
    label: featureLane(env.CI_MERGE_REQUEST_LABELS),
    sourceSha: env.CI_COMMIT_SHA,
    targetSha: env.CI_MERGE_REQUEST_DIFF_BASE_SHA,
  };
  const missing = Object.entries(required)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    return {
      ok: false,
      error: `Cannot verify local preflight receipt; missing ${missing.join(', ')}.`,
    };
  }
  if (env.CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED === 'true') {
    return {
      ok: false,
      error: 'Cannot verify a truncated MR description.',
    };
  }

  return verifyLocalPreflightReceipt(required);
}

export function main(env = process.env, output = console) {
  const result = evaluateFeatureMrPreflightReceipt(env);
  if (!result.ok) {
    output.error(`[feature-mr-preflight] ${result.error}`);
    return 1;
  }
  output.log(
    `[feature-mr-preflight] ${result.skipped ? `skipped: ${result.reason}` : 'receipt verified'}`,
  );
  return 0;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  process.exitCode = main();
}
