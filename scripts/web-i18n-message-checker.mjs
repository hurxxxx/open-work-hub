import fs from 'node:fs';
import path from 'node:path';

const DEFAULT_SKIP_DIRS = new Set(['node_modules', 'dist', 'coverage']);
const DEFAULT_FILE_RE = /\.(ts|tsx)$/;
const DEFAULT_EXCLUDE_FILE_RE =
  /(openapi\.generated\.d\.ts|\.spec\.tsx?$|\.test\.tsx?$)/;
const DEFAULT_EXCLUDE_PATH_PARTS = [
  `${path.sep}platform${path.sep}i18n${path.sep}`,
  `${path.sep}app-modules${path.sep}learning${path.sep}model${path.sep}`,
  // 이 legacy view는 API 계약의 한글 field/value를 UI wiring과 함께 보유한다.
  // 새 meal-invoice-ocr 파일까지 제외하지 않으며, 후속 분리 시 이 예외를 삭제한다.
  `${path.sep}app-modules${path.sep}meal-invoice-ocr${path.sep}views${path.sep}MealInvoiceOcrView.tsx`,
];

const DEFAULT_PATTERNS = [
  {
    kind: 'korean',
    re: /[가-힣][^`'"}<\n]*/g,
  },
  {
    kind: 'jsx-text',
    re: />\s*([A-Za-z][A-Za-z0-9 ,.!?&:/()#%+-]{2,})\s*</g,
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

const DEFAULT_ALLOW_RULES = [
  /i18n-exempt-line:/,
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

const NODE_FILE_SYSTEM = {
  existsSync: (target) => fs.existsSync(target),
  readFileSync: (target, encoding) => fs.readFileSync(target, encoding),
  readdirSync: (target, options) => fs.readdirSync(target, options),
};

function defaultSourceDirs(root) {
  return [path.join(root, 'apps/web/src'), path.join(root, 'packages/ui/src')];
}

function isAllowedValue(value) {
  // Stable message keys and route/tool ids are intentionally not display copy.
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) return true;
  // Common code fragments that can be caught by broad JSX heuristics.
  if (/^(current|new Promise)$/.test(value)) return true;
  if (/[A-Za-z_$][\w$]*\s*(?:&&|\?)\s*/.test(value)) return true;
  return false;
}

function isArrowFunctionMatch(text, match) {
  const index = match.index ?? 0;
  return text[index] === '>' && text[index - 1] === '=';
}

function lineForOffset(text, offset) {
  return text.slice(0, offset).split('\n').length;
}

function isInsideBlockComment(text, offset) {
  const before = text.slice(0, offset);
  const lastOpen = before.lastIndexOf('/*');
  if (lastOpen < 0) return false;
  const lastClose = before.lastIndexOf('*/');
  return lastClose < lastOpen;
}

function isInsideLineComment(text, offset) {
  const lineStart = text.lastIndexOf('\n', offset) + 1;
  const commentStart = text.indexOf('//', lineStart);
  return commentStart >= 0 && commentStart < offset;
}

function testRegex(re, value) {
  re.lastIndex = 0;
  return re.test(value);
}

function createPolicy({
  allowRules = DEFAULT_ALLOW_RULES,
  excludeFilePattern = DEFAULT_EXCLUDE_FILE_RE,
  excludePathParts = DEFAULT_EXCLUDE_PATH_PARTS,
  filePattern = DEFAULT_FILE_RE,
  patterns = DEFAULT_PATTERNS,
  skipDirs = DEFAULT_SKIP_DIRS,
} = {}) {
  return {
    allowRules,
    excludeFilePattern,
    excludePathParts,
    filePattern,
    patterns,
    skipDirs: skipDirs instanceof Set ? skipDirs : new Set(skipDirs),
  };
}

function shouldScanFile(fileName, absolutePath, policy) {
  return (
    testRegex(policy.filePattern, fileName) &&
    !testRegex(policy.excludeFilePattern, absolutePath) &&
    !policy.excludePathParts.some((part) => absolutePath.includes(part))
  );
}

function isAllowedLine(rule, line, finding) {
  if (typeof rule === 'function') {
    return rule({ ...finding, lineText: line });
  }
  return testRegex(rule, line);
}

function walk(dir, { fileSystem, policy }) {
  const entries = fileSystem.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (policy.skipDirs.has(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(abs, { fileSystem, policy }));
    } else if (shouldScanFile(entry.name, abs, policy)) {
      files.push(abs);
    }
  }
  return files;
}

export function findWebI18nFindingsInText(text, file, options = {}) {
  if (/^\s*\/\/\s*i18n-exempt-file:/m.test(text)) {
    return [];
  }
  const policy = createPolicy(options);
  const findings = [];
  for (const pattern of policy.patterns) {
    pattern.re.lastIndex = 0;
    for (const match of text.matchAll(pattern.re)) {
      if (pattern.kind === 'jsx-text' && isArrowFunctionMatch(text, match)) {
        continue;
      }
      const value = (match[1] ?? match[0]).trim();
      if (value.length < 3) continue;
      if (isAllowedValue(value)) continue;
      if (isInsideBlockComment(text, match.index ?? 0)) continue;
      if (isInsideLineComment(text, match.index ?? 0)) continue;
      const lineNumber = lineForOffset(text, match.index ?? 0);
      const line = text.split('\n')[lineNumber - 1] ?? '';
      if (/^\s*(\/\/|\/\*|\*)/.test(line)) continue;
      const finding = {
        file,
        kind: pattern.kind,
        line: lineNumber,
        value,
      };
      if (policy.allowRules.some((rule) => isAllowedLine(rule, line, finding)))
        continue;
      findings.push({
        ...finding,
      });
    }
  }
  return findings;
}

export function findWebI18nFindings({
  root = process.cwd(),
  srcDirs = defaultSourceDirs(root),
  fileSystem = NODE_FILE_SYSTEM,
  ...policyOptions
} = {}) {
  const policy = createPolicy(policyOptions);
  const findings = [];
  for (const file of srcDirs.flatMap((dir) =>
    fileSystem.existsSync(dir) ? walk(dir, { fileSystem, policy }) : [],
  )) {
    findings.push(
      ...findWebI18nFindingsInText(
        fileSystem.readFileSync(file, 'utf8'),
        path.relative(root, file),
        policy,
      ),
    );
  }
  return findings;
}

function groupFindingsByFile(findings) {
  const byFile = new Map();
  for (const finding of findings) {
    const current = byFile.get(finding.file) ?? [];
    current.push(finding);
    byFile.set(finding.file, current);
  }
  return byFile;
}

export function formatWebI18nFindings(findings) {
  const lines = [];
  const byFile = groupFindingsByFile(findings);
  for (const [file, items] of byFile) {
    lines.push(`${file}`);
    for (const item of items.slice(0, 8)) {
      lines.push(`  ${item.line}: [${item.kind}] ${item.value}`);
    }
    if (items.length > 8) {
      lines.push(`  ... ${items.length - 8} more`);
    }
  }
  lines.push('');
  lines.push(
    `${findings.length} potential hardcoded UI message(s) in ${byFile.size} file(s).`,
  );
  return lines.join('\n');
}
