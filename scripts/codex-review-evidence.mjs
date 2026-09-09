#!/usr/bin/env node
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export function queryGitLab(host, route, run = execFileSync) {
  let response;
  try {
    response = run(
      '/usr/bin/glab',
      ['api', '--hostname', host.hostname, `${host.href}/${route}`],
      {
        cwd: process.env.HOME,
        encoding: 'utf8',
        timeout: 30000,
        maxBuffer: 4 * 1024 * 1024,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { PATH: '/usr/bin:/bin', HOME: process.env.HOME, LANG: 'C.UTF-8' },
      },
    );
  } catch {
    throw new Error('Authenticated GitLab evidence request failed');
  }
  return JSON.parse(response);
}

export function verifyEvidence(env, config, query = queryGitLab) {
  function requireValue(condition, message) {
    if (!condition) throw new Error(message);
  }
  function id(name) {
    const value = env[name];
    requireValue(
      /^[1-9][0-9]*$/.test(value || ''),
      `Missing or invalid ${name}`,
    );
    return Number(value);
  }
  const host = new URL(config.api_url);
  requireValue(
    host.protocol === 'https:' &&
      !host.username &&
      !host.password &&
      host.pathname === '/api/v4' &&
      !host.search &&
      !host.hash &&
      env.CI_API_V4_URL === host.href,
    'GitLab evidence API must match the trusted HTTPS configuration',
  );
  requireValue(
    id('CI_PROJECT_ID') === config.project_id,
    'Unexpected evidence project',
  );
  const api = (route) => query(host, route);
  const projectId = id('CI_PROJECT_ID');
  const pipelineId = id('CI_PIPELINE_ID');
  const jobId = id('CI_JOB_ID');
  const mrId = id('CI_MERGE_REQUEST_IID');
  const prefix = `projects/${projectId}`;
  const project = api(prefix);
  requireValue(
    project.id === projectId &&
      project.only_allow_merge_if_pipeline_succeeds === true &&
      project.only_allow_merge_if_all_discussions_are_resolved === true,
    'Project pipeline/discussion merge gates are not enforced',
  );
  const mr = api(`${prefix}/merge_requests/${mrId}`);
  requireValue(
    mr.state === 'opened' &&
      mr.source_project_id === projectId &&
      mr.target_project_id === projectId &&
      mr.source_branch === env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME &&
      mr.target_branch === env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME &&
      mr.sha === env.CI_COMMIT_SHA &&
      mr.diff_refs?.base_sha === env.CI_MERGE_REQUEST_DIFF_BASE_SHA &&
      mr.head_pipeline?.id === pipelineId,
    'MR source, base, target or latest pipeline is stale or mismatched',
  );
  requireValue(
    mr.has_conflicts === false && mr.blocking_discussions_resolved === true,
    'MR has conflicts or unresolved blocking discussions',
  );
  const target = api(
    `${prefix}/repository/branches/${encodeURIComponent(mr.target_branch)}`,
  );
  requireValue(
    target.commit?.id === env.REVIEW_TARGET_SHA && target.protected === true,
    'Protected target SHA changed',
  );
  const protection = api(
    `${prefix}/protected_branches/${encodeURIComponent(mr.target_branch)}`,
  );
  requireValue(
    protection.allow_force_push === false &&
      protection.push_access_levels?.length > 0 &&
      protection.push_access_levels.every((level) => level.access_level === 0),
    'Target direct/force-push protection is not enforced',
  );
  const pipeline = api(`${prefix}/pipelines/${pipelineId}`);
  requireValue(
    pipeline.sha === env.CI_COMMIT_SHA &&
      pipeline.source === 'merge_request_event' &&
      pipeline.status === 'running',
    'Current MR pipeline is not running at the reviewed SHA',
  );
  const jobs = api(
    `${prefix}/pipelines/${pipelineId}/jobs?include_retried=false&per_page=100`,
  );
  requireValue(
    Array.isArray(jobs) && jobs.length > 0 && jobs.length < 100,
    'Pipeline job evidence is missing or truncated',
  );
  const current = jobs.find((job) => job.id === jobId);
  requireValue(
    current?.name === 'codex_review' &&
      current.stage === 'review' &&
      current.status === 'running' &&
      current.allow_failure === false &&
      current.commit?.id === env.CI_COMMIT_SHA &&
      current.runner?.id === id('CI_RUNNER_ID'),
    'Current required review job identity does not match',
  );
  const runner = api(`runners/${current.runner.id}`);
  requireValue(
    runner.tag_list?.includes('codex-local') &&
      runner.run_untagged === false &&
      runner.locked === true &&
      runner.runner_type === 'project_type' &&
      runner.projects?.length === 1 &&
      runner.projects[0].id === projectId,
    'Review runner is not project-scoped with the required tag',
  );
  const otherRequired = jobs.filter(
    (job) => job.id !== jobId && job.allow_failure === false,
  );
  requireValue(
    otherRequired.every((job) => job.status === 'success'),
    'Another required pipeline job has not succeeded',
  );
  const statuses = api(
    `${prefix}/repository/commits/${encodeURIComponent(env.CI_COMMIT_SHA)}/statuses?pipeline_id=${pipelineId}&all=false&per_page=100`,
  );
  requireValue(
    Array.isArray(statuses) && statuses.length < 100,
    'Commit status evidence is missing or truncated',
  );
  const checks = statuses.filter((check) => check.name !== current.name);
  requireValue(
    checks.every(
      (check) =>
        check.sha === env.CI_COMMIT_SHA &&
        check.pipeline_id === pipelineId &&
        /^[a-zA-Z0-9_.:-]{1,100}$/.test(check.name) &&
        typeof check.allow_failure === 'boolean' &&
        (check.allow_failure || check.status === 'success'),
    ),
    'Commit checks are stale, malformed or incomplete',
  );
  return {
    project_id: projectId,
    mr_iid: mrId,
    source_sha: mr.sha,
    target_sha: target.commit.id,
    diff_base_sha: mr.diff_refs.base_sha,
    pipeline_id: pipelineId,
    job_id: jobId,
    runner_id: runner.id,
    current_review_job: 'running (this review)',
    commit_checks: checks.map((check) => ({
      name: check.name,
      status: check.status,
      required: !check.allow_failure,
      sha: check.sha,
    })),
    other_required_checks: otherRequired.map((job) => ({
      id: job.id,
      status: 'success',
    })),
    conflicts: false,
    unresolved_blocking_discussions: false,
    pipeline_success_required_for_merge: true,
    discussions_resolved_required_for_merge: true,
  };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    if (process.argv.length !== 2)
      throw new Error('Evidence helper accepts stdin only');
    const config = JSON.parse(
      fs.readFileSync('/etc/open-work-hub/review-evidence.json', 'utf8'),
    );
    // Read a bounded identity request, never caller-selected code, paths or API routes.
    const chunks = [];
    let length = 0;
    for await (const chunk of process.stdin) {
      length += chunk.length;
      if (length > 16384) throw new Error('Evidence request too large');
      chunks.push(chunk);
    }
    const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    process.stdout.write(JSON.stringify(verifyEvidence(input, config)));
  } catch (error) {
    console.error(
      `[review-evidence] ${error instanceof SyntaxError ? 'Invalid evidence JSON' : error.message}`,
    );
    process.exitCode = 1;
  }
}
