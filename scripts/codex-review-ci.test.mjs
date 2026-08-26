import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const runnerSource = fs.readFileSync(
  path.join(repoRoot, 'scripts/codex-review-ci.sh'),
  'utf8',
);

test('passes approval policy as a Codex global option before exec', () => {
  assert.match(
    runnerSource,
    /"\$codex_bin" \\\n\s+-a never \\\n\s+exec \\/,
  );
  assert.doesNotMatch(
    runnerSource,
    /"\$codex_bin" exec \\\n[\s\S]{0,400}\s+-a never \\/,
  );
});
