import { fileURLToPath } from 'node:url';

const DEFAULT_DEVELOPMENT_BRANCH = 'dev';
const DEFAULT_PRODUCTION_BRANCH = 'main';

function readEnv(env, name) {
  return typeof env[name] === 'string' ? env[name].trim() : '';
}

export function evaluateMrTargetPolicy(env = process.env) {
  const pipelineSource = readEnv(env, 'CI_PIPELINE_SOURCE');
  const developmentBranch =
    readEnv(env, 'OPEN_WORK_HUB_DEVELOPMENT_BRANCH') ||
    DEFAULT_DEVELOPMENT_BRANCH;
  const productionBranch =
    readEnv(env, 'OPEN_WORK_HUB_PRODUCTION_BRANCH') ||
    DEFAULT_PRODUCTION_BRANCH;

  if (pipelineSource !== 'merge_request_event') {
    return {
      ok: true,
      skipped: true,
      message: 'skipped: not a merge request pipeline.',
    };
  }

  const sourceBranch = readEnv(env, 'CI_MERGE_REQUEST_SOURCE_BRANCH_NAME');
  const targetBranch = readEnv(env, 'CI_MERGE_REQUEST_TARGET_BRANCH_NAME');
  const missing = [];

  if (!sourceBranch) missing.push('CI_MERGE_REQUEST_SOURCE_BRANCH_NAME');
  if (!targetBranch) missing.push('CI_MERGE_REQUEST_TARGET_BRANCH_NAME');

  if (missing.length > 0) {
    return {
      ok: false,
      skipped: false,
      message: `missing required merge request variable(s): ${missing.join(', ')}.`,
    };
  }

  if (sourceBranch === targetBranch) {
    return {
      ok: false,
      skipped: false,
      message: `invalid MR branch pair: source and target are both ${sourceBranch}.`,
    };
  }

  if (sourceBranch === developmentBranch && targetBranch === productionBranch) {
    return {
      ok: true,
      skipped: false,
      message: `ok: release promotion MR ${developmentBranch} -> ${productionBranch}.`,
    };
  }

  if (targetBranch === developmentBranch && sourceBranch !== productionBranch) {
    return {
      ok: true,
      skipped: false,
      message: `ok: feature MR ${sourceBranch} -> ${developmentBranch}.`,
    };
  }

  return {
    ok: false,
    skipped: false,
    message: [
      `invalid MR branch pair: ${sourceBranch} -> ${targetBranch}.`,
      `Feature work must target ${developmentBranch}.`,
      `Only release promotion may target ${productionBranch}, and its source branch must be ${developmentBranch}.`,
    ].join(' '),
  };
}

export function main(env = process.env, output = console) {
  const result = evaluateMrTargetPolicy(env);
  const line = `[mr-target-policy] ${result.message}`;

  if (result.ok) {
    output.log(line);
    return 0;
  }

  output.error(line);
  return 1;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  process.exitCode = main();
}
