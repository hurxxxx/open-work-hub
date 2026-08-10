#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

import {
  classifyPath,
  lanesFromMergeRequestLabels,
  normalizeLane,
} from './app-platform-guardrails/classifier.mjs';
import {
  collectGitChanges,
  runGit,
} from './app-platform-guardrails/git-changes.mjs';
import { migrationRiskForChange } from './app-platform-guardrails/migrations.mjs';
import { CORE_API_DOMAINS, LANES } from './app-platform-guardrails/policy.mjs';

export const CONTRACT_EVIDENCE_MARKER = '<!-- open-alm:vibe-app-contract:v1 -->';
export const CORE_ENABLEMENT_MARKER = '<!-- open-alm:core-enablement:v1 -->';

const VIBE_REQUIRED_HEADINGS = [
  'Contract Map',
  'Data, Authorization, And Safety',
  'Verification Evidence',
  'Independent Review',
];

const CORE_REQUIRED_HEADINGS = [
  'Enablement Contract',
  'Verification Evidence',
  'Core Review',
];

export const REQUIRED_CHECK_IDS = Object.freeze([
  'scaffold',
  'app-owned-surface',
  'lane',
  'authorization',
  'transaction',
  'file-network',
  'ai',
  'worker',
  'compatibility',
  'workspace-keyword-search',
  'merge-result',
  'scope-clean',
  'affected-checks',
  'independent-review',
  'review-freshness',
  'remaining-risks',
]);

export const REQUIRED_FIELD_IDS = Object.freeze([
  'contract-outcome',
  'contract-boundaries',
  'contract-interfaces',
  'contract-runtime',
  'safety-evidence',
  'workspace-keyword-search',
  'target-state',
  'source-sha',
  'verification',
  'remaining-risks',
]);

export const CORE_REQUIRED_CHECK_IDS = Object.freeze([
  'independent-deployable',
  'hidden-default',
  'extension-contracts',
  'activation-owner',
  'workspace-keyword-search',
  'merge-result',
  'affected-checks',
  'core-review',
]);

export const CORE_REQUIRED_FIELD_IDS = Object.freeze([
  'outcome',
  'protected-surfaces',
  'app-boundary',
  'activation',
  'compatibility',
  'workspace-keyword-search',
  'target-state',
  'source-sha',
  'verification',
  'remaining-risks',
]);

function apiDomainForPath(filePath) {
  const match = /^apps\/api\/src\/open_alm_api\/domains\/([^/]+)(?:\/|$)/.exec(
    filePath,
  );
  return match?.[1] ?? null;
}

export function isDomainAppDeliveryPath(filePath) {
  if (/^apps\/web\/src\/app-modules\//.test(filePath)) {
    return true;
  }
  if (/^apps\/api\/alembic\/versions\/[^/]+\.py$/.test(filePath)) {
    return true;
  }
  if (/^apps\/worker\/src\/open_alm_worker\/tasks\//.test(filePath)) {
    return true;
  }
  const apiDomain = apiDomainForPath(filePath);
  return Boolean(apiDomain && !CORE_API_DOMAINS.has(apiDomain));
}

export function isPrimaryAppOwnedDeliveryPath(filePath) {
  if (/^apps\/web\/src\/app-modules\//.test(filePath)) {
    return true;
  }
  if (
    /^apps\/worker\/src\/open_alm_worker\/tasks\/apps\/[a-z0-9_-]+\//.test(
      filePath,
    )
  ) {
    return true;
  }
  const apiDomain = apiDomainForPath(filePath);
  return Boolean(apiDomain && !CORE_API_DOMAINS.has(apiDomain));
}

function isFeatureMergeRequestToDev(env) {
  return (
    (env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
      Boolean(env.CI_MERGE_REQUEST_IID)) &&
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME === 'dev'
  );
}

function isMergeRequestPipeline(env) {
  return (
    env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
    Boolean(env.CI_MERGE_REQUEST_IID)
  );
}

function isAppSandboxMergeRequest(env) {
  const lanes = lanesFromMergeRequestLabels(env.CI_MERGE_REQUEST_LABELS ?? '');
  return lanes.length === 1 && normalizeLane(lanes[0]) === LANES.APP_SANDBOX;
}

function isCorePlatformMergeRequest(env) {
  const lanes = lanesFromMergeRequestLabels(env.CI_MERGE_REQUEST_LABELS ?? '');
  return lanes.length === 1 && normalizeLane(lanes[0]) === LANES.CORE_PLATFORM;
}

function isProtectedCorePath(filePath) {
  const classification = classifyPath(filePath);
  return (
    Boolean(classification.protectedSurface) &&
    classification.lane !== LANES.APP_SANDBOX &&
    classification.lane !== LANES.PROTOTYPE &&
    classification.lane !== LANES.HARNESS_AND_POLICY
  );
}

function isHarnessPolicyPath(filePath) {
  const classification = classifyPath(filePath);
  return (
    Boolean(classification.protectedSurface) &&
    classification.lane === LANES.HARNESS_AND_POLICY
  );
}

export function isWorkspaceKeywordSearchContractPath(filePath) {
  return (
    /^apps\/api\/src\/open_alm_api\/domains\/search\//.test(filePath) ||
    /^apps\/api\/src\/open_alm_api\/domains\/[^/]+\/search_(?:hooks|projection|registration)\.py$/.test(
      filePath,
    ) ||
    /^apps\/api\/src\/open_alm_api\/domains\/auth\/(?:access|workspace_bootstrap_schemas)\.py$/.test(
      filePath,
    ) ||
    /^apps\/web\/src\/app\/shell\/(?:AppContent|tool-view-wrapper|tool-view-route-model)\.(?:ts|tsx)$/.test(
      filePath,
    ) ||
    /^apps\/web\/src\/components\/layout\/(?:app-bar-model|useAppBarController)\.ts$/.test(
      filePath,
    ) ||
    filePath === 'apps/web/src/platform/workspaces/workspaces-api.ts' ||
    /^apps\/web\/src\/app-modules\/ai\/views\/(?:RagSearchView|RagSearchViewParts|rag-search-view-model|useRagSearchController)\.(?:ts|tsx)$/.test(
      filePath,
    )
  );
}

function hasHeading(description, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^##\\s+${escaped}\\s*$`, 'im').test(description);
}

function includesSha(description, sha) {
  return (
    Boolean(sha) &&
    description.toLowerCase().includes(sha.slice(0, 8).toLowerCase())
  );
}

export function checkMergeRequestContractEvidence({
  changes = [],
  description = '',
  env = process.env,
  mergeResultError = null,
  readFile,
  repoRoot = process.cwd(),
} = {}) {
  if (isMergeRequestPipeline(env) && !env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME) {
    return {
      ok: false,
      required: true,
      relevantPaths: [],
      failures: [
        'CI_MERGE_REQUEST_TARGET_BRANCH_NAME is required in an MR pipeline.',
      ],
    };
  }
  if (!isFeatureMergeRequestToDev(env)) {
    return { ok: true, required: false, relevantPaths: [], failures: [] };
  }

  const changedPaths = [
    ...new Set(
      changes.flatMap((change) =>
        [change.path, change.previousPath].filter(Boolean),
      ),
    ),
  ].sort();
  const domainAppPaths = changedPaths.filter(isDomainAppDeliveryPath);
  const primaryAppPaths = changedPaths.filter(isPrimaryAppOwnedDeliveryPath);
  const harnessPolicyPaths = changedPaths.filter(isHarnessPolicyPath);
  if (domainAppPaths.length > 0 && harnessPolicyPaths.length > 0) {
    return {
      ok: false,
      required: true,
      evidenceKind: 'split-required',
      relevantPaths: [...domainAppPaths, ...harnessPolicyPaths].sort(),
      failures: [
        'App delivery and harness/policy changes must be split into separate merge requests.',
      ],
    };
  }

  const migrationRisks = changes
    .map((change) => migrationRiskForChange(change, { readFile, repoRoot }))
    .filter(Boolean);
  const riskyMigrationPaths = new Set(migrationRisks.map((risk) => risk.path));
  const workspaceKeywordSearchContractChange = changedPaths.some(
    isWorkspaceKeywordSearchContractPath,
  );
  const appSandboxEvidence = isAppSandboxMergeRequest(env);
  const coreEnablementEvidence =
    isCorePlatformMergeRequest(env) &&
    (primaryAppPaths.length > 0 || workspaceKeywordSearchContractChange) &&
    (changedPaths.some(isProtectedCorePath) || riskyMigrationPaths.size > 0);
  if (!appSandboxEvidence && !coreEnablementEvidence) {
    return { ok: true, required: false, relevantPaths: [], failures: [] };
  }

  const relevantPaths = changedPaths.filter((filePath) =>
    appSandboxEvidence
      ? isDomainAppDeliveryPath(filePath)
      : isPrimaryAppOwnedDeliveryPath(filePath) ||
        isProtectedCorePath(filePath) ||
        isWorkspaceKeywordSearchContractPath(filePath) ||
        riskyMigrationPaths.has(filePath),
  );
  if (relevantPaths.length === 0) {
    return { ok: true, required: false, relevantPaths, failures: [] };
  }

  const evidenceKind = coreEnablementEvidence
    ? 'core-enablement'
    : 'app-sandbox';
  const evidenceMarker = coreEnablementEvidence
    ? CORE_ENABLEMENT_MARKER
    : CONTRACT_EVIDENCE_MARKER;
  const requiredHeadings = coreEnablementEvidence
    ? CORE_REQUIRED_HEADINGS
    : VIBE_REQUIRED_HEADINGS;
  const requiredCheckIds = coreEnablementEvidence
    ? CORE_REQUIRED_CHECK_IDS
    : REQUIRED_CHECK_IDS;
  const requiredFieldIds = coreEnablementEvidence
    ? CORE_REQUIRED_FIELD_IDS
    : REQUIRED_FIELD_IDS;
  const templatePath = coreEnablementEvidence
    ? '.gitlab/merge_request_templates/Core_Enablement.md'
    : '.gitlab/merge_request_templates/Vibe_Domain_App.md';

  const failures = [];
  if (!env.CI_COMMIT_SHA) {
    failures.push('CI_COMMIT_SHA is required for latest-source evidence.');
  }
  if (!env.CI_MERGE_REQUEST_DIFF_BASE_SHA) {
    failures.push(
      'CI_MERGE_REQUEST_DIFF_BASE_SHA is required for full-diff evidence.',
    );
  }
  if (mergeResultError) {
    failures.push(`Target-branch merge simulation failed: ${mergeResultError}`);
  }
  if (
    String(env.CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED).toLowerCase() ===
    'true'
  ) {
    failures.push(
      "MR description exceeds GitLab CI's 2,700-character limit. Keep evidence concise and link to logs.",
    );
  }
  if (!description.includes(evidenceMarker)) {
    failures.push(`Use ${templatePath} and preserve its contract marker.`);
  }
  for (const heading of requiredHeadings) {
    if (!hasHeading(description, heading)) {
      failures.push(`Missing required MR section: ## ${heading}`);
    }
  }

  const descriptionLines = description.split(/\r?\n/);
  for (const checkId of requiredCheckIds) {
    const marker = `<!-- open-alm:check:${checkId} -->`;
    const matchingLines = descriptionLines.filter((line) =>
      line.includes(marker),
    );
    if (matchingLines.length !== 1) {
      failures.push(
        `Required contract check ${checkId} must appear exactly once; found ${matchingLines.length}.`,
      );
      continue;
    }
    if (!/^\s*-\s*\[[xX]\]/.test(matchingLines[0])) {
      failures.push(`Required contract check ${checkId} is not complete.`);
    }
  }
  const fieldValues = new Map();
  for (const fieldId of requiredFieldIds) {
    const marker = `<!-- open-alm:field:${fieldId} -->`;
    const matchingLines = descriptionLines.filter((line) =>
      line.includes(marker),
    );
    if (matchingLines.length !== 1) {
      failures.push(
        `Required evidence field ${fieldId} must appear exactly once; found ${matchingLines.length}.`,
      );
      continue;
    }
    const value = matchingLines[0].split(marker, 2)[1]?.trim() ?? '';
    fieldValues.set(fieldId, value);
    if (
      !value ||
      /^(?:REPLACE_ME|TBD|TODO)$/i.test(value) ||
      /^N\/?A\s*$/i.test(value)
    ) {
      failures.push(
        `Required evidence field ${fieldId} needs a value or N/A with a reason.`,
      );
    }
  }
  const workspaceKeywordSearchEvidence =
    fieldValues.get('workspace-keyword-search') ?? '';
  if (
    workspaceKeywordSearchEvidence &&
    !/^(?:REPLACE_ME|TBD|TODO)$/i.test(workspaceKeywordSearchEvidence)
  ) {
    if (/^none\b/i.test(workspaceKeywordSearchEvidence)) {
      if (workspaceKeywordSearchContractChange) {
        failures.push(
          'workspace-keyword-search changes require "workspace — ..." evidence; "none" is not allowed.',
        );
      }
      if (!/^none\s+[—-]\s+\S.{2,}$/i.test(workspaceKeywordSearchEvidence)) {
        failures.push(
          'workspace-keyword-search evidence must use "none — reason" with a concrete reason.',
        );
      }
    } else if (/^workspace\b/i.test(workspaceKeywordSearchEvidence)) {
      const missingEvidence = [
        'owner',
        'entity',
        'resource',
        'projection',
        'hook',
        'test',
        'acl',
        'backfill',
        'rollback',
      ].filter(
        (token) =>
          !workspaceKeywordSearchEvidence.toLowerCase().includes(token),
      );
      if (missingEvidence.length > 0) {
        failures.push(
          'workspace-keyword-search workspace evidence is missing: ' +
            missingEvidence.join(', '),
        );
      }
    } else {
      failures.push(
        'workspace-keyword-search evidence must start with "none — reason" or "workspace — ...".',
      );
    }
  }

  const unchecked = description.match(/^\s*-\s*\[\s\]\s+.+$/gm) ?? [];
  if (unchecked.length > 0) {
    failures.push(
      `Complete or explicitly resolve every contract checklist item; ${unchecked.length} remain unchecked.`,
    );
  }
  if (/\bREPLACE_ME\b/.test(description)) {
    failures.push(
      'Replace the target-base and latest-source SHA placeholders with reviewed SHAs.',
    );
  }
  if (!includesSha(description, env.CI_COMMIT_SHA)) {
    failures.push(
      'Verification evidence does not name the current CI source SHA.',
    );
  }
  if (!includesSha(description, env.CI_MERGE_REQUEST_DIFF_BASE_SHA)) {
    failures.push(
      'Verification evidence does not name the current MR diff-base SHA.',
    );
  }
  return {
    ok: failures.length === 0,
    required: true,
    evidenceKind,
    relevantPaths,
    failures,
  };
}

export function runCli({ env = process.env, changes = null } = {}) {
  let mergeResultError = null;
  if (isFeatureMergeRequestToDev(env)) {
    const targetRef = `origin/${env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME}`;
    try {
      runGit(['merge-tree', '--write-tree', targetRef, 'HEAD']);
    } catch (error) {
      mergeResultError = error instanceof Error ? error.message : String(error);
    }
  }
  const result = checkMergeRequestContractEvidence({
    changes: changes ?? collectGitChanges({ env }),
    description: env.CI_MERGE_REQUEST_DESCRIPTION ?? '',
    env,
    mergeResultError,
  });
  if (!result.required) {
    console.log('[mr-contract-evidence] not required for this pipeline/diff');
    return 0;
  }
  if (!result.ok) {
    for (const failure of result.failures) {
      console.error(`[mr-contract-evidence] ${failure}`);
    }
    console.error(
      `[mr-contract-evidence] app delivery paths: ${result.relevantPaths.join(', ')}`,
    );
    return 1;
  }
  console.log('[mr-contract-evidence] complete');
  return 0;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  process.exitCode = runCli();
}
