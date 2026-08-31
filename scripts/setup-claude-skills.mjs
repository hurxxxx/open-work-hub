import {
  lstat,
  mkdir,
  readFile,
  realpath,
  symlink,
  unlink,
} from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const POSIX_BRIDGE_TARGET = '../.agents/skills';

async function pathState(target) {
  try {
    return await lstat(target);
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw error;
  }
}

export async function ensureClaudeSkillsBridge({
  repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url))),
  platform = process.platform,
} = {}) {
  const canonical = path.join(repoRoot, '.agents', 'skills');
  const bridgeDirectory = path.join(repoRoot, '.claude');
  const bridge = path.join(bridgeDirectory, 'skills');

  const canonicalState = await pathState(canonical);
  if (!canonicalState?.isDirectory()) {
    throw new Error(`canonical project skills directory is missing: ${canonical}`);
  }

  await mkdir(bridgeDirectory, { recursive: true });
  const existing = await pathState(bridge);
  if (existing?.isSymbolicLink()) {
    const [actual, expected] = await Promise.all([
      realpath(bridge),
      realpath(canonical),
    ]);
    if (actual === expected) {
      return { changed: false, bridge, canonical };
    }
    throw new Error(`refusing to replace a different Claude skills link: ${bridge}`);
  }

  if (existing) {
    if (!existing.isFile()) {
      throw new Error(`refusing to replace an existing Claude skills path: ${bridge}`);
    }
    const placeholder = (await readFile(bridge, 'utf8')).trim();
    if (placeholder !== POSIX_BRIDGE_TARGET) {
      throw new Error(`refusing to replace an existing Claude skills file: ${bridge}`);
    }
    await unlink(bridge);
  }

  const target = platform === 'win32' ? canonical : POSIX_BRIDGE_TARGET;
  const type = platform === 'win32' ? 'junction' : 'dir';
  await symlink(target, bridge, type);

  const [actual, expected] = await Promise.all([
    realpath(bridge),
    realpath(canonical),
  ]);
  if (actual !== expected) {
    throw new Error(`Claude skills bridge resolved to an unexpected path: ${actual}`);
  }
  return { changed: true, bridge, canonical };
}

export async function main() {
  const result = await ensureClaudeSkillsBridge();
  console.log(
    result.changed
      ? `[claude-skills] linked ${result.bridge} -> ${result.canonical}`
      : `[claude-skills] ok: ${result.bridge} -> ${result.canonical}`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(`[claude-skills] ${error.message}`);
    process.exitCode = 1;
  });
}
