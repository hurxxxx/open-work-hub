import fs from 'node:fs';
import path from 'node:path';

import {
  ALEMBIC_VERSION_PATTERN,
  DESTRUCTIVE_MIGRATION_PATTERNS,
  LANES,
  SHARED_TABLE_PATTERN,
} from './policy.mjs';

export function migrationRiskForChange(change, options = {}) {
  if (!ALEMBIC_VERSION_PATTERN.test(change.path)) {
    return null;
  }
  if (change.status.startsWith('D')) {
    return {
      path: change.path,
      reason: 'Migration file deletion changes schema history.',
      requiredLane: LANES.CORE_PLATFORM,
      nextAction:
        'Do not delete migration history in App Sandbox. Route through Core Platform review or add a forward migration.',
    };
  }

  const repoRoot = options.repoRoot ?? process.cwd();
  const readFile =
    options.readFile ??
    ((relativePath) => {
      const absolutePath = path.join(repoRoot, relativePath);
      if (!fs.existsSync(absolutePath)) {
        return '';
      }
      return fs.readFileSync(absolutePath, 'utf8');
    });
  const source = readFile(change.path);
  if (!source) {
    return null;
  }
  const upgradeSource = source.split(/\ndef\s+downgrade\s*\(/)[0] ?? source;
  const isDestructive = DESTRUCTIVE_MIGRATION_PATTERNS.some((pattern) =>
    pattern.test(upgradeSource),
  );
  if (isDestructive) {
    return {
      path: change.path,
      reason: 'Migration contains drop/truncate/delete operations.',
      requiredLane: LANES.CORE_PLATFORM,
      nextAction:
        'Route destructive schema changes through Core Platform review and include rollback/compatibility notes.',
    };
  }
  if (SHARED_TABLE_PATTERN.test(upgradeSource)) {
    return {
      path: change.path,
      reason: 'Migration touches shared/core platform tables.',
      requiredLane: LANES.CORE_PLATFORM,
      nextAction:
        'Move app-owned tables into an app-local migration, or route shared table changes through Core Platform review.',
    };
  }
  return null;
}
