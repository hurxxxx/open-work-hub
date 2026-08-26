import fs from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(import.meta.dirname, '..');
const packageJsonPath = path.join(repoRoot, 'packages/contracts/package.json');
const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
const tag = process.env.CI_COMMIT_TAG;
const expectedTag = `contracts-v${packageJson.version}`;

if (!tag) {
  throw new Error(
    'CI_COMMIT_TAG is required to publish @open-work-hub/contracts.',
  );
}

if (tag !== expectedTag) {
  throw new Error(
    `Contract package tag mismatch. Expected ${expectedTag} for @open-work-hub/contracts ${packageJson.version}, got ${tag}.`,
  );
}
