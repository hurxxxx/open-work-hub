#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const SRC_DIRS = [
  path.join(ROOT, 'apps/web/src'),
  path.join(ROOT, 'packages/ui/src'),
];
const FAIL = process.argv.includes('--fail-on-findings');

const SKIP_DIRS = new Set(['node_modules', 'dist', 'coverage']);
const FILE_RE = /\.(ts|tsx)$/;
const EXCLUDE_FILE_RE = /(openapi\.generated\.d\.ts|\.spec\.tsx?$|\.test\.tsx?$)/;
const EXCLUDE_PATH_PARTS = [
  `${path.sep}platform${path.sep}i18n${path.sep}`,
  `${path.sep}app-modules${path.sep}learning${path.sep}model${path.sep}`,
];

const PATTERNS = [
  {
    kind: 'korean',
    re: /[가-힣][^`'"}<\n]*/g,
  },
  {
    kind: 'jsx-text',
    re: />\s*([A-Za-z][A-Za-z0-9 ,.!?&:/()#%+\-]{2,})\s*</g,
  },
  {
    kind: 'display-prop',
    re: /\b(?:placeholder|aria-label|title|label|description)\s*=\s*["']([A-Za-z가-힣][^"']{2,})["']/g,
  },
  {
    kind: 'message-call',
    re: /\b(?:setError|setMessage|throw new Error|confirm|prompt)\(\s*["']([A-Za-z가-힣][^"']{2,})["']/g,
  },
  {
    kind: 'option-label',
    re: /\b(?:label|description|title|desc)\s*:\s*["']([A-Za-z가-힣][^"']{2,})["']/g,
  },
];

const ALLOW_RE = [
  /data-testid=/,
  /className=/,
  /import\s/,
  /from\s+['"]/,
  /type\s+.*=/,
  /interface\s/,
  /Record</,
  /Promise</,
  /new Promise/,
  /console\./,
  /must be used within/,
  /CustomEvent\(/,
  /localStorage/,
  /sessionStorage/,
  /api\/v1/,
  /https?:\/\//,
  /\/.*가-힣.*\//,
  /\?\s*\(/,
  /[A-Z_]{3,}/,
];

function isAllowedValue(value) {
  // Stable message keys and route/tool ids are intentionally not display copy.
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) return true;
  // Common code fragments that can be caught by broad JSX heuristics.
  if (/^(current|new Promise)$/.test(value)) return true;
  if (/[A-Za-z_$][\w$]*\s*(?:&&|\?)\s*/.test(value)) return true;
  return false;
}

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(abs));
    } else if (FILE_RE.test(entry.name) && !EXCLUDE_FILE_RE.test(abs)) {
      if (EXCLUDE_PATH_PARTS.some((part) => abs.includes(part))) continue;
      files.push(abs);
    }
  }
  return files;
}

function lineForOffset(text, offset) {
  return text.slice(0, offset).split('\n').length;
}

const findings = [];
for (const file of SRC_DIRS.flatMap((dir) => (fs.existsSync(dir) ? walk(dir) : []))) {
  const text = fs.readFileSync(file, 'utf8');
  for (const pattern of PATTERNS) {
    pattern.re.lastIndex = 0;
    for (const match of text.matchAll(pattern.re)) {
      const value = (match[1] ?? match[0]).trim();
      if (value.length < 3) continue;
      if (isAllowedValue(value)) continue;
      const line = text.split('\n')[lineForOffset(text, match.index ?? 0) - 1] ?? '';
      if (/^\s*(\/\/|\*)/.test(line)) continue;
      if (ALLOW_RE.some((re) => re.test(line))) continue;
      findings.push({
        file: path.relative(ROOT, file),
        kind: pattern.kind,
        line: lineForOffset(text, match.index ?? 0),
        value,
      });
    }
  }
}

const byFile = new Map();
for (const finding of findings) {
  const current = byFile.get(finding.file) ?? [];
  current.push(finding);
  byFile.set(finding.file, current);
}

for (const [file, items] of byFile) {
  console.log(`${file}`);
  for (const item of items.slice(0, 8)) {
    console.log(`  ${item.line}: [${item.kind}] ${item.value}`);
  }
  if (items.length > 8) {
    console.log(`  ... ${items.length - 8} more`);
  }
}

console.log(`\n${findings.length} potential hardcoded UI message(s) in ${byFile.size} file(s).`);

if (FAIL && findings.length > 0) {
  process.exitCode = 1;
}
