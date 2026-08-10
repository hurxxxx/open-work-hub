import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectVersion = fs.readFileSync(path.join(rootDir, 'VERSION'), 'utf8').trim();

if (!/^\d+\.\d+\.\d+$/.test(projectVersion)) {
  console.error(`VERSION must be SemVer without a prefix, got ${JSON.stringify(projectVersion)}.`);
  process.exit(1);
}

const checks = [
  {
    file: 'package.json',
    pattern: /"version":\s*"([^"]+)"/,
    label: 'root package version',
  },
  {
    file: 'apps/api/pyproject.toml',
    pattern: /^version = "([^"]+)"/m,
    label: 'API package version',
  },
  {
    file: 'apps/worker/pyproject.toml',
    pattern: /^version = "([^"]+)"/m,
    label: 'worker package version',
  },
  {
    file: 'apps/ops/pyproject.toml',
    pattern: /^version = "([^"]+)"/m,
    label: 'ops package version',
  },
  {
    file: 'apps/api/src/open_alm_api/version.py',
    pattern: /^VERSION = "([^"]+)"/m,
    label: 'API runtime version',
  },
  {
    file: 'apps/api/uv.lock',
    pattern: /name = "open-alm-api"\nversion = "([^"]+)"/,
    label: 'API lockfile version',
  },
  {
    file: 'apps/worker/uv.lock',
    pattern: /name = "open-alm-worker"\nversion = "([^"]+)"/,
    label: 'worker lockfile version',
  },
  {
    file: 'apps/ops/uv.lock',
    pattern: /name = "open-alm-ops"\nversion = "([^"]+)"/,
    label: 'ops lockfile version',
  },
];

const errors = [];

for (const check of checks) {
  const fullPath = path.join(rootDir, check.file);
  const contents = fs.readFileSync(fullPath, 'utf8');
  const match = check.pattern.exec(contents);
  if (!match) {
    errors.push(`${check.file}: could not find ${check.label}.`);
    continue;
  }
  if (match[1] !== projectVersion) {
    errors.push(
      `${check.file}: ${check.label} is ${match[1]}, expected ${projectVersion}.`,
    );
  }
}

if (errors.length > 0) {
  console.error(['Project version check failed:', ...errors.map((item) => `- ${item}`)].join('\n'));
  process.exit(1);
}

console.log(`Project version ${projectVersion} is consistent.`);
