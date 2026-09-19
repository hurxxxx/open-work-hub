import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const api = fileURLToPath(new URL('../../codex-console-api', import.meta.url));
const target = fileURLToPath(
  new URL('../src/api.generated.ts', import.meta.url),
);
const source = JSON.parse(
  execFileSync('uv', ['run', '--frozen', 'codex-console', 'openapi'], {
    cwd: api,
    encoding: 'utf8',
  }),
);
const result = astToString(await openapiTS(source));
if (process.argv.includes('--check')) {
  if (readFileSync(target, 'utf8') !== result)
    throw new Error('Codex console API contract drift');
} else {
  writeFileSync(target, result);
}
