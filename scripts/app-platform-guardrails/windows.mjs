import fs from 'node:fs';
import path from 'node:path';

import { normalizePath } from './classifier.mjs';
import { WINDOWS_FORBIDDEN_PATTERNS, WINDOWS_GUARDRAIL_FILES } from './policy.mjs';

export function validateWindowsDevGuardrailSource(filePath, source) {
  const normalizedPath = normalizePath(filePath);
  const errors = [];
  for (const { pattern, label } of WINDOWS_FORBIDDEN_PATTERNS) {
    if (pattern.test(source)) {
      errors.push({
        filePath: normalizedPath,
        message: `Windows administrator dev surface must not reference ${label}.`,
      });
    }
  }
  return errors;
}

export function validateWindowsDevGuardrails({ repoRoot = process.cwd() } = {}) {
  const errors = [];
  for (const filePath of WINDOWS_GUARDRAIL_FILES) {
    const absolutePath = path.join(repoRoot, filePath);
    if (!fs.existsSync(absolutePath)) {
      errors.push({
        filePath,
        message: 'Windows administrator dev surface file is required.',
      });
      continue;
    }
    const source = fs.readFileSync(absolutePath, 'utf8');
    errors.push(...validateWindowsDevGuardrailSource(filePath, source));
  }
  return { ok: errors.length === 0, errors };
}
