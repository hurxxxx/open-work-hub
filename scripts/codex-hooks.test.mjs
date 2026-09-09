import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  handleEvent,
  patchViolation,
  workspaceSnapshot,
  selectChecks,
  runChecks,
} from './codex-hooks.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const git = (root, args) =>
  execFileSync('git', ['-C', root, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'owh-hooks-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  git(root, ['init', '-q']);
  fs.writeFileSync(path.join(root, '.gitignore'), '.runtime/\n.env\n');
  fs.writeFileSync(path.join(root, 'file.txt'), 'original\n');
  git(root, ['add', '.']);
  git(root, [
    '-c',
    'user.name=Test',
    '-c',
    'user.email=test@invalid',
    '-c',
    'commit.gpgsign=false',
    'commit',
    '-qm',
    'fixture',
  ]);
  return root;
}
const event = (root, name, extra = {}) => ({
  cwd: root,
  session_id: 'synthetic-session',
  hook_event_name: name,
  ...extra,
});

test('patch policy blocks Git metadata and generated contracts, permits source changes', (t) => {
  const root = fixture(t);
  for (const name of [
    '.git/config',
    'packages/contracts/api.generated.d.ts',
    'apps/api/contracts_generated.py',
  ]) {
    assert.ok(
      patchViolation(
        root,
        `*** Begin Patch\n*** Add File: ${name}\n+x\n*** End Patch`,
      ),
    );
  }
  assert.equal(
    patchViolation(
      root,
      '*** Begin Patch\n*** Update File: file.txt\n@@\n-original\n+changed\n*** End Patch',
    ),
    null,
  );
  assert.throws(() => patchViolation(root, {}));
});

test('patch uses session cwd and resolves existing symlink ancestors and rename destinations', (t) => {
  const root = fixture(t);
  fs.mkdirSync(path.join(root, 'nested'));
  fs.symlinkSync(path.join(root, '.git'), path.join(root, 'nested', 'alias'));
  assert.ok(
    patchViolation(
      root,
      '*** Begin Patch\n*** Update File: file.txt\n*** Move to: alias/config\n*** End Patch',
      path.join(root, 'nested'),
    ),
  );
  assert.ok(
    patchViolation(
      root,
      '*** Begin Patch\n*** Add File: ../.git/config\n+x\n*** End Patch',
      path.join(root, 'nested'),
    ),
  );
});

test('PreToolUse returns the documented deny schema; no guessed shell parsing', (t) => {
  const root = fixture(t);
  const output = handleEvent(
    event(root, 'PreToolUse', {
      tool_name: 'apply_patch',
      tool_input: {
        command: '*** Begin Patch\n*** Delete File: .git/config\n*** End Patch',
      },
    }),
  );
  assert.equal(output.hookSpecificOutput.permissionDecision, 'deny');
  assert.equal(output.hookSpecificOutput.hookEventName, 'PreToolUse');
  assert.deepEqual(
    handleEvent(
      event(root, 'PreToolUse', {
        tool_name: 'Bash',
        tool_input: { command: 'git status' },
      }),
    ),
    {},
  );
});

test('snapshot covers staged, unstaged, untracked, deleted, and symlink changes without env values', (t) => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, 'file.txt'), 'edited\n');
  git(root, ['add', 'file.txt']);
  fs.writeFileSync(path.join(root, 'new.txt'), 'new\n');
  fs.writeFileSync(
    path.join(root, '.env'),
    'SENSITIVE=synthetic-private-value\n',
  );
  fs.symlinkSync('/nonexistent-sensitive-target', path.join(root, 'link'));
  let snapshot = workspaceSnapshot(root);
  assert.deepEqual(Object.keys(snapshot), ['file.txt', 'link', 'new.txt']);
  assert.ok(!JSON.stringify(snapshot).includes('synthetic-private-value'));
  fs.unlinkSync(path.join(root, 'file.txt'));
  snapshot = workspaceSnapshot(root);
  assert.equal(snapshot['file.txt'], 'deleted');
});

test('startup/resume is idempotent and pre-existing dirty work is not attributed to the session', (t) => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, 'file.txt'), 'pre-existing\n');
  handleEvent(event(root, 'SessionStart'));
  let calls = 0;
  const dependencies = {
    run: () => {
      calls++;
    },
  };
  assert.deepEqual(handleEvent(event(root, 'Stop'), dependencies), {});
  assert.equal(calls, 0);
  fs.writeFileSync(path.join(root, 'new.txt'), 'new\n');
  handleEvent(event(root, 'SessionStart', { source: 'resume' }));
  handleEvent(event(root, 'Stop'), dependencies);
  assert.ok(calls > 0);
});

test('Stop blocks once for failure and never loops on stop_hook_active', (t) => {
  const root = fixture(t);
  handleEvent(event(root, 'SessionStart'));
  fs.writeFileSync(path.join(root, 'file.txt'), 'changed\n');
  const dependencies = {
    run: () => {
      throw Error('sensitive stderr must not propagate');
    },
  };
  assert.equal(
    handleEvent(event(root, 'Stop'), dependencies).decision,
    'block',
  );
  const second = handleEvent(
    event(root, 'Stop', { stop_hook_active: true }),
    dependencies,
  );
  assert.equal(second.decision, undefined);
  assert.ok(second.systemMessage);
  assert.ok(!JSON.stringify(second).includes('sensitive stderr'));
});

test('only successful checks cache; edited files invalidate cached results', (t) => {
  const root = fixture(t);
  handleEvent(event(root, 'SessionStart'));
  fs.writeFileSync(path.join(root, 'file.txt'), 'changed\n');
  let calls = 0;
  const dependencies = {
    run: () => {
      calls++;
    },
  };
  handleEvent(event(root, 'Stop'), dependencies);
  const first = calls;
  handleEvent(event(root, 'Stop'), dependencies);
  assert.equal(calls, first);
  fs.writeFileSync(path.join(root, 'file.txt'), 'another\n');
  handleEvent(event(root, 'Stop'), dependencies);
  assert.ok(calls > first);
});

test('failed checks retry and post feedback is deduplicated without hiding original tool output', (t) => {
  const root = fixture(t);
  handleEvent(event(root, 'SessionStart'));
  fs.writeFileSync(path.join(root, 'file.txt'), 'changed \n');
  const failed = {
    run: () => {
      throw Error('failure');
    },
  };
  const post = handleEvent(event(root, 'PostToolUse'), failed);
  assert.ok(post.hookSpecificOutput.additionalContext);
  assert.equal(post.decision, undefined);
  assert.deepEqual(handleEvent(event(root, 'PostToolUse'), failed), {});
  assert.equal(handleEvent(event(root, 'Stop'), failed).decision, 'block');
  assert.deepEqual(handleEvent(event(root, 'Stop'), { run: () => {} }), {});
});

test('missing baseline warns without attributing dirty work or blocking completion', (t) => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, 'file.txt'), 'changed\n');
  assert.ok(handleEvent(event(root, 'Stop')).systemMessage);
  assert.equal(handleEvent(event(root, 'Stop')).decision, undefined);
});

test('unsafe cache links fail closed and active Stop errors return a warning', (t) => {
  const root = fixture(t);
  fs.symlinkSync(os.tmpdir(), path.join(root, '.runtime'));
  assert.throws(() => handleEvent(event(root, 'SessionStart')), /unsafe cache/);
  const response = spawnSync(
    'node',
    [path.join(ROOT, 'scripts/codex-hooks.mjs')],
    {
      input: JSON.stringify(event(root, 'Stop', { stop_hook_active: true })),
      encoding: 'utf8',
    },
  );
  assert.equal(response.status, 0);
  assert.ok(JSON.parse(response.stdout).systemMessage);
  const invalid = spawnSync(
    'node',
    [path.join(ROOT, 'scripts/codex-hooks.mjs')],
    { input: 'not JSON', encoding: 'utf8' },
  );
  assert.equal(invalid.status, 2);
  assert.ok(!invalid.stderr.includes('not JSON'));
});

test('routing is focused; unavailable checks and timeouts remain visible', () => {
  assert.deepEqual(
    selectChecks(['docs/README.md']).map((c) => c.id),
    ['diff'],
  );
  assert.deepEqual(
    selectChecks(['.codex/hooks.json']).map((c) => c.id),
    ['diff', 'skills', 'hooks'],
  );
  assert.ok(
    selectChecks(['apps/web/src/locales/ko.json']).some((c) => c.id === 'i18n'),
  );
  assert.ok(selectChecks(['.env.example']).some((c) => c.id === 'env'));
  const commands = [{ id: 'probe', args: ['unavailable'] }];
  assert.equal(
    runChecks(ROOT, commands, () => {
      throw Object.assign(Error(), { code: 'ENOENT' });
    })[0].status,
    'unavailable',
  );
  assert.equal(
    runChecks(ROOT, commands, () => {
      throw Object.assign(Error(), { code: 'ETIMEDOUT' });
    })[0].status,
    'timeout',
  );
});

test('native execpolicy rules allow PR operations and retain unrelated mutation denials', (t) => {
  if (spawnSync('codex', ['--version']).status !== 0) {
    t.skip(
      'Codex CLI unavailable; native integration must run on a Codex host',
    );
    return;
  }
  for (const [argv, denied, expectedDecision] of [
    [['gh', 'pr', 'create'], false, 'allow'],
    [['gh', 'pr', 'edit', '1'], false, 'allow'],
    [['gh', 'pr', 'merge', '1'], false, 'allow'],
    [['gh', 'pr', 'review', '1'], false, 'allow'],
    [['gh', 'pr', 'comment', '1'], false, 'allow'],
    [['gh', 'pr', 'close', '1'], false, 'allow'],
    [['gh', 'pr', 'reopen', '1'], false, 'allow'],
    [['gh', 'pr', 'view', '1'], false],
    [['gh', 'issue', 'edit', '1'], true],
    [['gh', 'issue', 'view', '1'], false],
    [['git', 'push', 'upstream', 'dev'], true],
    [['git', 'push', 'upstream', 'HEAD:main'], true],
    [['git', 'fetch', 'upstream'], false],
    [['git', 'push', 'origin', 'dev'], false],
    [
      [
        'docker',
        'compose',
        '-f',
        'ops/compose/open-work-hub-prod.app.yml',
        'up',
      ],
      true,
    ],
    [
      [
        'docker',
        'compose',
        '-f',
        'ops/compose/open-work-hub-prod.app.yml',
        'config',
      ],
      false,
    ],
  ]) {
    const output = JSON.parse(
      execFileSync(
        'codex',
        [
          'execpolicy',
          'check',
          '--rules',
          path.join(ROOT, '.codex/rules/project.rules'),
          '--',
          ...argv,
        ],
        { encoding: 'utf8' },
      ),
    );
    assert.equal(output.decision === 'forbidden', denied, argv.join(' '));
    if (expectedDecision) {
      assert.equal(output.decision, expectedDecision, argv.join(' '));
    }
  }
});

test('checked-in hook config uses native synchronous events, bounded timeouts, and no trust bypass', () => {
  const config = JSON.parse(
    fs.readFileSync(path.join(ROOT, '.codex/hooks.json'), 'utf8'),
  );
  assert.deepEqual(Object.keys(config.hooks).sort(), [
    'PostToolUse',
    'PreToolUse',
    'SessionStart',
    'Stop',
  ]);
  for (const groups of Object.values(config.hooks))
    for (const group of groups)
      for (const hook of group.hooks) {
        assert.equal(hook.type, 'command');
        assert.ok(hook.timeout > 0 && hook.timeout <= 60);
        assert.ok(!hook.async);
        assert.ok(hook.command.includes('scripts/codex-hooks.mjs'));
        assert.ok(!hook.command.includes('bypass'));
      }
});
