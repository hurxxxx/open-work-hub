import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import {
  CODEOWNERS_PATH,
  CODEOWNERS_REQUIRED_RULES,
  GUARDRAIL_ARTIFACT_PATH,
} from './policy.mjs';

function parseCodeowners(source) {
  const rules = [];
  const errors = [];

  source.split(/\r?\n/).forEach((rawLine, index) => {
    const withoutComment = rawLine.replace(/\s+#.*$/, '').trim();
    if (
      !withoutComment ||
      withoutComment.startsWith('#') ||
      withoutComment.startsWith('[')
    ) {
      return;
    }

    const [pattern, ...owners] = withoutComment.split(/\s+/);
    if (!pattern) {
      return;
    }
    if (owners.length === 0) {
      errors.push({
        filePath: CODEOWNERS_PATH,
        message: `CODEOWNERS rule on line ${index + 1} has no owner: ${pattern}`,
      });
    }
    for (const owner of owners) {
      if (!/^@[\w.-]+(?:\/[\w.-]+)*$/.test(owner)) {
        errors.push({
          filePath: CODEOWNERS_PATH,
          message: `CODEOWNERS owner on line ${index + 1} must be a GitLab @user or @group path: ${owner}`,
        });
      }
    }
    rules.push({ pattern, owners, line: index + 1 });
  });

  return { rules, errors };
}

export function validateCodeownersProtectedSurface({
  repoRoot = process.cwd(),
} = {}) {
  const absolutePath = path.join(repoRoot, CODEOWNERS_PATH);
  if (!fs.existsSync(absolutePath)) {
    return {
      ok: false,
      errors: [
        {
          filePath: CODEOWNERS_PATH,
          message:
            'CODEOWNERS is required for protected surface owner routing.',
        },
      ],
    };
  }

  const { rules, errors } = parseCodeowners(
    fs.readFileSync(absolutePath, 'utf8'),
  );
  const patterns = new Set(
    rules.filter((rule) => rule.owners.length > 0).map((rule) => rule.pattern),
  );
  for (const requiredPattern of CODEOWNERS_REQUIRED_RULES) {
    if (!patterns.has(requiredPattern)) {
      errors.push({
        filePath: CODEOWNERS_PATH,
        message: `Missing protected surface owner rule: ${requiredPattern}`,
      });
    }
  }

  return { ok: errors.length === 0, errors };
}

function extractGitlabJobBlock(source, jobName) {
  const lines = source.split(/\r?\n/);
  const startIndex = lines.findIndex((line) => line === `${jobName}:`);
  if (startIndex < 0) {
    return null;
  }

  const block = [lines[startIndex]];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^[A-Za-z0-9_.-]+:\s*$/.test(line)) {
      break;
    }
    block.push(line);
  }
  return block.join('\n');
}

function extractGitlabChildBlock(jobBlock, key) {
  const lines = jobBlock.split(/\r?\n/);
  const startIndex = lines.findIndex((line) => line === `  ${key}:`);
  if (startIndex < 0) {
    return null;
  }

  const block = [lines[startIndex]];
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^  [A-Za-z0-9_.-]+:\s*/.test(line)) {
      break;
    }
    block.push(line);
  }
  return block.join('\n').trimEnd();
}

function countYamlKey(source, key, indent = 0) {
  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const keyPattern = `(?:${escapedKey}|["']${escapedKey}["'])`;
  const pattern = new RegExp(`^${' '.repeat(indent)}${keyPattern}:`, 'gm');
  return [...source.matchAll(pattern)].length;
}

function validateCodexReviewCiContract({ source, filePath, errors }) {
  if (/^(?:include|["']include["']):/m.test(source)) {
    errors.push({
      filePath,
      message:
        'GitLab CI includes are not allowed because codex_review must be fully auditable in this file.',
    });
  }
  if (countYamlKey(source, 'stages') !== 1) {
    errors.push({
      filePath,
      message: 'GitLab CI must declare exactly one top-level stages key.',
    });
  }
  if (countYamlKey(source, 'codex_review') !== 1) {
    errors.push({
      filePath,
      message: 'GitLab CI must declare exactly one codex_review job.',
    });
  }
  const stageMatch = /^stages:\s*\n((?:\s+-\s+[^\n]+\n?)+)/m.exec(source);
  const stages = stageMatch
    ? [...stageMatch[1].matchAll(/^\s+-\s+(.+)$/gm)].map((match) =>
        match[1].trim(),
      )
    : [];
  const validateIndex = stages.indexOf('validate');
  const reviewIndex = stages.indexOf('review');
  const publishIndex = stages.indexOf('publish');
  if (
    validateIndex < 0 ||
    reviewIndex <= validateIndex ||
    publishIndex <= reviewIndex
  ) {
    errors.push({
      filePath,
      message:
        'GitLab stages must run validate before review and review before publish.',
    });
  }

  const codexReview = extractGitlabJobBlock(source, 'codex_review');
  if (!codexReview) {
    errors.push({ filePath, message: 'codex_review job is required.' });
    return;
  }
  for (const key of [
    'stage',
    'tags',
    'inherit',
    'dependencies',
    'allow_failure',
    'rules',
    'variables',
    'before_script',
    'script',
    'after_script',
    'artifacts',
  ]) {
    if (countYamlKey(codexReview, key, 2) !== 1) {
      errors.push({
        filePath,
        message: `codex_review must declare exactly one direct ${key} key.`,
      });
    }
  }
  if (countYamlKey(codexReview, 'needs', 2) !== 0) {
    errors.push({
      filePath,
      message:
        'codex_review must not declare needs because feature MR review is runner-only.',
    });
  }
  if (!/^  stage:\s*review\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message: 'codex_review must run in the dedicated review stage.',
    });
  }
  if (!/^  dependencies:\s*\[\]\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message:
        'codex_review must declare dependencies: [] to avoid untrusted artifact downloads.',
    });
  }
  if (!/^  allow_failure:\s*false\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message: 'codex_review must keep allow_failure: false.',
    });
  }
  if (!/^  before_script:\s*\[\]\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message: 'codex_review must explicitly disable before_script.',
    });
  }
  if (!/^  after_script:\s*\[\]\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message: 'codex_review must explicitly disable after_script.',
    });
  }
  if (!/^    GIT_DEPTH:\s*["']?0["']?\s*$/m.test(codexReview)) {
    errors.push({
      filePath,
      message: 'codex_review must use GIT_DEPTH: "0" for full-diff review.',
    });
  }
  if (
    !codexReview.includes('    - /home/dwdcc/.local/bin/ai-do-codex-review-ci')
  ) {
    errors.push({
      filePath,
      message:
        'codex_review must execute the trusted runner-local review script.',
    });
  }

  const expectedRules = `  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "dev" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID'
      when: always`;
  if (extractGitlabChildBlock(codexReview, 'rules') !== expectedRules) {
    errors.push({
      filePath,
      message:
        'codex_review rules must always run exactly once for same-project merge requests targeting dev.',
    });
  }

  const expectedTags = `  tags:
    - codex-local`;
  if (extractGitlabChildBlock(codexReview, 'tags') !== expectedTags) {
    errors.push({
      filePath,
      message: 'codex_review must run only on the codex-local runner tag.',
    });
  }

  const expectedInherit = `  inherit:
    default: false
    variables: false`;
  if (extractGitlabChildBlock(codexReview, 'inherit') !== expectedInherit) {
    errors.push({
      filePath,
      message:
        'codex_review must disable inherited defaults and global variables.',
    });
  }

  const expectedVariables = `  variables:
    GIT_DEPTH: "0"`;
  if (extractGitlabChildBlock(codexReview, 'variables') !== expectedVariables) {
    errors.push({
      filePath,
      message: 'codex_review must keep the exact full-depth variable contract.',
    });
  }

  const expectedScript = `  script:
    - /home/dwdcc/.local/bin/ai-do-codex-review-ci`;
  if (extractGitlabChildBlock(codexReview, 'script') !== expectedScript) {
    errors.push({
      filePath,
      message:
        'codex_review must execute only the trusted runner-local review script.',
    });
  }

  const artifacts = extractGitlabChildBlock(codexReview, 'artifacts');
  if (!artifacts) {
    errors.push({
      filePath,
      message: 'codex_review restricted artifacts are required.',
    });
    return;
  }
  for (const key of ['when', 'expire_in', 'access', 'paths']) {
    if (countYamlKey(artifacts, key, 4) !== 1) {
      errors.push({
        filePath,
        message: `codex_review artifacts must declare exactly one ${key} key.`,
      });
    }
  }
  if (!/^    when:\s*always\s*$/m.test(artifacts)) {
    errors.push({
      filePath,
      message: 'codex_review artifacts must use artifacts.when: always.',
    });
  }
  if (!/^    access:\s*maintainer\s*$/m.test(artifacts)) {
    errors.push({
      filePath,
      message: 'codex_review artifacts must remain maintainer-only.',
    });
  }
  for (const artifactPath of [
    'codex-review.md',
    'codex-review-comment.md',
    'codex-review-pipeline-context.md',
    'codex-review-policy-context.md',
    'codex-review-prior-context.md',
    'codex-review-progress-start.md',
    'codex-review-prompt.md',
    'codex-review-run.log',
  ]) {
    if (!artifacts.includes(`      - ${artifactPath}`)) {
      errors.push({
        filePath,
        message: `codex_review artifacts must include ${artifactPath}.`,
      });
    }
  }

  const expectedCodexReview = `codex_review:
  stage: review
  tags:
    - codex-local
  inherit:
    default: false
    variables: false
  dependencies: []
  allow_failure: false
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "dev" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID'
      when: always
  variables:
    GIT_DEPTH: "0"
  before_script: []
  script:
    - /home/dwdcc/.local/bin/ai-do-codex-review-ci
  after_script: []
  artifacts:
    when: always
    expire_in: 14 days
    access: maintainer
    paths:
      - codex-review.md
      - codex-review-comment.md
      - codex-review-pipeline-context.md
      - codex-review-policy-context.md
      - codex-review-prior-context.md
      - codex-review-progress-start.md
      - codex-review-prompt.md
      - codex-review-run.log`;
  if (codexReview.trimEnd() !== expectedCodexReview) {
    errors.push({
      filePath,
      message:
        'codex_review must match the canonical non-inheriting runner-only job block.',
    });
  }
}

export function validateGitlabCiGuardrailArtifact({
  repoRoot = process.cwd(),
} = {}) {
  const filePath = '.gitlab-ci.yml';
  const absolutePath = path.join(repoRoot, filePath);
  const errors = [];
  if (!fs.existsSync(absolutePath)) {
    return {
      ok: false,
      errors: [{ filePath, message: 'GitLab CI configuration is required.' }],
    };
  }

  const source = fs.readFileSync(absolutePath, 'utf8');
  const trustedRunnerPath = fileURLToPath(
    new URL('../codex-review-ci.sh', import.meta.url),
  );
  const contractCheck = spawnSync(
    'bash',
    [trustedRunnerPath, '--validate-gitlab-ci-contract', absolutePath],
    {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  if (contractCheck.status !== 0) {
    errors.push({
      filePath,
      message:
        'Required GitLab CI jobs must match the enforced runner-owned semantic contract.',
    });
  }
  validateCodexReviewCiContract({ source, filePath, errors });
  const releaseValidation = extractGitlabJobBlock(
    source,
    'release_validation',
  );
  if (!releaseValidation) {
    errors.push({ filePath, message: 'release_validation job is required.' });
    return { ok: false, errors };
  }
  if (!/^\s+GIT_DEPTH:\s*["']?0["']?\s*$/m.test(releaseValidation)) {
    errors.push({
      filePath,
      message:
        'release_validation must use GIT_DEPTH: "0" for complete release evidence.',
    });
  }
  for (const command of [
    'pnpm check:app-platform-guardrails:artifact',
    'pnpm ci:harness',
    'pnpm nx run api:ci-contracts',
    'node scripts/run-affected-api-tests.mjs migration',
    'node scripts/run-affected-api-tests.mjs standard',
    'node scripts/run-affected-api-tests.mjs slow',
    'node scripts/run-affected-api-tests.mjs external',
    'pnpm ci:app-web-contracts',
  ]) {
    if (!releaseValidation.includes(command)) {
      errors.push({
        filePath,
        message: `release_validation must run ${command}.`,
      });
    }
  }
  if (
    !/\n\s+artifacts:\n/.test(releaseValidation) ||
    !/\n\s+when:\s+always\b/.test(releaseValidation) ||
    !releaseValidation.includes(GUARDRAIL_ARTIFACT_PATH)
  ) {
    errors.push({
      filePath,
      message:
        'release_validation must always publish the app platform guardrail artifact.',
    });
  }


  return { ok: errors.length === 0, errors };
}
