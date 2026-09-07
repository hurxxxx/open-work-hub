import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { CASES, collectEvent, prepareFixture } from './agent-guidance-eval.mjs';
import { spawnSync } from 'node:child_process';

test('six distinct service-free cases include a multi-turn authorization boundary', () => {
  assert.equal(CASES.length, 6);
  assert.equal(new Set(CASES.map((c) => c.id)).size, 6);
  assert.equal(CASES.filter((c) => c.followup).length, 1);
  for (const item of CASES) assert.equal(typeof item.grade, 'function');
});

test('fixture starts on dev with no remotes, synthetic env ignored, and immutable test baseline', (t) => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'owh-eval-test-'));
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }));
  const root = prepareFixture(
    parent,
    CASES.find((c) => c.id === 'env-preservation'),
    [{ name: 'AGENTS.md', content: 'Synthetic rules\n' }],
  );
  assert.ok(fs.existsSync(path.join(root, '.git')));
  assert.ok(
    !fs
      .readFileSync(path.join(root, '.git/config'), 'utf8')
      .includes('[remote'),
  );
  assert.equal(
    fs.readFileSync(path.join(root, '.gitignore'), 'utf8'),
    '.env\n.runtime/\n',
  );
  for (const tool of ['glab', 'gh', 'docker', 'curl', 'wget', 'ssh']) {
    const result = spawnSync(
      path.join(root, '.runtime/bin', tool),
      ['ignored-argument'],
      { encoding: 'utf8' },
    );
    assert.equal(result.status, 69);
    assert.ok(!result.stderr.includes('ignored-argument'));
  }
});

test('metrics collect usage, observed reads, boundary attempts, and model errors without storing tool text', () => {
  const result = {
    usage: { input_tokens: 0, cached_input_tokens: 0, output_tokens: 0 },
    skills: new Set(),
    toolCalls: 0,
  };
  collectEvent(result, {
    type: 'turn.completed',
    usage: { input_tokens: 100, cached_input_tokens: 50, output_tokens: 10 },
  });
  collectEvent(result, {
    type: 'item.completed',
    item: {
      type: 'command_execution',
      command: 'sed -n 1,80p .agents/skills/owh-mr-review/SKILL.md',
    },
  });
  collectEvent(result, {
    type: 'item.completed',
    item: { type: 'command_execution', command: 'glab mr merge 5' },
  });
  collectEvent(result, {
    type: 'turn.failed',
    error: { message: 'private error' },
  });
  assert.deepEqual(result.usage, {
    input_tokens: 100,
    cached_input_tokens: 50,
    output_tokens: 10,
  });
  assert.ok(result.skills.has('owh-mr-review'));
  assert.ok(result.externalAttempt);
  assert.ok(result.modelError);
  assert.ok(!JSON.stringify(result).includes('private error'));
});

test('artifact graders reject missing implementation and malformed drafts', (t) => {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'owh-eval-grader-'));
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }));
  for (const id of [
    'localized-copy',
    'diagnosis-then-fix',
    'existing-app-ai',
    'issue-draft',
  ]) {
    const definition = CASES.find((c) => c.id === id);
    const root = prepareFixture(parent, definition, []);
    assert.equal(definition.grade(root, {}), false, id);
  }
  assert.equal(
    CASES.find((c) => c.id === 'mr-review-only').grade(parent, {
      final: 'MERGE_READY',
    }),
    false,
  );
});
