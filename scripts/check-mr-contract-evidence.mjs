#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export const CONTRACT_EVIDENCE_MARKER =
  '<!-- open-work-hub:vibe-app-contract:v1 -->';
export const CORE_ENABLEMENT_MARKER =
  '<!-- open-work-hub:core-enablement:v1 -->';

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
  'target',
  'authorization',
  'transaction',
  'file-network',
  'ai',
  'worker',
  'compatibility',
  'company-keyword-search',
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
  'company-keyword-search',
  'safety-evidence',
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
  'company-keyword-search',
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
  'company-keyword-search',
  'target-state',
  'source-sha',
  'verification',
  'remaining-risks',
]);

const CORE_API_DOMAINS = new Set([
  'admin',
  'ai',
  'auth',
  'content_access',
  'files',
  'groups',
  'organization',
  'rag',
  'retrieval',
  'search',
  'storage',
  // Changes deleting the retired domain still require core evidence.
  'workspaces',
]);

function apiDomainForPath(filePath) {
  const match =
    /^apps\/api\/src\/open_work_hub_api\/domains\/([^/]+)(?:\/|$)/.exec(
      filePath,
    );
  return match?.[1] ?? null;
}

export function isDomainAppDeliveryPath(filePath) {
  if (/^apps\/web\/src\/app-modules\//.test(filePath)) return true;
  if (/^apps\/api\/alembic\/versions\/[^/]+\.py$/.test(filePath)) return true;
  if (/^apps\/worker\/src\/open_work_hub_worker\/tasks\//.test(filePath)) {
    return true;
  }
  const apiDomain = apiDomainForPath(filePath);
  return Boolean(apiDomain && !CORE_API_DOMAINS.has(apiDomain));
}

export function isProtectedCorePath(filePath) {
  return (
    CORE_API_DOMAINS.has(apiDomainForPath(filePath)) ||
    filePath === '.gitlab-ci.yml' ||
    /^ops\/ci\//.test(filePath) ||
    /^scripts\/(?:ci\/|check-|.*\.test\.mjs$)/.test(filePath) ||
    /^\.agents\/skills\//.test(filePath) ||
    /^docs\/agents\//.test(filePath) ||
    /^packages\/(?:contracts|core-web|ui)\//.test(filePath) ||
    /^apps\/web\/src\/platform\//.test(filePath) ||
    /^apps\/api\/src\/open_work_hub_api\/api_registry\.py$/.test(filePath)
  );
}

export function isCompanyKeywordSearchContractPath(filePath) {
  return (
    /^apps\/api\/src\/open_work_hub_api\/domains\/search\//.test(filePath) ||
    /^apps\/api\/src\/open_work_hub_api\/domains\/[^/]+\/search_(?:hooks|projection|registration)\.py$/.test(
      filePath,
    ) ||
    /^apps\/web\/src\/app-modules\/ai\/views\/(?:RagSearchView|RagSearchViewParts|rag-search-view-model|useRagSearchController)\.(?:ts|tsx)$/.test(
      filePath,
    )
  );
}

function isMergeRequestPipeline(env) {
  return (
    env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
    Boolean(env.CI_MERGE_REQUEST_IID)
  );
}

function isFeatureMergeRequestToDev(env) {
  return (
    isMergeRequestPipeline(env) &&
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME === 'dev' &&
    env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME !== 'main' &&
    env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME !== 'dev'
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

function parseNameStatusLine(line) {
  const parts = line.split('\t');
  const status = parts[0] ?? '';
  if (!status) return null;
  if (status.startsWith('R') || status.startsWith('C')) {
    return { status, previousPath: parts[1] ?? '', path: parts[2] ?? '' };
  }
  return { status, path: parts[1] ?? '' };
}

export function collectGitChanges({ env = process.env } = {}) {
  const base =
    env.CI_MERGE_REQUEST_DIFF_BASE_SHA ||
    (env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME
      ? `origin/${env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME}`
      : 'origin/dev');
  const output = execFileSync(
    'git',
    ['diff', '--name-status', '-M', `${base}...HEAD`],
    {
      encoding: 'utf8',
    },
  );
  return output
    .split(/\r?\n/)
    .filter(Boolean)
    .map(parseNameStatusLine)
    .filter(Boolean);
}

function selectEvidenceKind(description, changedPaths) {
  if (description.includes(CORE_ENABLEMENT_MARKER)) {
    return 'core-enablement';
  }
  if (description.includes(CONTRACT_EVIDENCE_MARKER)) {
    return 'app-sandbox';
  }
  if (changedPaths.some(isProtectedCorePath)) {
    return 'core-enablement';
  }
  if (changedPaths.some(isDomainAppDeliveryPath)) {
    return 'app-sandbox';
  }
  return null;
}

function checkFieldValue(fieldId, value, failures) {
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

function checkSearchEvidence({
  value,
  companyKeywordSearchContractChange,
  failures,
}) {
  if (!value || /^(?:REPLACE_ME|TBD|TODO)$/i.test(value)) return;
  if (/^none\b/i.test(value)) {
    if (companyKeywordSearchContractChange) {
      failures.push(
        'company-keyword-search changes require "company - ..." evidence; "none" is not allowed.',
      );
    }
    if (!/^none\s+[--]\s+\S.{2,}$/i.test(value)) {
      failures.push(
        'company-keyword-search evidence must use "none - reason" with a concrete reason.',
      );
    }
    return;
  }
  if (/^company\b/i.test(value)) {
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
    ].filter((token) => !value.toLowerCase().includes(token));
    if (missingEvidence.length > 0) {
      failures.push(
        'company-keyword-search company evidence is missing: ' +
          missingEvidence.join(', '),
      );
    }
    return;
  }
  failures.push(
    'company-keyword-search evidence must start with "none - reason" or "company - ...".',
  );
}

export function checkMergeRequestContractEvidence({
  changes = [],
  description = '',
  env = process.env,
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
  const relevantPaths = changedPaths.filter(
    (filePath) =>
      isDomainAppDeliveryPath(filePath) ||
      isProtectedCorePath(filePath) ||
      isCompanyKeywordSearchContractPath(filePath),
  );
  const evidenceKind = selectEvidenceKind(description, changedPaths);
  if (!evidenceKind) {
    return { ok: true, required: false, relevantPaths: [], failures: [] };
  }

  const core = evidenceKind === 'core-enablement';
  const evidenceMarker = core
    ? CORE_ENABLEMENT_MARKER
    : CONTRACT_EVIDENCE_MARKER;
  const templatePath = core
    ? '.gitlab/merge_request_templates/Core_Enablement.md'
    : '.gitlab/merge_request_templates/Vibe_Domain_App.md';
  const requiredHeadings = core
    ? CORE_REQUIRED_HEADINGS
    : VIBE_REQUIRED_HEADINGS;
  const requiredCheckIds = core ? CORE_REQUIRED_CHECK_IDS : REQUIRED_CHECK_IDS;
  const requiredFieldIds = core ? CORE_REQUIRED_FIELD_IDS : REQUIRED_FIELD_IDS;
  const failures = [];

  if (!env.CI_COMMIT_SHA) {
    failures.push('CI_COMMIT_SHA is required for latest-source evidence.');
  }
  if (!env.CI_MERGE_REQUEST_DIFF_BASE_SHA) {
    failures.push(
      'CI_MERGE_REQUEST_DIFF_BASE_SHA is required for full-diff evidence.',
    );
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
    const marker = `<!-- open-work-hub:check:${checkId} -->`;
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
    const marker = `<!-- open-work-hub:field:${fieldId} -->`;
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
    checkFieldValue(fieldId, value, failures);
  }

  checkSearchEvidence({
    value: fieldValues.get('company-keyword-search') ?? '',
    companyKeywordSearchContractChange: changedPaths.some(
      isCompanyKeywordSearchContractPath,
    ),
    failures,
  });

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
  const effectiveChanges =
    changes ??
    (isFeatureMergeRequestToDev(env) ? collectGitChanges({ env }) : []);
  const result = checkMergeRequestContractEvidence({
    changes: effectiveChanges,
    description: env.CI_MERGE_REQUEST_DESCRIPTION ?? '',
    env,
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
      `[mr-contract-evidence] relevant paths: ${result.relevantPaths.join(', ')}`,
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
