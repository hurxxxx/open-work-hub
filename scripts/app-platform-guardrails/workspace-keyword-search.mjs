import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const FRONTEND_LEGACY_TOKENS = [
  'workspaceSearchSource',
  'workspaceSearchSourceAppIds',
  'WORKSPACE_SEARCH_SOURCE_APP_IDS',
];
const SEARCH_PROJECTION_PATH =
  /^apps\/api\/src\/ai_do_api\/domains\/([^/]+)\/search_projection\.py$/;
const SEARCH_LABEL_KEY_PATTERN = /^ai\.search\.(entity[A-Z][A-Za-z0-9]*)$/;
const SEARCH_LIFECYCLE_OPERATIONS = ['create', 'update', 'delete'];

function visitFiles(directory, callback) {
  if (!fs.existsSync(directory)) {
    return;
  }
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      visitFiles(absolutePath, callback);
    } else if (entry.isFile()) {
      callback(absolutePath);
    }
  }
}

function relativePath(repoRoot, absolutePath) {
  return path.relative(repoRoot, absolutePath).replaceAll(path.sep, '/');
}

function readFileIfPresent(filePath) {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function pythonTestFunctionBodies(source) {
  const definitions = [
    ...source.matchAll(/^(?:(?:async\s+)?def|class)\s+([A-Za-z0-9_]+)/gm),
  ];
  return definitions.flatMap((definition, index) => {
    if (!definition[0].startsWith('def test_')) {
      return [];
    }
    return [
      source.slice(
        definition.index,
        definitions[index + 1]?.index ?? source.length,
      ),
    ];
  });
}

function hasExecutableLifecycleEvidence(source, entityType, operation) {
  const helper =
    operation === 'delete'
      ? '_process_pending_delete'
      : '_process_pending_entity';
  const entityPattern = new RegExp(
    `\\bentity_type\\s*=\\s*["']${escapeRegExp(entityType)}["']`,
  );
  const operationPattern = new RegExp(
    `\\blifecycle_operation\\s*=\\s*["']${escapeRegExp(operation)}["']`,
  );
  const callPattern = new RegExp(
    `^\\s+(?:[A-Za-z_][A-Za-z0-9_]*\\s*=\\s*)?${helper}\\(([\\s\\S]*?)\\)`,
    'gm',
  );

  return pythonTestFunctionBodies(source).some((testBody) =>
    [...testBody.matchAll(callPattern)].some(
      (call) => entityPattern.test(call[1]) && operationPattern.test(call[1]),
    ),
  );
}

function propertyNameText(name) {
  if (
    ts.isIdentifier(name) ||
    ts.isStringLiteral(name) ||
    ts.isNumericLiteral(name)
  ) {
    return name.text;
  }
  return null;
}

function objectPropertyAssignments(objectLiteral, propertyName) {
  return objectLiteral.properties.filter(
    (property) =>
      ts.isPropertyAssignment(property) &&
      propertyNameText(property.name) === propertyName,
  );
}

function asObjectLiteral(expression) {
  let candidate = expression;
  while (
    candidate &&
    (ts.isAsExpression(candidate) ||
      ts.isSatisfiesExpression(candidate) ||
      ts.isParenthesizedExpression(candidate))
  ) {
    candidate = candidate.expression;
  }
  return candidate && ts.isObjectLiteralExpression(candidate)
    ? candidate
    : null;
}

function nestedObjectProperty(objectLiteral, propertyName) {
  const matches = objectPropertyAssignments(objectLiteral, propertyName);
  if (matches.length !== 1) {
    return null;
  }
  return asObjectLiteral(matches[0].initializer);
}

function searchLabelLocaleCoverage(resourcesSource, labelProperty) {
  const sourceFile = ts.createSourceFile(
    'resources.ts',
    resourcesSource,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  let resourcesObject = null;
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) {
      continue;
    }
    for (const declaration of statement.declarationList.declarations) {
      if (
        ts.isIdentifier(declaration.name) &&
        declaration.name.text === 'resources' &&
        declaration.initializer
      ) {
        resourcesObject = asObjectLiteral(declaration.initializer);
      }
    }
  }
  if (!resourcesObject) {
    return { localeCount: 0, validLocaleCount: 0, invalidLocales: [] };
  }

  const locales = resourcesObject.properties.filter(ts.isPropertyAssignment);
  const invalidLocales = [];
  let validLocaleCount = 0;
  for (const locale of locales) {
    const localeName = propertyNameText(locale.name) ?? '<unknown>';
    const localeObject = asObjectLiteral(locale.initializer);
    if (!localeObject) {
      invalidLocales.push(localeName);
      continue;
    }
    const apps = nestedObjectProperty(localeObject, 'apps');
    const ai = apps && nestedObjectProperty(apps, 'ai');
    const search = ai && nestedObjectProperty(ai, 'search');
    const labels = search
      ? objectPropertyAssignments(search, labelProperty)
      : [];
    if (labels.length === 1) {
      validLocaleCount += 1;
    } else {
      invalidLocales.push(localeName);
    }
  }
  return {
    localeCount: locales.length,
    validLocaleCount,
    invalidLocales,
  };
}

function searchEntityEnumValues(repoRoot) {
  const schemaSource = readFileIfPresent(
    path.join(repoRoot, 'apps/api/src/ai_do_api/domains/search/schemas.py'),
  );
  return new Map(
    [
      ...schemaSource.matchAll(
        /^\s+([A-Z][A-Z0-9_]*)\s*=\s*["']([^"']+)["']/gm,
      ),
    ].map((match) => [match[1], match[2]]),
  );
}

function searchAdapterDeclarations({ domain, filePath, source, enumValues }) {
  const declarations = [];
  const adapterPattern =
    /^([A-Z][A-Z0-9_]*)\s*=\s*SearchEntityAdapter\(([\s\S]*?)^\)/gm;
  for (const match of source.matchAll(adapterPattern)) {
    const body = match[2];
    const literalEntityType = body.match(
      /\bentity_type\s*=\s*["']([^"']+)["']/,
    )?.[1];
    const enumName = body.match(
      /\bentity_type\s*=\s*SearchEntityType\.([A-Z][A-Z0-9_]*)\.value/,
    )?.[1];
    const labelKey = body.match(/\blabel_key\s*=\s*["']([^"']+)["']/)?.[1];
    declarations.push({
      constantName: match[1],
      domain,
      entityType: literalEntityType ?? enumValues.get(enumName) ?? null,
      filePath,
      labelKey: labelKey ?? null,
    });
  }
  return declarations;
}

export function validateWorkspaceKeywordSearchHarness({
  repoRoot = process.cwd(),
} = {}) {
  const errors = [];
  const adapterDeclarations = [];
  const enumValues = searchEntityEnumValues(repoRoot);
  visitFiles(path.join(repoRoot, 'apps/web/src'), (absolutePath) => {
    if (!/\.(?:ts|tsx)$/.test(absolutePath)) {
      return;
    }
    const source = fs.readFileSync(absolutePath, 'utf8');
    for (const token of FRONTEND_LEGACY_TOKENS) {
      if (source.includes(token)) {
        errors.push({
          filePath: relativePath(repoRoot, absolutePath),
          message:
            `Frontend ${token} is not authoritative. Register a SearchEntityAdapter ` +
            'in domains/<domain>/search_projection.py and consume workspace bootstrap.',
        });
      }
    }
  });

  visitFiles(
    path.join(repoRoot, 'apps/api/src/ai_do_api/domains'),
    (absolutePath) => {
      if (!absolutePath.endsWith('.py')) {
        return;
      }
      const filePath = relativePath(repoRoot, absolutePath);
      const source = fs.readFileSync(absolutePath, 'utf8');
      const projectionMatch = filePath.match(SEARCH_PROJECTION_PATH);
      if (
        source.includes('SearchEntityAdapter(') &&
        filePath !==
          'apps/api/src/ai_do_api/domains/search/entity_adapter_registry.py' &&
        !projectionMatch
      ) {
        errors.push({
          filePath,
          message:
            'SearchEntityAdapter declarations must live in domains/<domain>/search_projection.py.',
        });
      }
      if (
        /register_search_(?:entity_descriptor|projection_adapter)\s*\(/.test(
          source,
        ) &&
        !filePath.startsWith('apps/api/src/ai_do_api/domains/search/')
      ) {
        errors.push({
          filePath,
          message:
            'App domains must register workspace keyword search through SearchEntityAdapter, not low-level registries.',
        });
      }
      if (projectionMatch && source.includes('SearchEntityAdapter(')) {
        const declarations = searchAdapterDeclarations({
          domain: projectionMatch[1],
          filePath,
          source,
          enumValues,
        });
        if (declarations.length === 0) {
          errors.push({
            filePath,
            message:
              'SearchEntityAdapter must be assigned to an uppercase module constant for explicit composition.',
          });
        }
        adapterDeclarations.push(...declarations);
      }
    },
  );

  const compositionSource = readFileIfPresent(
    path.join(
      repoRoot,
      'apps/api/src/ai_do_api/domains/search/default_entity_adapters.py',
    ),
  );
  const lifecycleTestSource = readFileIfPresent(
    path.join(repoRoot, 'apps/api/tests/test_search_index_hooks.py'),
  );
  const resourcesSource = readFileIfPresent(
    path.join(repoRoot, 'apps/web/src/platform/i18n/resources.ts'),
  );

  for (const declaration of adapterDeclarations) {
    const moduleName = `ai_do_api.domains.${declaration.domain}.search_projection`;
    const constantOccurrences = [
      ...compositionSource.matchAll(
        new RegExp(`\\b${escapeRegExp(declaration.constantName)}\\b`, 'g'),
      ),
    ].length;
    if (!compositionSource.includes(moduleName) || constantOccurrences < 2) {
      errors.push({
        filePath: declaration.filePath,
        message:
          `${declaration.constantName} is missing from the explicit ` +
          'domains/search/default_entity_adapters.py composition root.',
      });
    }
    if (!declaration.entityType) {
      errors.push({
        filePath: declaration.filePath,
        message:
          `${declaration.constantName} must use a literal entity_type or a declared ` +
          'SearchEntityType enum value so lifecycle evidence can be checked.',
      });
    } else {
      for (const operation of SEARCH_LIFECYCLE_OPERATIONS) {
        if (
          !hasExecutableLifecycleEvidence(
            lifecycleTestSource,
            declaration.entityType,
            operation,
          )
        ) {
          errors.push({
            filePath: declaration.filePath,
            message:
              `${declaration.constantName} is missing executable CRUD-to-outbox ` +
              `integration evidence for ${declaration.entityType}:${operation} in ` +
              'apps/api/tests/test_search_index_hooks.py. Call the search processing ' +
              'assertion helper with matching entity_type and lifecycle_operation.',
          });
        }
      }
    }

    const labelMatch = declaration.labelKey?.match(SEARCH_LABEL_KEY_PATTERN);
    if (!labelMatch) {
      errors.push({
        filePath: declaration.filePath,
        message:
          `${declaration.constantName} label_key must match ` +
          'ai.search.entity<Name> for the shared apps i18n catalog.',
      });
      continue;
    }
    const localeCoverage = searchLabelLocaleCoverage(
      resourcesSource,
      labelMatch[1],
    );
    if (
      localeCoverage.localeCount === 0 ||
      localeCoverage.validLocaleCount !== localeCoverage.localeCount
    ) {
      const invalidLocaleDetail =
        localeCoverage.invalidLocales.length > 0
          ? ` Missing or duplicated at apps.ai.search in: ${localeCoverage.invalidLocales.join(', ')}.`
          : '';
      errors.push({
        filePath: declaration.filePath,
        message:
          `${declaration.labelKey} must exist exactly once at apps.ai.search ` +
          'in every supported locale in apps/web/src/platform/i18n/resources.ts ' +
          `(${localeCoverage.validLocaleCount}/${localeCoverage.localeCount}).` +
          invalidLocaleDetail,
      });
    }
  }

  return { ok: errors.length === 0, errors };
}
