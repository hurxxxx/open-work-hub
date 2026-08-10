#!/usr/bin/env node

import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const TARGETS = ['apps/web/src', 'packages/ui/src'];
const EXTENSIONS = new Set(['.css', '.ts', '.tsx']);

const highRiskAccentForeground = [
  {
    name: 'bg-app-accent with light-mode-only foreground',
    pattern:
      /\bbg-app-accent\b(?=[^\n]*(?:\btext-white\b|\btext-app-bg\b))|(?:\btext-white\b|\btext-app-bg\b)(?=[^\n]*\bbg-app-accent\b)/,
    guidance: 'Use text-app-accent-fg on bg-app-accent.',
  },
  {
    name: 'bg-ui-accent with light-mode-only foreground',
    pattern:
      /\bbg-ui-accent\b(?=[^\n]*(?:\btext-white\b|\btext-app-bg\b))|(?:\btext-white\b|\btext-app-bg\b)(?=[^\n]*\bbg-ui-accent\b)/,
    guidance: 'Use text-[var(--ui-color-accent-fg)] on bg-ui-accent.',
  },
  {
    name: 'CSS var accent with light-mode-only foreground',
    pattern:
      /\bbg-\[var\(--ui-color-accent\)\](?=[^\n]*(?:\btext-white\b|\btext-app-bg\b))|(?:\btext-white\b|\btext-app-bg\b)(?=[^\n]*\bbg-\[var\(--ui-color-accent\)\])/,
    guidance: 'Use the accent foreground token on accent backgrounds.',
  },
];

const exactBgWhite = /(?:^|[\s'"`])bg-white(?:$|[\s'"`])/;

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const fullPath = path.join(dir, name);
    const stats = statSync(fullPath);
    if (stats.isDirectory()) {
      yield* walk(fullPath);
    } else if (EXTENSIONS.has(path.extname(fullPath))) {
      yield fullPath;
    }
  }
}

const findings = [];

for (const target of TARGETS) {
  const absTarget = path.join(ROOT, target);
  for (const filePath of walk(absTarget)) {
    const relativePath = path.relative(ROOT, filePath);
    const lines = readFileSync(filePath, 'utf8').split('\n');

    lines.forEach((line, index) => {
      for (const rule of highRiskAccentForeground) {
        if (rule.pattern.test(line)) {
          findings.push({
            file: relativePath,
            line: index + 1,
            message: `${rule.name}. ${rule.guidance}`,
          });
        }
      }

      if (relativePath.startsWith('packages/ui/src/') && exactBgWhite.test(line)) {
        findings.push({
          file: relativePath,
          line: index + 1,
          message:
            'Shared UI components must use surface tokens instead of exact bg-white.',
        });
      }
    });
  }
}

if (findings.length > 0) {
  console.error('Dark-mode token check failed:');
  for (const finding of findings) {
    console.error(`- ${finding.file}:${finding.line} ${finding.message}`);
  }
  process.exit(1);
}

console.log('Dark-mode token check passed.');
