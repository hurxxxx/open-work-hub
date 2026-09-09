import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const TESTED_CODEX_VERSION = '0.153.4';
const MAX_INPUT_BYTES = 1024 * 1024;
const hash = (value) => createHash('sha256').update(value).digest('hex');
const git = (root, args) =>
  execFileSync('git', ['-C', root, ...args], {
    encoding: 'utf8',
    timeout: 3000,
    maxBuffer: 8 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
const within = (root, target) => {
  const relative = path.relative(root, target);
  return (
    relative === '' ||
    (!relative.startsWith(`..${path.sep}`) &&
      relative !== '..' &&
      !path.isAbsolute(relative))
  );
};
const protectedData = (name) =>
  /(^|\/)(?:\.env(?:\..*)?|secrets|data|backups)(?:\/|$)/.test(name) &&
  name !== '.env.example';

export function resolveRoot(cwd) {
  if (typeof cwd !== 'string' || !path.isAbsolute(cwd))
    throw new Error('invalid cwd');
  return fs.realpathSync(git(cwd, ['rev-parse', '--show-toplevel']).trim());
}

function resolvedPatchPath(root, name) {
  let target = path.resolve(root, name);
  const tail = [];
  while (!fs.existsSync(target)) {
    const parent = path.dirname(target);
    if (parent === target) break;
    tail.unshift(path.basename(target));
    target = parent;
  }
  return path.join(fs.realpathSync(target), ...tail);
}

export function patchViolation(root, patch, cwd = root) {
  if (typeof patch !== 'string') throw new Error('invalid patch');
  for (const match of patch.matchAll(
    /^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm,
  )) {
    const name = match[1].trim();
    const target = resolvedPatchPath(cwd, name);
    if (
      target.split(path.sep).includes('.git') ||
      path.resolve(cwd, name).split(path.sep).includes('.git')
    ) {
      return 'Git metadata must be changed through Git, not a file patch.';
    }
    if (
      within(root, target) &&
      /(?:\.generated\.(?:ts|d\.ts)|_generated\.py)$/.test(target)
    ) {
      return 'Generated contracts must be updated through their owning generator.';
    }
  }
  return null;
}

export function workspaceSnapshot(root) {
  const names = new Set(
    [
      ...git(root, ['diff', '--name-only', '-z', 'HEAD']).split('\0'),
      ...git(root, ['ls-files', '--others', '--exclude-standard', '-z']).split(
        '\0',
      ),
    ].filter(Boolean),
  );
  const files = {};
  for (const name of [...names].sort()) {
    if (protectedData(name) || name.startsWith('.runtime/')) continue;
    const target = path.resolve(root, name);
    if (!within(root, target)) continue;
    try {
      const stat = fs.lstatSync(target);
      if (!within(root, fs.realpathSync(path.dirname(target)))) continue;
      files[name] = stat.isSymbolicLink()
        ? hash(fs.readlinkSync(target))
        : stat.isFile() && stat.size <= 8 * 1024 * 1024
          ? hash(fs.readFileSync(target))
          : `${stat.size}:${stat.mtimeMs}`;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      files[name] = 'deleted';
    }
  }
  return files;
}

function cacheDirectory(root, session) {
  if (typeof session !== 'string' || !session)
    throw new Error('missing session');
  const parts = ['.runtime', 'codex-hooks', hash(session)];
  let target = root;
  for (const part of parts) {
    target = path.join(target, part);
    try {
      fs.mkdirSync(target, { mode: 0o700 });
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
    }
    if (
      !fs.lstatSync(target).isDirectory() ||
      fs.lstatSync(target).isSymbolicLink()
    )
      throw new Error('unsafe cache directory');
  }
  return target;
}

function readCache(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 8 * 1024 * 1024)
    throw new Error('invalid cache');
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function immutableCache(file, value) {
  try {
    fs.writeFileSync(file, JSON.stringify(value), { flag: 'wx', mode: 0o600 });
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
}

export function selectChecks(names) {
  const checks = [];
  const add = (id, args) => {
    if (!checks.some((item) => item.id === id)) checks.push({ id, args });
  };
  if (names.length)
    add('diff', ['git', 'diff', '--check', 'HEAD', '--', ...names]);
  if (
    names.some(
      (n) =>
        n === 'package.json' ||
        /(^|\/)(?:AGENTS|CLAUDE)\.md$/.test(n) ||
        /^(?:\.agents\/|\.codex\/|docs\/agents\/|scripts\/check-skill-harness\.py$)/.test(
          n,
        ),
    )
  )
    add('skills', ['pnpm', 'check:skills']);
  if (
    names.some(
      (n) =>
        n === 'package.json' ||
        /^\.codex\/|^scripts\/(?:codex-hooks|agent-guidance)/.test(n),
    )
  )
    add('hooks', ['pnpm', 'test:codex-hooks']);
  if (names.some((n) => /(?:\/i18n\/|\/locales\/)/.test(n)))
    add('i18n', ['pnpm', 'check:i18n']);
  if (
    names.some(
      (n) =>
        n === '.env.example' ||
        /^(?:ops\/compose\/|scripts\/(?:dev-env|infra-stack|prod-app)\.)/.test(
          n,
        ) ||
        /\/settings\.py$/.test(n),
    )
  ) {
    add('env', ['pnpm', 'check:env-contract']);
    add('paths', ['pnpm', 'check:path-hardcoding']);
  }
  if (
    names.some((n) =>
      /(?:schemas\.py$|openapi\.generated\.d\.ts$|generate-openapi-client\.mjs$)/.test(
        n,
      ),
    )
  )
    add('api-contract', ['pnpm', 'check:api-contract']);
  if (
    names.some((n) =>
      /^(?:\.gitlab-ci\.yml|ops\/ci\/|scripts\/(?:check-gitlab-pipeline|codex-review-ci))/.test(
        n,
      ),
    )
  )
    add('ci', ['pnpm', 'check:gitlab-pipeline']);
  return checks;
}

export function runChecks(root, checks, run = execFileSync, budgetMs = 45000) {
  const deadline = Date.now() + budgetMs;
  return checks.map(({ id, args }) => {
    if (Date.now() >= deadline) return { id, status: 'timeout' };
    try {
      run(args[0], args.slice(1), {
        cwd: root,
        timeout: Math.max(1, deadline - Date.now()),
        maxBuffer: 2 * 1024 * 1024,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      return { id, status: 'passed' };
    } catch (error) {
      return {
        id,
        status:
          error.code === 'ETIMEDOUT'
            ? 'timeout'
            : error.code === 'ENOENT'
              ? 'unavailable'
              : 'failed',
      };
    }
  });
}

function feedback(event, message) {
  if (event === 'Stop') return { systemMessage: message };
  return {
    hookSpecificOutput: { hookEventName: event, additionalContext: message },
  };
}

export function handleEvent(input, dependencies = {}) {
  const root = (dependencies.resolveRoot ?? resolveRoot)(input.cwd);
  const event = input.hook_event_name;
  if (event === 'PreToolUse') {
    // Shell policy is owned by native .rules, whose runtime parser understands
    // shell composition. The public execpolicy check accepts argv, not shell text.
    const violation = ['apply_patch', 'Edit', 'Write'].includes(input.tool_name)
      ? patchViolation(root, input.tool_input?.command, input.cwd)
      : null;
    return violation
      ? {
          hookSpecificOutput: {
            hookEventName: event,
            permissionDecision: 'deny',
            permissionDecisionReason: violation,
          },
        }
      : {};
  }
  if (!['SessionStart', 'PostToolUse', 'Stop'].includes(event))
    throw new Error('unsupported event');
  const directory = cacheDirectory(root, input.session_id);
  const baselineFile = path.join(directory, 'baseline.json');
  const current = (dependencies.workspaceSnapshot ?? workspaceSnapshot)(root);
  if (event === 'SessionStart') {
    immutableCache(baselineFile, current);
    return {};
  }
  if (!fs.existsSync(baselineFile)) {
    // Do not attribute pre-existing work to this session when startup was missed.
    return feedback(
      event,
      'Codex validation has no session baseline. Run the affected checks explicitly; restart with trusted SessionStart hooks to enable automatic validation.',
    );
  }
  const baseline = readCache(baselineFile);
  const names = [
    ...new Set([...Object.keys(current), ...Object.keys(baseline)]),
  ].filter((name) => current[name] !== baseline[name]);
  if (!names.length) return {};
  const checks = selectChecks(names);
  // Hash the whole diff (including pre-existing dirty work) and validation machinery.
  const machinery = [
    'package.json',
    'pnpm-lock.yaml',
    'scripts/check-skill-harness.py',
    'scripts/codex-hooks.mjs',
    '.codex/hooks.json',
    '.codex/rules/project.rules',
  ];
  const signature = hash(
    JSON.stringify({
      current,
      checks,
      head: git(root, ['rev-parse', 'HEAD']).trim(),
      machinery: machinery.map((name) => {
        try {
          return hash(fs.readFileSync(path.join(root, name)));
        } catch {
          return 'missing';
        }
      }),
    }),
  );
  if (event === 'PostToolUse') {
    const marker = path.join(directory, `feedback-${signature}.json`);
    if (fs.existsSync(marker)) return {};
    const result = runChecks(
      root,
      checks.filter((check) => check.id === 'diff'),
      dependencies.run,
      2500,
    );
    immutableCache(marker, result);
    return result.some((item) => item.status !== 'passed')
      ? feedback(
          event,
          'The edited diff fails git diff --check. Fix whitespace before completion.',
        )
      : {};
  }
  const resultFile = path.join(directory, `checks-${signature}.json`);
  const results = fs.existsSync(resultFile)
    ? readCache(resultFile)
    : runChecks(root, checks, dependencies.run);
  // Failed/unavailable results are retryable; only successful checks are reusable.
  if (results.every((item) => item.status === 'passed')) {
    immutableCache(resultFile, results);
    return {};
  }
  const summary = results
    .filter((item) => item.status !== 'passed')
    .map((item) => `${item.id}: ${item.status}`)
    .join(', ');
  const message = `Automatic validation did not pass (${summary}). Run the affected check for details; report unresolved failures or missing environment accurately.`;
  return input.stop_hook_active
    ? { systemMessage: message }
    : { decision: 'block', reason: message };
}

export async function main() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > MAX_INPUT_BYTES) throw new Error('hook input too large');
    chunks.push(chunk);
  }
  const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  let result;
  try {
    result = handleEvent(input);
  } catch (error) {
    if (input.hook_event_name !== 'Stop' || !input.stop_hook_active)
      throw error;
    result = {
      systemMessage:
        'Project validation is unavailable. Report the missing checks; no further automatic continuation will be requested.',
    };
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === path.join(HERE, 'codex-hooks.mjs')
) {
  main().catch(() => {
    // Exit 2 is the documented blocking/feedback status. Never echo tool input or stderr.
    process.stderr.write(
      'Project hook failed to validate this operation. Inspect hook configuration and run the affected checks explicitly.\n',
    );
    process.exitCode = 2;
  });
}
