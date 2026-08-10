#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const repoRoot = process.cwd();
const checkOnly = process.argv.includes('--check');
const noSync = process.argv.includes('--no-sync');
const targetPath = path.join(
  repoRoot,
  'packages/contracts/src/openapi.generated.d.ts',
);
const tempDir = mkdtempSync(path.join(tmpdir(), 'open-alm-openapi-'));
const schemaPath = path.join(tempDir, 'openapi.json');
const generatedPath = checkOnly
  ? path.join(tempDir, 'openapi.generated.d.ts')
  : targetPath;

function run(command, args, options = {}) {
  execFileSync(command, args, {
    cwd: repoRoot,
    stdio: 'inherit',
    ...options,
  });
}

try {
  run(
    'uv',
    [
      'run',
      ...(noSync ? ['--no-sync'] : []),
      '--python',
      '3.12',
      'python',
      '-c',
      [
        'import json, os',
        'from pathlib import Path',
        'from open_alm_api.app import create_app',
        'from open_alm_api.openapi_contract import assert_openapi_contract',
        'app = create_app(initialize_runtime=False)',
        'schema = app.openapi()',
        'assert_openapi_contract(schema)',
        'Path(os.environ["OPEN_ALM_OPENAPI_OUTPUT"]).write_text(',
        '    json.dumps(schema, ensure_ascii=False, indent=2) + "\\n",',
        '    encoding="utf-8",',
        ')',
      ].join('\n'),
    ],
    {
      cwd: path.join(repoRoot, 'apps/api'),
      env: {
        ...process.env,
        OPEN_ALM_OPENAPI_OUTPUT: schemaPath,
        OPEN_ALM_POSTGRES_DSN:
          process.env.OPEN_ALM_POSTGRES_DSN ??
          'postgresql+psycopg://openapi:openapi@127.0.0.1:1/openapi',
        OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP: '0',
      },
    },
  );

  run('pnpm', ['exec', 'openapi-typescript', schemaPath, '-o', generatedPath]);

  if (checkOnly) {
    const expected = readFileSync(targetPath, 'utf8');
    const actual = readFileSync(generatedPath, 'utf8');
    if (expected !== actual) {
      console.error(
        'OpenAPI generated types are out of date. Run `pnpm generate:api-client`.',
      );
      process.exit(1);
    }
  }
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
