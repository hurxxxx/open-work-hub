#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs']);
const skippedDirectories = new Set(['dist', 'node_modules']);

const forbiddenSpecifiers = [
  {
    pattern: /^@\/src\//,
    reason:
      'core-web must not import the web application source alias. Move shared code into packages instead.',
  },
  {
    pattern: /^@ai-do\/web-shell(?:\/|$)/,
    reason: 'core-web must be below the web shell boundary, not depend on it.',
  },
];

function walkSourceFiles(directory) {
  const entries = fs
    .readdirSync(directory, { withFileTypes: true })
    .toSorted((left, right) => left.name.localeCompare(right.name));
  const files = [];

  for (const entry of entries) {
    if (skippedDirectories.has(entry.name)) {
      continue;
    }

    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkSourceFiles(fullPath));
      continue;
    }
    if (sourceExtensions.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }

  return files;
}

function collectSpecifiers(source) {
  const specifiers = [];
  const staticPattern =
    /\b(?:import|export)\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]/g;
  const dynamicPattern = /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g;

  for (const pattern of [staticPattern, dynamicPattern]) {
    let match;
    while ((match = pattern.exec(source)) !== null) {
      specifiers.push(match[1]);
    }
  }

  return specifiers;
}

function resolveRelativeImport(importer, specifier) {
  if (!specifier.startsWith('./') && !specifier.startsWith('../')) {
    return null;
  }
  return path.resolve(path.dirname(importer), specifier);
}

function collectViolations(repoRoot) {
  const packageSourceRoot = path.join(repoRoot, 'packages/core-web/src');
  const violations = [];

  for (const file of walkSourceFiles(packageSourceRoot)) {
    const source = fs.readFileSync(file, 'utf8');
    for (const specifier of collectSpecifiers(source)) {
      const forbidden = forbiddenSpecifiers.find(({ pattern }) =>
        pattern.test(specifier),
      );
      if (forbidden) {
        violations.push({
          file,
          reason: forbidden.reason,
          specifier,
        });
        continue;
      }

      const resolved = resolveRelativeImport(file, specifier);
      if (
        resolved &&
        !path
          .relative(packageSourceRoot, resolved)
          .split(path.sep)
          .every((segment) => segment !== '..')
      ) {
        violations.push({
          file,
          reason:
            'core-web source files must not import files outside packages/core-web/src.',
          specifier,
        });
      }
    }
  }

  return violations;
}

function formatViolations(violations, repoRoot) {
  const lines = ['core-web boundary violations found:', ''];
  for (const violation of violations) {
    lines.push(
      `- ${path.relative(repoRoot, violation.file)} imports "${violation.specifier}"`,
    );
    lines.push(`  ${violation.reason}`);
  }
  return lines.join('\n');
}

const repoRoot = path.resolve(import.meta.dirname, '..');
const violations = collectViolations(repoRoot);

if (violations.length > 0) {
  console.error(formatViolations(violations, repoRoot));
  process.exitCode = 1;
}
