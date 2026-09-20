#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const SHA = /^[a-f0-9]{40}$/;
const IID = /^[1-9][0-9]*$/;

function invoke(command, args, cwd) {
  return execFileSync(command, args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

function requireShape(mr, expectedIid) {
  const pipeline = mr?.head_pipeline;
  if (
    mr?.iid !== Number(expectedIid) ||
    mr?.state !== 'merged' ||
    mr?.source_branch !== 'dev' ||
    mr?.target_branch !== 'main' ||
    !Number.isInteger(mr?.source_project_id) ||
    mr.source_project_id !== mr?.target_project_id ||
    !SHA.test(mr?.sha ?? '') ||
    !SHA.test(mr?.merge_commit_sha ?? '') ||
    !Number.isInteger(pipeline?.id) ||
    pipeline.id < 1 ||
    pipeline?.project_id !== mr.target_project_id ||
    pipeline?.source !== 'merge_request_event' ||
    pipeline?.ref !== `refs/merge-requests/${expectedIid}/head` ||
    pipeline?.status !== 'success' ||
    pipeline?.sha !== mr.sha
  ) {
    throw new Error(
      'Release MR must be a merged same-project dev-to-main MR with a successful current release pipeline.',
    );
  }
  return pipeline;
}

export function validateReleaseEvidence(
  mr,
  { expectedIid, headRevision, headTree, sourceTree, pipelineJobs },
) {
  if (!IID.test(String(expectedIid)))
    throw new Error('Release MR IID must be a positive integer.');
  const pipeline = requireShape(mr, String(expectedIid));
  if (mr.merge_commit_sha !== headRevision)
    throw new Error(
      'Release MR merge commit does not match the production checkout.',
    );
  if (!SHA.test(headTree) || !SHA.test(sourceTree) || headTree !== sourceTree)
    throw new Error(
      'Validated release source tree does not match the production checkout tree.',
    );
  if (
    !Array.isArray(pipelineJobs) ||
    !pipelineJobs.some(
      (job) =>
        job?.name === 'release_validation' &&
        job?.status === 'success' &&
        job?.allow_failure === false,
    )
  )
    throw new Error(
      'Release pipeline does not contain a successful required release_validation job.',
    );
  return {
    sourceRevision: mr.sha,
    mergeRevision: mr.merge_commit_sha,
    pipelineId: pipeline.id,
  };
}

export function readReleaseEvidence(rootDir, iid, { run = invoke } = {}) {
  if (!IID.test(String(iid)))
    throw new Error('Release MR IID must be a positive integer.');
  let mr;
  try {
    mr = JSON.parse(
      run('glab', ['mr', 'view', String(iid), '--output', 'json'], rootDir),
    );
  } catch {
    throw new Error('Could not read release MR evidence from GitLab.');
  }
  requireShape(mr, String(iid));
  let pipelineJobs;
  try {
    pipelineJobs = JSON.parse(
      run(
        'glab',
        [
          'api',
          `projects/${mr.target_project_id}/pipelines/${mr.head_pipeline.id}/jobs?per_page=100`,
        ],
        rootDir,
      ),
    );
  } catch {
    throw new Error('Could not read release pipeline jobs from GitLab.');
  }
  let headRevision;
  let headTree;
  let sourceTree;
  try {
    headRevision = run('git', ['-C', rootDir, 'rev-parse', 'HEAD'], rootDir);
    headTree = run('git', ['-C', rootDir, 'rev-parse', 'HEAD^{tree}'], rootDir);
    sourceTree = run(
      'git',
      ['-C', rootDir, 'rev-parse', `${mr.sha}^{tree}`],
      rootDir,
    );
  } catch {
    throw new Error(
      'Could not resolve release commits in the production checkout.',
    );
  }
  return validateReleaseEvidence(mr, {
    expectedIid: String(iid),
    headRevision,
    headTree,
    sourceTree,
    pipelineJobs,
  });
}

export function main(args = process.argv.slice(2)) {
  if (args.length !== 2) {
    throw new Error('Usage: prod-app-release.mjs <prod-root> <release-mr-iid>');
  }
  const evidence = readReleaseEvidence(args[0], args[1]);
  process.stdout.write(
    `${evidence.sourceRevision}\n${evidence.mergeRevision}\n${evidence.pipelineId}\n`,
  );
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    main();
  } catch (error) {
    console.error(`[prod-app-release] ${error.message}`);
    process.exitCode = 1;
  }
}
