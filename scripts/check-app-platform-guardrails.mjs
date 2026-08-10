#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { formatGuardrailOutput } from './app-platform-guardrails/report.mjs';
import { runGuardrailSuite } from './app-platform-guardrails/runner.mjs';

export {
  classifyPath,
  laneCanCover,
  laneFromMergeRequestLabels,
  lanesFromMergeRequestLabels,
  laneLabel,
  normalizeLane,
  normalizePath,
  repoWideRewriteApprovalFromMergeRequestLabels,
} from './app-platform-guardrails/classifier.mjs';
export {
  checkAppPlatformGuardrails,
  dedupeChanges,
} from './app-platform-guardrails/engine.mjs';
export {
  validateAppManifestContracts,
  validateManifestContractSource,
} from './app-platform-guardrails/manifest.mjs';
export {
  validateCodeownersProtectedSurface,
  validateGitlabCiGuardrailArtifact,
} from './app-platform-guardrails/ownership.mjs';
export { LANES } from './app-platform-guardrails/policy.mjs';
export {
  formatGuardrailOutput,
  formatGuardrailReport,
} from './app-platform-guardrails/report.mjs';
export {
  appendValidationFailure,
  collectGitChanges,
  createGitChangeSource,
  DEFAULT_GUARDRAIL_VALIDATORS,
  parseGitNameStatus,
  refExists,
  resolveBaseRef,
  runGit,
  runGuardrailSuite,
  runGuardrailValidators,
} from './app-platform-guardrails/runner.mjs';
export {
  validateWindowsDevGuardrailSource,
  validateWindowsDevGuardrails,
} from './app-platform-guardrails/windows.mjs';
export { validateWorkspaceKeywordSearchHarness } from './app-platform-guardrails/workspace-keyword-search.mjs';

function requireArgValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${flag} requires a value.`);
  }
  return value;
}

export function parseArgs(argv) {
  const options = {
    baseRef: null,
    declaredLane: null,
    json: false,
    output: null,
    allowRepoWideRewrite: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--base') {
      options.baseRef = requireArgValue(argv, index, arg);
      index += 1;
    } else if (arg === '--lane') {
      options.declaredLane = requireArgValue(argv, index, arg);
      index += 1;
    } else if (arg === '--json') {
      options.json = true;
    } else if (arg === '--output') {
      options.output = requireArgValue(argv, index, arg);
      index += 1;
    } else if (arg === '--allow-repo-wide-rewrite') {
      options.allowRepoWideRewrite = true;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function printHelp() {
  console.log(`Usage: node scripts/check-app-platform-guardrails.mjs [options]

Options:
  --base <ref>                    Compare against a specific git ref.
  --lane <lane>                   Declare the primary change lane.
  --json                          Print JSON result.
  --output <path>                 Write result to a file instead of stdout.
  --allow-repo-wide-rewrite       Allow mass delete / repo-wide rewrite threshold.
  -h, --help                      Show this help.

Lane values:
  prototype, app-sandbox, shared-capability, core-platform,
  harness-and-policy, windows-admin-dev-env
`);
}

function writeOutput(output, outputPath) {
  if (outputPath) {
    fs.mkdirSync(path.dirname(path.resolve(outputPath)), { recursive: true });
    fs.writeFileSync(outputPath, `${output}\n`, 'utf8');
  } else {
    console.log(output);
  }
}

export function runCli({
  argv = process.argv.slice(2),
  env = process.env,
} = {}) {
  const options = parseArgs(argv);
  if (options.help) {
    printHelp();
    return 0;
  }

  const result = runGuardrailSuite({
    baseRef: options.baseRef,
    lane: options.declaredLane,
    env,
    allowRepoWideRewrite: options.allowRepoWideRewrite,
  });
  writeOutput(
    formatGuardrailOutput(result, { json: options.json }),
    options.output,
  );

  return result.ok ? 0 : 1;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  process.exitCode = runCli();
}
