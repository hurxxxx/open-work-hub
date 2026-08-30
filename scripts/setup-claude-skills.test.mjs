import assert from 'node:assert/strict';
import {
  lstat,
  mkdir,
  mkdtemp,
  realpath,
  rm,
  symlink,
  writeFile,
} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { ensureClaudeSkillsBridge } from './setup-claude-skills.mjs';

async function fixture(t) {
  const repoRoot = await mkdtemp(
    path.join(os.tmpdir(), 'open-work-hub-claude-skills-'),
  );
  t.after(async () => {
    await rm(repoRoot, { recursive: true, force: true });
  });
  await mkdir(path.join(repoRoot, '.agents', 'skills'), { recursive: true });
  return repoRoot;
}

test('creates and preserves the POSIX skills bridge', async (t) => {
  const repoRoot = await fixture(t);

  const created = await ensureClaudeSkillsBridge({ repoRoot, platform: 'linux' });
  const preserved = await ensureClaudeSkillsBridge({ repoRoot, platform: 'linux' });

  assert.equal(created.changed, true);
  assert.equal(preserved.changed, false);
  assert.equal((await lstat(created.bridge)).isSymbolicLink(), true);
  assert.equal(await realpath(created.bridge), await realpath(created.canonical));
});

test('replaces only the exact Git symlink placeholder', async (t) => {
  const repoRoot = await fixture(t);
  const bridge = path.join(repoRoot, '.claude', 'skills');
  await mkdir(path.dirname(bridge), { recursive: true });
  await writeFile(bridge, '../.agents/skills\n', 'utf8');

  const result = await ensureClaudeSkillsBridge({ repoRoot, platform: 'win32' });

  assert.equal(result.changed, true);
  assert.equal((await lstat(bridge)).isSymbolicLink(), true);
  assert.equal(await realpath(bridge), await realpath(result.canonical));
});

test('refuses to replace a real directory or different link', async (t) => {
  const directoryRoot = await fixture(t);
  await mkdir(path.join(directoryRoot, '.claude', 'skills'), { recursive: true });

  await assert.rejects(
    ensureClaudeSkillsBridge({ repoRoot: directoryRoot }),
    /refusing to replace an existing Claude skills path/,
  );

  const linkRoot = await fixture(t);
  const other = path.join(linkRoot, 'other-skills');
  const bridge = path.join(linkRoot, '.claude', 'skills');
  await mkdir(other, { recursive: true });
  await mkdir(path.dirname(bridge), { recursive: true });
  await symlink(other, bridge, 'dir');

  await assert.rejects(
    ensureClaudeSkillsBridge({ repoRoot: linkRoot }),
    /refusing to replace a different Claude skills link/,
  );
});
