import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
import {
  queryGitLab,
  verifyEvidence,
  verifyBranchProtection,
  matchesBranch,
} from './codex-review-evidence.mjs';

const runnerSourcePath = path.join(repoRoot, 'scripts/codex-review-ci.sh');
const runnerSource = fs.readFileSync(runnerSourcePath, 'utf8');
const invocationStart = runnerSource.indexOf('  env -i \\');
const invocationEnd = runnerSource.indexOf('\n    fail ', invocationStart);
const codexInvocation = runnerSource.slice(invocationStart, invocationEnd);

test('passes approval policy as a Codex global option before exec', () => {
  assert.match(
    runnerSource,
    /"\$codex_bin" \\\n\s+-a never \\\n\s+-C "\$review_workspace" \\\n\s+exec \\/,
  );
  assert.doesNotMatch(
    runnerSource,
    /"\$codex_bin" exec \\\n[\s\S]{0,400}\s+-a never \\/,
  );
});

test('uses target-owned developer instructions with the structured base review', () => {
  assert.ok(invocationStart >= 0);
  assert.ok(invocationEnd > invocationStart);
  assert.match(
    codexInvocation,
    /-c "developer_instructions=\$\{trusted_instructions\}"/,
  );
  assert.match(codexInvocation, /\s+review \\/);
  assert.match(
    codexInvocation,
    /--base "origin\/\$\{CI_MERGE_REQUEST_TARGET_BRANCH_NAME\}"/,
  );
  assert.doesNotMatch(codexInvocation, /\s+- < <\(write_prompt\)/);
  assert.match(runnerSource, /select_target_instruction_paths/);
  assert.match(
    runnerSource,
    /git show "\$\{target_sha\}:\$\{instruction_path\}"/,
  );
});

test('reviews in a credential-free checkout without source instructions', () => {
  assert.match(
    runnerSource,
    /git clone --quiet --local --no-hardlinks --no-checkout/,
  );
  assert.match(runnerSource, /remote remove origin/);
  assert.match(runnerSource, /config core\.symlinks false/);
  assert.match(runnerSource, /'!\/\*\*\/AGENTS\.md'/);
  assert.match(runnerSource, /'!\/\*\*\/\.agents\/'/);
  assert.match(
    runnerSource,
    /update-ref \\\n\s+"refs\/remotes\/origin\/\$\{CI_MERGE_REQUEST_TARGET_BRANCH_NAME\}"/,
  );
  assert.match(runnerSource, /review clone must not retain remotes/);
});

test('keeps source instructions out of the review checkout but in its diff', () => {
  const fixtureRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), 'open-work-hub-codex-review-test.'),
  );
  const remote = path.join(fixtureRoot, 'remote.git');
  const checkout = path.join(fixtureRoot, 'checkout');
  const fakeCodex = path.join(fixtureRoot, 'fake-codex');
  const codexHome = path.join(fixtureRoot, 'codex-home');
  const mockBin = path.join(fixtureRoot, 'bin');
  const evidenceFile = path.join(fixtureRoot, 'evidence.json');
  const git = (args, cwd = fixtureRoot) =>
    execFileSync('git', args, {
      cwd,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();

  try {
    fs.mkdirSync(checkout);
    fs.mkdirSync(codexHome);
    git(['init', '--bare', remote]);
    git(['init', '--initial-branch=dev'], checkout);
    git(['config', 'user.name', 'Codex Review Test'], checkout);
    git(['config', 'user.email', 'codex-review@example.invalid'], checkout);
    fs.mkdirSync(path.join(checkout, 'apps', 'api'), { recursive: true });
    fs.writeFileSync(
      path.join(checkout, 'AGENTS.md'),
      'trusted target root instructions\n',
    );
    fs.writeFileSync(
      path.join(checkout, 'apps', 'api', 'AGENTS.md'),
      'trusted target API instructions\n',
    );
    fs.writeFileSync(path.join(checkout, 'base.txt'), 'base\n');
    git(['add', 'AGENTS.md', 'apps/api/AGENTS.md', 'base.txt'], checkout);
    git(['commit', '-m', 'base'], checkout);
    const baseSha = git(['rev-parse', 'HEAD'], checkout);
    git(['remote', 'add', 'origin', remote], checkout);
    git(['push', '-u', 'origin', 'dev'], checkout);
    git(['checkout', '-b', 'feature'], checkout);
    fs.mkdirSync(path.join(checkout, '.agents', 'skills', 'untrusted'), {
      recursive: true,
    });
    fs.writeFileSync(
      path.join(checkout, 'AGENTS.md'),
      'untrusted source root instructions\n',
    );
    fs.writeFileSync(
      path.join(checkout, 'apps', 'api', 'AGENTS.md'),
      'untrusted source API instructions\n',
    );
    fs.writeFileSync(
      path.join(checkout, 'apps', 'api', 'feature.py'),
      'FEATURE = True\n',
    );
    fs.writeFileSync(
      path.join(checkout, '.agents', 'skills', 'untrusted', 'SKILL.md'),
      'untrusted skill\n',
    );
    fs.writeFileSync(path.join(checkout, 'feature.txt'), 'feature\n');
    fs.mkdirSync(path.join(checkout, '.codex'), { recursive: true });
    fs.writeFileSync(
      path.join(checkout, '.codex', 'hooks.json'),
      JSON.stringify({
        hooks: {
          SessionStart: [
            { hooks: [{ type: 'command', command: 'untrusted-source-hook' }] },
          ],
        },
      }),
    );
    git(
      ['add', 'AGENTS.md', 'apps/api', '.agents', '.codex', 'feature.txt'],
      checkout,
    );
    git(['commit', '-m', 'feature'], checkout);
    const sourceSha = git(['rev-parse', 'HEAD'], checkout);
    fs.mkdirSync(mockBin);
    const evidence = {
      'projects/1': {
        id: 1,
        only_allow_merge_if_pipeline_succeeds: true,
        only_allow_merge_if_all_discussions_are_resolved: true,
      },
      'projects/1/merge_requests/1': {
        state: 'opened',
        source_project_id: 1,
        target_project_id: 1,
        source_branch: 'feature',
        target_branch: 'dev',
        sha: sourceSha,
        diff_refs: { base_sha: baseSha },
        head_pipeline: { id: 2 },
        has_conflicts: false,
        blocking_discussions_resolved: true,
        description: 'UNTRUSTED_MR_CONTENT_MUST_NOT_REACH_CODEX',
      },
      'projects/1/repository/branches/dev': {
        commit: { id: baseSha },
        protected: true,
      },
      'projects/1/protected_branches?per_page=100&page=1': [
        {
          name: 'dev',
          allow_force_push: false,
          push_access_levels: [{ access_level: 0 }],
        },
      ],
      'projects/1/pipelines/2': {
        sha: sourceSha,
        source: 'merge_request_event',
        status: 'running',
      },
      'projects/1/pipelines/2/jobs?include_retried=false&per_page=100': [
        {
          id: 3,
          name: 'codex_review',
          stage: 'review',
          status: 'running',
          allow_failure: false,
          commit: { id: sourceSha },
          runner: { id: 4 },
        },
      ],
      [`projects/1/repository/commits/${sourceSha}/statuses?pipeline_id=2&all=false&per_page=100`]:
        [
          {
            name: 'pnpm-ci-harness',
            sha: sourceSha,
            pipeline_id: 2,
            allow_failure: false,
            status: 'success',
          },
        ],
      'runners/4': {
        id: 4,
        tag_list: ['codex-local'],
        run_untagged: false,
        locked: true,
        runner_type: 'project_type',
        projects: [{ id: 1 }],
      },
    };
    fs.writeFileSync(evidenceFile, JSON.stringify(evidence));
    fs.writeFileSync(
      path.join(mockBin, 'sudo'),
      `#!/usr/bin/env node
const fs = require('node:fs');
const assert = require('node:assert/strict');
assert.deepEqual(process.argv.slice(2), ['-n', '-H', '-u', 'owh-review-evidence', '/usr/local/libexec/open-work-hub-review-evidence']);
(async () => {
  const { verifyEvidence } = await import(${JSON.stringify(path.join(repoRoot, 'scripts/codex-review-evidence.mjs'))});
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  assert.equal(input.CI_JOB_TOKEN, undefined);
  const query = (host, route) => {
    assert.equal(host.host, 'gitlab.example.invalid:8443');
    const evidence = JSON.parse(fs.readFileSync(${JSON.stringify(evidenceFile)}, 'utf8'));
    if (!Object.hasOwn(evidence, route)) throw new Error('Unexpected route');
    if (evidence.__change_after_snapshot && route === 'projects/1/merge_requests/1') {
      const counter = ${JSON.stringify(`${evidenceFile}.calls`)};
      if (fs.existsSync(counter)) evidence[route].sha = '0'.repeat(40);
      fs.writeFileSync(counter, 'called');
    }
    if (evidence.__change_protection_after_snapshot && route === 'projects/1/protected_branches?per_page=100&page=1') {
      const counter = ${JSON.stringify(`${evidenceFile}.protection-calls`)};
      if (fs.existsSync(counter)) evidence[route].push({name: '*', allow_force_push: true, push_access_levels: [{access_level: 40}]});
      fs.writeFileSync(counter, 'called');
    }
    return evidence[route];
  };
  process.stdout.write(JSON.stringify(verifyEvidence(input, {
    api_url: 'https://gitlab.example.invalid:8443/api/v4', project_id: 1,
  }, query)));
})().catch(() => { process.exitCode = 1; });
`,
      { mode: 0o755 },
    );

    fs.writeFileSync(
      fakeCodex,
      `#!/usr/bin/env bash
set -Eeuo pipefail
workspace=""
output=""
base=""
trusted_instructions=""
while (( $# > 0 )); do
  case "$1" in
    -C)
      workspace="$2"
      shift 2
      ;;
    -c)
      if [[ "$2" == developer_instructions=* ]]; then
        trusted_instructions="\${2#developer_instructions=}"
      fi
      shift 2
      ;;
    --output-last-message)
      output="$2"
      shift 2
      ;;
    --base)
      base="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
[[ -n "$trusted_instructions" ]]
node -e '
const value = JSON.parse(process.argv[1]);
if (!value.includes("trusted target root instructions")) process.exit(1);
if (!value.includes("trusted target API instructions")) process.exit(1);
if (value.includes("untrusted source root instructions")) process.exit(1);
if (value.includes("untrusted source API instructions")) process.exit(1);
if (value.includes("UNTRUSTED_MR_CONTENT_MUST_NOT_REACH_CODEX")) process.exit(1);
if (!value.includes("pipeline_success_required_for_merge")) process.exit(1);
if (!value.includes("Authenticated runner verification")) process.exit(1);
if (!value.includes("pnpm-ci-harness")) process.exit(1);
' "$trusted_instructions"
[[ -z "\${CI_JOB_TOKEN:-}" && -z "\${MOCK_GITLAB_EVIDENCE:-}" ]]
[[ -n "$workspace" && -n "$output" && "$base" == "origin/dev" ]]
[[ ! -e "$workspace/AGENTS.md" && ! -e "$workspace/apps/api/AGENTS.md" && ! -e "$workspace/.agents" && ! -e "$workspace/.codex" ]]
[[ -z "$(git -C "$workspace" remote)" ]]
git -C "$workspace" rev-parse --verify "$base" >/dev/null
git -C "$workspace" diff --name-only "$base"...HEAD | grep -Fxq AGENTS.md
printf '%s\n' \\
  '## 운영 배포 전 필수 수정' \\
  '운영 배포 차단 사항 없음.' \\
  '## 통합 적합성 검토' \\
  '- 검토 영역: fixture' \\
  '- 프로젝트 계약: fixture' \\
  '- 결과 및 근거: fixture' \\
  '## 병합 가능 여부' \\
  'MERGE_READY' \\
  '## 후속 이슈 후보' \\
  '없음.' \\
  '## 검증 및 잔여 위험' \\
  'fixture' \\
  '## 확인한 명령' \\
  'fixture' >"$output"
`,
      { mode: 0o755 },
    );

    const result = spawnSync(runnerSourcePath, {
      cwd: checkout,
      encoding: 'utf8',
      env: {
        ...process.env,
        PATH: `${mockBin}${path.delimiter}${process.env.PATH}`,
        MOCK_GITLAB_EVIDENCE: evidenceFile,
        CI_API_V4_URL: 'https://gitlab.example.invalid:8443/api/v4',
        CI_PIPELINE_ID: '2',
        CI_JOB_ID: '3',
        CI_RUNNER_ID: '4',
        CI_MERGE_REQUEST_IID: '1',
        CI_JOB_TOKEN: 'fixture-secret-not-for-codex',
        CODEX_BIN: fakeCodex,
        CODEX_HOME: codexHome,
        CI_COMMIT_SHA: sourceSha,
        CI_JOB_NAME: 'codex_review',
        CI_JOB_STAGE: 'review',
        CI_MERGE_REQUEST_DIFF_BASE_SHA: baseSha,
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature',
        CI_MERGE_REQUEST_SOURCE_PROJECT_ID: '1',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_PROJECT_ID: '1',
      },
    });

    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /MERGE_READY/);
    assert.match(
      fs.readFileSync(path.join(checkout, 'codex-review.md'), 'utf8'),
      /MERGE_READY/,
    );
    const policyContext = fs.readFileSync(
      path.join(checkout, 'codex-review-policy-context.md'),
      'utf8',
    );
    assert.match(policyContext, new RegExp(`target_sha=${baseSha}`));
    assert.match(policyContext, /policy_path=AGENTS\.md blob=/);
    assert.match(policyContext, /policy_path=apps\/api\/AGENTS\.md blob=/);

    const failedCases = [
      [
        'failed external check',
        (v) => {
          v[
            `projects/1/repository/commits/${sourceSha}/statuses?pipeline_id=2&all=false&per_page=100`
          ][0].status = 'failed';
        },
      ],
      [
        'stale external check',
        (v) => {
          v[
            `projects/1/repository/commits/${sourceSha}/statuses?pipeline_id=2&all=false&per_page=100`
          ][0].pipeline_id = 99;
        },
      ],
      [
        'stale source',
        (v) => {
          v['projects/1/merge_requests/1'].sha = baseSha;
        },
      ],
      [
        'unresolved discussion',
        (v) => {
          v['projects/1/merge_requests/1'].blocking_discussions_resolved =
            false;
        },
      ],
      [
        'disabled pipeline gate',
        (v) => {
          v['projects/1'].only_allow_merge_if_pipeline_succeeds = false;
        },
      ],
      [
        'wrong runner',
        (v) => {
          v['runners/4'].tag_list = ['untrusted'];
        },
      ],
      [
        'shared runner',
        (v) => {
          v['runners/4'].projects.push({ id: 2 });
        },
      ],
      [
        'direct pushes enabled',
        (v) => {
          v[
            'projects/1/protected_branches?per_page=100&page=1'
          ][0].push_access_levels = [{ access_level: 40 }];
        },
      ],
      [
        'other required check failed',
        (v) => {
          v[
            'projects/1/pipelines/2/jobs?include_retried=false&per_page=100'
          ].push({ id: 9, allow_failure: false, status: 'failed' });
        },
      ],
      [
        'newer pipeline',
        (v) => {
          v['projects/1/merge_requests/1'].head_pipeline.id = 99;
        },
      ],
      [
        'protection changed during review',
        (v) => {
          v.__change_protection_after_snapshot = true;
        },
        /post-review verification failed/,
      ],
      [
        'changed during review',
        (v) => {
          v.__change_after_snapshot = true;
        },
        /post-review verification failed/,
      ],
    ];
    for (const [
      name,
      mutate,
      expected = /pre-review verification failed/,
    ] of failedCases) {
      const changed = structuredClone(evidence);
      mutate(changed);
      fs.writeFileSync(evidenceFile, JSON.stringify(changed));
      const failed = spawnSync(runnerSourcePath, {
        cwd: checkout,
        encoding: 'utf8',
        env: {
          ...process.env,
          PATH: `${mockBin}${path.delimiter}${process.env.PATH}`,
          MOCK_GITLAB_EVIDENCE: evidenceFile,
          CODEX_BIN: fakeCodex,
          CODEX_HOME: codexHome,
          CI_API_V4_URL: 'https://gitlab.example.invalid:8443/api/v4',
          CI_PROJECT_ID: '1',
          CI_PIPELINE_ID: '2',
          CI_JOB_ID: '3',
          CI_RUNNER_ID: '4',
          CI_MERGE_REQUEST_IID: '1',
          CI_COMMIT_SHA: sourceSha,
          CI_JOB_NAME: 'codex_review',
          CI_JOB_STAGE: 'review',
          CI_MERGE_REQUEST_DIFF_BASE_SHA: baseSha,
          CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature',
          CI_MERGE_REQUEST_SOURCE_PROJECT_ID: '1',
          CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
          CI_PIPELINE_SOURCE: 'merge_request_event',
        },
      });
      assert.notEqual(failed.status, 0, name);
      assert.match(failed.stderr, expected, name);
    }
  } finally {
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});

test('preserves the configured HTTPS port and excludes caller credentials', () => {
  const value = queryGitLab(
    new URL('https://gitlab.example.invalid:8443/api/v4'),
    'projects/1',
    (file, args, options) => {
      assert.equal(file, '/usr/local/bin/glab');
      assert.deepEqual(args, [
        'api',
        '--hostname',
        'gitlab.example.invalid',
        'https://gitlab.example.invalid:8443/api/v4/projects/1',
      ]);
      assert.deepEqual(Object.keys(options.env).sort(), [
        'HOME',
        'LANG',
        'PATH',
      ]);
      return '{"id":1}';
    },
    '/usr/local/bin/glab',
  );
  assert.deepEqual(value, { id: 1 });
});

test('rejects untrusted API servers and projects before accessing credentials', () => {
  const config = {
    api_url: 'https://gitlab.example.invalid:8443/api/v4',
    project_id: 1,
  };
  const query = () => {
    assert.fail('must not call GitLab');
  };
  assert.throws(
    () =>
      verifyEvidence(
        {
          CI_API_V4_URL: 'https://attacker.invalid/api/v4',
          CI_PROJECT_ID: '1',
        },
        config,
        query,
      ),
    /trusted HTTPS/,
  );
  assert.throws(
    () =>
      verifyEvidence(
        { CI_API_V4_URL: config.api_url, CI_PROJECT_ID: '2' },
        config,
        query,
      ),
    /Unexpected evidence project/,
  );
});

test('checks every matching rule, including inherited and wildcard-only rules', () => {
  const strict = {
    name: 'dev',
    allow_force_push: false,
    push_access_levels: [{ access_level: 0 }],
  };
  const verify = (rules) =>
    verifyBranchProtection(() => rules, 'projects/1', 'dev');
  for (const name of ['*', 'd*', '*ev', 'd*v']) {
    verify([{ ...strict, name, inherited: true }]);
    assert.throws(
      () =>
        verify([
          strict,
          { ...strict, name, inherited: true, allow_force_push: true },
        ]),
      /permits/,
    );
    assert.throws(
      () =>
        verify([
          strict,
          { ...strict, name, push_access_levels: [{ access_level: 40 }] },
        ]),
      /permits/,
    );
  }
  for (const field of [
    'user_id',
    'group_id',
    'deploy_key_id',
    'member_role_id',
  ]) {
    assert.throws(
      () =>
        verify([
          { ...strict, push_access_levels: [{ access_level: 0, [field]: 5 }] },
        ]),
      /permits/,
    );
  }
  verify([
    strict,
    {
      name: 'main',
      allow_force_push: true,
      push_access_levels: [{ access_level: 40 }],
    },
  ]);
  assert.throws(() => verify([]), /No matching/);
  assert.throws(
    () => verify([{ ...strict, allow_force_push: undefined }]),
    /permits/,
  );
  assert.throws(
    () => verify([{ ...strict, push_access_levels: [] }]),
    /permits/,
  );
  assert.throws(() => verify([null]), /Invalid/);
});

test('uses GitLab literal and case-sensitive star matching', () => {
  for (const [pattern, branch, expected] of [
    ['*', 'dev', true],
    ['d**v', 'dev', true],
    ['dev*', 'dev', true],
    ['DEV', 'dev', false],
    ['d.v', 'dev', false],
    ['d?v', 'dev', false],
    ['release/*', 'release/1/x', true],
    ['release/1.0', 'release/1x0', false],
    ['dev', 'develop', false],
    ['*ev', 'dev', true],
    ['*ev', 'deva', false],
  ])
    assert.equal(
      matchesBranch(pattern, branch),
      expected,
      `${pattern}: ${branch}`,
    );
});

test('reads later protection pages and fails closed on missing or unbounded evidence', () => {
  const first = Array.from({ length: 100 }, (_, i) => ({
    name: `unrelated-${i}`,
  }));
  const strict = {
    name: 'dev',
    allow_force_push: false,
    push_access_levels: [{ access_level: 0 }],
  };
  const routes = [];
  verifyBranchProtection(
    (route) => {
      routes.push(route);
      return route.endsWith('page=1') ? first : [strict];
    },
    'projects/1',
    'dev',
  );
  assert.deepEqual(routes, [
    'projects/1/protected_branches?per_page=100&page=1',
    'projects/1/protected_branches?per_page=100&page=2',
  ]);
  assert.throws(
    () =>
      verifyBranchProtection(
        (route) =>
          route.endsWith('page=1')
            ? [strict, ...first.slice(1)]
            : [{ ...strict, name: '*', allow_force_push: true }],
        'projects/1',
        'dev',
      ),
    /permits/,
  );
  assert.throws(
    () =>
      verifyBranchProtection(
        (route) => {
          if (route.endsWith('page=1')) return first;
          throw new Error('page unavailable');
        },
        'projects/1',
        'dev',
      ),
    /unavailable/,
  );
  assert.throws(
    () => verifyBranchProtection(() => first, 'projects/1', 'dev'),
    /limit/,
  );
  assert.throws(
    () => verifyBranchProtection(() => ({}), 'projects/1', 'dev'),
    /Invalid/,
  );
});

test('installer embeds the resolved glab path and rejects unsafe executable paths', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'owh-evidence-install.'));
  try {
    const bin = path.join(root, 'bin');
    const custom = path.join(root, 'custom tools');
    fs.mkdirSync(bin);
    fs.mkdirSync(custom);
    const glab = path.join(custom, 'glab-$&-real');
    fs.writeFileSync(glab, `#!/bin/sh\nprintf '{"id":1}\\n'\n`, {
      mode: 0o755,
    });
    fs.symlinkSync(glab, path.join(bin, 'glab'));
    fs.symlinkSync(process.execPath, path.join(bin, 'node'));
    for (const name of ['id', 'codex'])
      fs.writeFileSync(path.join(bin, name), '#!/bin/sh\nexit 0\n', {
        mode: 0o755,
      });
    fs.writeFileSync(
      path.join(bin, 'stat'),
      `#!/bin/sh
if [ "$2" = '%u' ]; then
  if [ "$3" = "$BAD_OWNER_PATH" ]; then echo 1000; else echo 0; fi
elif [ "$3" = "$BAD_MODE_PATH" ]; then echo 777; else echo 755; fi
`,
      { mode: 0o755 },
    );
    fs.writeFileSync(
      path.join(bin, 'sudo'),
      `#!/bin/bash
set -eu
[[ "$1" == install ]]
if [[ "\${@: -1}" == /usr/local/libexec/open-work-hub-review-evidence ]]; then
  cp "\${@: -2:1}" "$INSTALL_FIXTURE_OUTPUT"
fi
`,
      { mode: 0o755 },
    );
    const output = path.join(root, 'installed.mjs');
    const env = {
      ...process.env,
      PATH: `${bin}:${process.env.PATH}`,
      INSTALL_FIXTURE_OUTPUT: output,
    };
    const install = (extra) =>
      spawnSync(
        'bash',
        [
          path.join(
            repoRoot,
            'scripts/install-codex-review-runner-entrypoint.sh',
          ),
        ],
        { env: { ...env, ...extra }, encoding: 'utf8' },
      );
    const result = install({});
    assert.equal(result.status, 0, result.stderr);
    const probe = execFileSync(process.execPath, ['--input-type=module', '-'], {
      input: `import {queryGitLab} from ${JSON.stringify(output)};
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const result = queryGitLab(new URL('https://gitlab.invalid:8443/api/v4'), 'projects/1', (file,args,options) => {
  assert.equal(file, ${JSON.stringify(glab)});
  return execFileSync(file,args,options);
});
assert.deepEqual(result,{id:1});`,
      encoding: 'utf8',
    });
    assert.equal(probe, '');
    for (const extra of [
      { BAD_OWNER_PATH: glab },
      { BAD_MODE_PATH: glab },
      { BAD_MODE_PATH: custom },
    ]) {
      fs.unlinkSync(output);
      const failed = install(extra);
      assert.notEqual(failed.status, 0);
      assert.match(failed.stderr, /root-owned/);
      assert.equal(fs.existsSync(output), false);
      // Restore the successful fixture for the next rejection case.
      fs.writeFileSync(output, '');
    }
    assert.throws(
      () => queryGitLab(new URL('https://gitlab.invalid/api/v4'), 'projects/1'),
      /Install the evidence helper/,
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
