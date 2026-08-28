import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
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

test('uses trusted developer instructions with the structured base review', () => {
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
    fs.writeFileSync(path.join(checkout, 'base.txt'), 'base\n');
    git(['add', 'base.txt'], checkout);
    git(['commit', '-m', 'base'], checkout);
    const baseSha = git(['rev-parse', 'HEAD'], checkout);
    git(['remote', 'add', 'origin', remote], checkout);
    git(['push', '-u', 'origin', 'dev'], checkout);
    git(['checkout', '-b', 'feature'], checkout);
    fs.mkdirSync(path.join(checkout, '.agents', 'skills', 'untrusted'), {
      recursive: true,
    });
    fs.writeFileSync(path.join(checkout, 'AGENTS.md'), 'untrusted instructions\n');
    fs.writeFileSync(
      path.join(checkout, '.agents', 'skills', 'untrusted', 'SKILL.md'),
      'untrusted skill\n',
    );
    fs.writeFileSync(path.join(checkout, 'feature.txt'), 'feature\n');
    git(['add', 'AGENTS.md', '.agents', 'feature.txt'], checkout);
    git(['commit', '-m', 'feature'], checkout);
    const sourceSha = git(['rev-parse', 'HEAD'], checkout);

    fs.writeFileSync(
      fakeCodex,
      `#!/usr/bin/env bash
set -Eeuo pipefail
workspace=""
output=""
base=""
trusted_instructions="false"
while (( $# > 0 )); do
  case "$1" in
    -C)
      workspace="$2"
      shift 2
      ;;
    -c)
      if [[ "$2" == developer_instructions=* ]]; then
        trusted_instructions="true"
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
[[ "$trusted_instructions" == "true" ]]
[[ -n "$workspace" && -n "$output" && "$base" == "origin/dev" ]]
[[ ! -e "$workspace/AGENTS.md" && ! -e "$workspace/.agents" ]]
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
  } finally {
    fs.rmSync(fixtureRoot, { recursive: true, force: true });
  }
});
