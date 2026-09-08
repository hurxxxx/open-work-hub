#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import YAML from 'yaml';

export const CONTRACT = 'feature-codex-release-v1';
export const VALIDATION_IMAGE = 'open-work-hub-validation:node22-python312';
export const VALIDATION_TAG = 'open-work-hub-validation';
export const CODEX_ENTRYPOINT = '/usr/local/bin/open-work-hub-codex-review-ci';

export const FEATURE_MR_RULE =
  '$CI_PIPELINE_SOURCE == "merge_request_event" && ' +
  '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "dev" && ' +
  '$CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID';
export const RELEASE_MR_RULE =
  '$CI_PIPELINE_SOURCE == "merge_request_event" && ' +
  '$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == "dev" && ' +
  '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main" && ' +
  '$CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID';
export const CONTRACTS_TAG_RULE =
  '$CI_COMMIT_TAG =~ ' +
  '/^contracts-v[0-9]+\\.[0-9]+\\.[0-9]+(-[0-9A-Za-z.-]+)?$/';

const REDIS_SERVICE =
  'redis@sha256:5a77f0f4698389019f828f6387049ce1d5adbea204e56422aa7720dab7034287';
const MINIO_SERVICE =
  'minio/minio@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e';
const OPENSEARCH_SERVICE = 'open-work-hub-opensearch:3.3.2-nori';
const RETIRED_IDENTIFIER_PATTERN = new RegExp(
  [
    String.raw`\bA` + String.raw`I_DO\b`,
    String.raw`\ba` + String.raw`i_do\b`,
    String.raw`/projects/a` + String.raw`i-do\b`,
    String.raw`\bdw` + String.raw`dcc\b`,
  ].join('|'),
  'i',
);

export function expectedGitlabPipelineConfig() {
  const targetRef = '${CI_MERGE_REQUEST_TARGET_BRANCH_NAME}';
  return {
    workflow: {
      auto_cancel: { on_new_commit: 'interruptible' },
      rules: [
        { if: FEATURE_MR_RULE },
        { if: RELEASE_MR_RULE },
        { if: CONTRACTS_TAG_RULE },
        { when: 'never' },
      ],
    },
    stages: ['validate', 'review', 'publish'],
    release_validation: {
      stage: 'validate',
      image: VALIDATION_IMAGE,
      services: [
        {
          name: REDIS_SERVICE,
          alias: 'redis',
          command: ['redis-server', '--save', '', '--appendonly', 'no'],
          variables: { HEALTHCHECK_TCP_PORT: '6379' },
        },
        {
          name: MINIO_SERVICE,
          alias: 'minio',
          command: ['server', '/data', '--console-address=:9001'],
          variables: {
            HEALTHCHECK_TCP_PORT: '9000',
            MINIO_ROOT_PASSWORD: 'open_work_hub_ci_minio_job_only',
            MINIO_ROOT_USER: 'open_work_hub_ci_minio',
          },
        },
        {
          name: OPENSEARCH_SERVICE,
          alias: 'opensearch',
          variables: {
            HEALTHCHECK_TCP_PORT: '9200',
            'discovery.type': 'single-node',
            DISABLE_SECURITY_PLUGIN: 'true',
            OPENSEARCH_JAVA_OPTS: '-Xms512m -Xmx512m',
          },
        },
      ],
      tags: [VALIDATION_TAG],
      inherit: {
        default: false,
        variables: ['OPEN_WORK_HUB_CI_POSTGRES_DSN'],
      },
      dependencies: [],
      allow_failure: false,
      interruptible: true,
      resource_group: 'open-work-hub-release-validation',
      environment: { name: 'ci-validation', action: 'access' },
      variables: {
        GIT_DEPTH: '0',
        OPEN_WORK_HUB_API_PYTEST_WORKERS: '2',
        VITEST_MAX_WORKERS: '1',
        PLAYWRIGHT_WORKERS: '1',
        OPEN_WORK_HUB_API_COLLAB_REDIS_URL: 'redis://redis:6379/0',
        OPEN_WORK_HUB_API_REALTIME_REDIS_URL: 'redis://redis:6379/0',
        OPEN_WORK_HUB_API_TEST_RUN_ID: '$CI_JOB_ID',
        OPEN_WORK_HUB_ENV_PROFILE: 'test',
        OPEN_WORK_HUB_MINIO_ACCESS_KEY: 'open_work_hub_ci_minio',
        OPEN_WORK_HUB_MINIO_BUCKET: 'open-work-hub-ci',
        OPEN_WORK_HUB_MINIO_ENDPOINT: 'http://minio:9000',
        OPEN_WORK_HUB_MINIO_SECRET_KEY: 'open_work_hub_ci_minio_job_only',
        OPEN_WORK_HUB_OPENSEARCH_INDEX_PREFIX: 'open-work-hub-ci',
        OPEN_WORK_HUB_OPENSEARCH_URL: 'http://opensearch:9200',
        OPEN_WORK_HUB_POSTGRES_DSN: '$OPEN_WORK_HUB_CI_POSTGRES_DSN',
        OPEN_WORK_HUB_TEST_MINIO_ACCESS_KEY: 'open_work_hub_ci_minio',
        OPEN_WORK_HUB_TEST_MINIO_ENDPOINT: 'http://minio:9000',
        OPEN_WORK_HUB_TEST_MINIO_SECRET_KEY: 'open_work_hub_ci_minio_job_only',
        OPEN_WORK_HUB_TEST_NON_PRODUCTION_ACK: 'non-production',
        OPEN_WORK_HUB_TEST_OPENSEARCH_URL: 'http://opensearch:9200',
        OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN:
          '$OPEN_WORK_HUB_CI_POSTGRES_DSN',
        OPEN_WORK_HUB_TEST_REDIS_URL: 'redis://redis:6379/0',
        OPEN_WORK_HUB_WORKER_BROKER_URL: 'memory://',
        OPEN_WORK_HUB_WORKER_QUEUE_GROUP: 'default',
        OPEN_WORK_HUB_WORKER_RESULT_BACKEND: 'cache+memory://',
      },
      rules: [{ if: RELEASE_MR_RULE }],
      before_script: [],
      script: [
        'bash scripts/ci/prepare-validation-runtime.sh',
        'cp .env.example .env',
        "sed -i 's#^OPEN_WORK_HUB_ENV_PROFILE=.*#OPEN_WORK_HUB_ENV_PROFILE=test#; s#^OPEN_WORK_HUB_WORKER_BROKER_URL=.*#OPEN_WORK_HUB_WORKER_BROKER_URL=memory://#; s#^OPEN_WORK_HUB_WORKER_RESULT_BACKEND=.*#OPEN_WORK_HUB_WORKER_RESULT_BACKEND=cache+memory://#' .env",
        "grep -qx 'OPEN_WORK_HUB_ENV_PROFILE=test' .env",
        "grep -qx 'OPEN_WORK_HUB_WORKER_BROKER_URL=memory://' .env",
        "grep -qx 'OPEN_WORK_HUB_WORKER_RESULT_BACKEND=cache+memory://' .env",
        'printf \'release_validation source=%s target=%s base=%s\\n\' "$CI_COMMIT_SHA" "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME" "$CI_MERGE_REQUEST_DIFF_BASE_SHA" > release-validation-context.md',
        'node scripts/check-gitlab-pipeline.mjs',
        'node scripts/check-mr-target-policy.mjs',
        `git fetch --no-tags origin "+refs/heads/${targetRef}:refs/remotes/origin/${targetRef}"`,
        'node scripts/check-mr-contract-evidence.mjs',
        'pnpm test:gitlab-pipeline',
        'pnpm test:mr-target-policy',
        'pnpm test:mr-contract-evidence',
        'node scripts/release-validation.mjs ci',
      ],
      after_script: [],
      artifacts: {
        when: 'always',
        expire_in: '14 days',
        access: 'maintainer',
        paths: ['release-validation-context.md', 'test-results/'],
      },
    },
    codex_review: {
      stage: 'review',
      tags: ['codex-local'],
      inherit: { default: false, variables: false },
      dependencies: [],
      allow_failure: false,
      rules: [{ if: FEATURE_MR_RULE, when: 'always' }],
      variables: { GIT_DEPTH: '0' },
      before_script: [],
      script: [CODEX_ENTRYPOINT],
      after_script: [],
      artifacts: {
        when: 'always',
        expire_in: '14 days',
        access: 'maintainer',
        paths: [
          'codex-review.md',
          'codex-review-comment.md',
          'codex-review-pipeline-context.md',
          'codex-review-policy-context.md',
          'codex-review-prior-context.md',
          'codex-review-progress-start.md',
          'codex-review-prompt.md',
          'codex-review-run.log',
        ],
      },
    },
    contracts_publish: {
      stage: 'publish',
      image: VALIDATION_IMAGE,
      tags: [VALIDATION_TAG],
      inherit: { default: false, variables: false },
      dependencies: [],
      allow_failure: false,
      rules: [{ if: CONTRACTS_TAG_RULE }],
      before_script: [],
      script: [
        'bash scripts/ci/prepare-validation-runtime.sh',
        'node scripts/check-gitlab-pipeline.mjs',
        'node scripts/check-contracts-publish-tag.mjs',
        'pnpm build:contracts',
        'export NPM_CONFIG_USERCONFIG="$(mktemp)"',
        'trap \'rm -f "$NPM_CONFIG_USERCONFIG"\' EXIT',
        'printf \'@open-work-hub:registry=%s/projects/%s/packages/npm/\\n\' "$CI_API_V4_URL" "$CI_PROJECT_ID" > "$NPM_CONFIG_USERCONFIG"',
        'printf \'//%s/projects/%s/packages/npm/:_authToken=%s\\n\' "${CI_API_V4_URL#*://}" "$CI_PROJECT_ID" "$CI_JOB_TOKEN" >> "$NPM_CONFIG_USERCONFIG"',
        'cd packages/contracts',
        'pnpm publish --no-git-checks',
      ],
    },
  };
}

function parseYamlConfig(source, label) {
  const doc = YAML.parseDocument(source, { uniqueKeys: true });
  if (doc.errors.length > 0) {
    throw new Error(`${label}: ${doc.errors[0].message}`);
  }
  return doc.toJS();
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function assertEqual(actual, expected, label) {
  if (stableJson(actual) !== stableJson(expected)) {
    throw new Error(`${label} does not match ${CONTRACT}.`);
  }
}

export function validateGitlabPipelineSource(source, label = '.gitlab-ci.yml') {
  if (RETIRED_IDENTIFIER_PATTERN.test(source)) {
    throw new Error(`${label} contains retired project identifiers.`);
  }
  const config = parseYamlConfig(source, label);
  const expected = expectedGitlabPipelineConfig();
  assertEqual(config, expected, label);
  return CONTRACT;
}

export function validateGitlabPipelineFiles(repoRoot = process.cwd()) {
  const rootCiPath = path.join(repoRoot, '.gitlab-ci.yml');
  const externalCiPath = path.join(repoRoot, 'ops/ci/ci-first.gitlab-ci.yml');
  const rootSource = fs.readFileSync(rootCiPath, 'utf8');
  const externalSource = fs.readFileSync(externalCiPath, 'utf8');
  if (rootSource !== externalSource) {
    throw new Error('root and ops GitLab CI files must be byte-identical.');
  }
  return validateGitlabPipelineSource(rootSource, rootCiPath);
}

export function main({ repoRoot = process.cwd(), output = console } = {}) {
  try {
    output.log(validateGitlabPipelineFiles(repoRoot));
    return 0;
  } catch (error) {
    output.error(
      `[gitlab-pipeline] ${error instanceof Error ? error.message : String(error)}`,
    );
    return 1;
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
