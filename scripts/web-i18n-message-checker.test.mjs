import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';

import {
  findWebI18nFindings,
  findWebI18nFindingsInText,
  formatWebI18nFindings,
} from './web-i18n-message-checker.mjs';

function createMemoryFileSystem(files) {
  const sources = new Map(
    Object.entries(files).map(([file, source]) => [
      path.normalize(file),
      source,
    ]),
  );

  return {
    existsSync(target) {
      const normalizedTarget = path.normalize(target);
      const targetPrefix = normalizedTarget.endsWith(path.sep)
        ? normalizedTarget
        : `${normalizedTarget}${path.sep}`;

      if (sources.has(normalizedTarget)) return true;
      for (const file of sources.keys()) {
        if (file.startsWith(targetPrefix)) return true;
      }
      return false;
    },

    readFileSync(target, encoding) {
      assert.equal(encoding, 'utf8');
      const source = sources.get(path.normalize(target));
      if (source === undefined) {
        throw new Error(`Missing in-memory fixture: ${target}`);
      }
      return source;
    },

    readdirSync(target, options) {
      assert.equal(options?.withFileTypes, true);
      const normalizedTarget = path.normalize(target);
      const targetPrefix = normalizedTarget.endsWith(path.sep)
        ? normalizedTarget
        : `${normalizedTarget}${path.sep}`;
      const children = new Map();

      for (const file of sources.keys()) {
        if (!file.startsWith(targetPrefix)) continue;
        const relativePath = file.slice(targetPrefix.length);
        if (!relativePath) continue;
        const [name, ...rest] = relativePath.split(path.sep);
        children.set(name, (children.get(name) ?? false) || rest.length > 0);
      }

      return [...children.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([name, isDirectory]) => ({
          name,
          isDirectory: () => isDirectory,
        }));
    },
  };
}

function scanMemoryFiles(files, options = {}) {
  const root = path.join(path.sep, 'repo');
  return findWebI18nFindings({
    root,
    srcDirs: [path.join(root, 'apps/web/src')],
    fileSystem: createMemoryFileSystem(files),
    ...options,
  });
}

test('finds literal JSX text that should come from i18n resources', () => {
  const findings = findWebI18nFindingsInText(
    'export function View() { return <button>Save changes</button>; }\n',
    'View.tsx',
  );

  assert.deepEqual(findings, [
    {
      file: 'View.tsx',
      kind: 'jsx-text',
      line: 1,
      value: 'Save changes',
    },
  ]);
});

test('does not treat arrow function expressions as JSX text', () => {
  const findings = findWebI18nFindingsInText(
    [
      'const candidates = useMemo(() => selectUserOptionsForPicker<PmsUserSummary>({ users }), [users]);',
      'const offset = chunks.filter((chunk) => chunk.seq < seq).length;',
      'type Plan = { successPatch: (message: string) => Partial<State> };',
    ].join('\n'),
    'model.ts',
  );

  assert.deepEqual(findings, []);
});

test('does not treat line or block comments as UI copy', () => {
  const findings = findWebI18nFindingsInText(
    [
      '// 저장 버튼 설명',
      '/* 업로드 영역 */',
      'const visible = <button>Save changes</button>;',
      'const config = { label: "Visible label" }; // 관리자 전용 설명',
      '/*',
      ' * 파일 선택 안내',
      ' */',
    ].join('\n'),
    'View.tsx',
  );

  assert.deepEqual(findings, [
    {
      file: 'View.tsx',
      kind: 'jsx-text',
      line: 3,
      value: 'Save changes',
    },
    {
      file: 'View.tsx',
      kind: 'option-label',
      line: 4,
      value: 'Visible label',
    },
  ]);
});

test('allows explicitly exempt domain data modules', () => {
  const findings = findWebI18nFindingsInText(
    [
      '// i18n-exempt-file: domain contract constants; callers localize display labels.',
      'export const labels = ["개발목표온도"];',
    ].join('\n'),
    'domain-contract.ts',
  );

  assert.deepEqual(findings, []);
});

test('allows explicitly exempt domain value lines', () => {
  const findings = findWebI18nFindingsInText(
    [
      "const brand = '현대'; // i18n-exempt-line: stored domain value",
      '<span>Visible label</span>',
    ].join('\n'),
    'domain-contract.tsx',
  );

  assert.deepEqual(
    findings.map((finding) => finding.value),
    ['Visible label'],
  );
});

test('walk skips ignored directories', () => {
  const root = path.join(path.sep, 'repo');
  const findings = scanMemoryFiles({
    [path.join(root, 'apps/web/src/Visible.tsx')]:
      'export function View() { return <button>Save changes</button>; }\n',
    [path.join(root, 'apps/web/src/node_modules/Ignored.tsx')]:
      'export function View() { return <button>Install now</button>; }\n',
    [path.join(root, 'apps/web/src/dist/Ignored.tsx')]:
      'export function View() { return <button>Publish now</button>; }\n',
    [path.join(root, 'apps/web/src/coverage/Ignored.tsx')]:
      'export function View() { return <button>Retry later</button>; }\n',
  });

  assert.deepEqual(findings, [
    {
      file: 'apps/web/src/Visible.tsx',
      kind: 'jsx-text',
      line: 1,
      value: 'Save changes',
    },
  ]);
});

test('walk excludes specs, tests, and generated OpenAPI declarations', () => {
  const root = path.join(path.sep, 'repo');
  const findings = scanMemoryFiles({
    [path.join(root, 'apps/web/src/Actual.tsx')]:
      'export function View() { return <button>Save changes</button>; }\n',
    [path.join(root, 'apps/web/src/Actual.spec.tsx')]:
      'export function View() { return <button>Spec only</button>; }\n',
    [path.join(root, 'apps/web/src/Actual.test.ts')]:
      'throw new Error("Test only");\n',
    [path.join(root, 'apps/web/src/platform/api/openapi.generated.d.ts')]:
      'export type ApiMessage = "Generated only";\n',
  });

  assert.deepEqual(
    findings.map((finding) => finding.file),
    ['apps/web/src/Actual.tsx'],
  );
});

test('walk excludes paths that own i18n resources or learning model data', () => {
  const root = path.join(path.sep, 'repo');
  const findings = scanMemoryFiles({
    [path.join(root, 'apps/web/src/Feature.tsx')]:
      'export function View() { return <button>Save changes</button>; }\n',
    [path.join(root, 'apps/web/src/platform/i18n/resources.ts')]:
      'export const resources = { "en-US": { save: "Save changes" } };\n',
    [path.join(root, 'apps/web/src/app-modules/learning/model/cards.ts')]:
      'export const card = { title: "학습 카드" };\n',
  });

  assert.deepEqual(
    findings.map((finding) => finding.file),
    ['apps/web/src/Feature.tsx'],
  );
});

test('scanner reports messages in ordinary app views', () => {
  const root = path.join(path.sep, 'repo');
  const findings = scanMemoryFiles({
    [path.join(
      root,
      'apps/web/src/app-modules/docs/views/NewPanel.tsx',
    )]:
      'export function NewPanel() { return <button>Save document</button>; }\n',
  });

  assert.deepEqual(
    findings.map((finding) => finding.file),
    ['apps/web/src/app-modules/docs/views/NewPanel.tsx'],
  );
});

test('scanner accepts injected allow rules', () => {
  const root = path.join(path.sep, 'repo');
  const findings = scanMemoryFiles(
    {
      [path.join(root, 'apps/web/src/Feature.ts')]:
        'throw new Error("Visible failure"); // allow-web-i18n-fixture\n',
    },
    {
      allowRules: [/allow-web-i18n-fixture/],
    },
  );

  assert.deepEqual(findings, []);
});

test('formats grouped findings for CLI output', () => {
  assert.equal(
    formatWebI18nFindings([
      {
        file: 'View.tsx',
        kind: 'jsx-text',
        line: 3,
        value: 'Save changes',
      },
    ]),
    'View.tsx\n  3: [jsx-text] Save changes\n\n1 potential hardcoded UI message(s) in 1 file(s).',
  );
});
