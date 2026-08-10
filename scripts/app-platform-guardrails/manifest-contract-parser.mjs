const STRING_ARRAY_FIELDS = [
  'permissions',
  'aiCapabilities',
  'writeAuditActions',
  'appLocalTests',
];

function isWhitespace(char) {
  return /\s/.test(char);
}

function isIdentifierStart(char) {
  return /[$A-Z_a-z]/.test(char);
}

function isIdentifierChar(char) {
  return /[$0-9A-Z_a-z]/.test(char);
}

function skipQuotedString(source, startIndex, quote) {
  let escaped = false;
  for (let index = startIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (escaped) {
      escaped = false;
    } else if (char === '\\') {
      escaped = true;
    } else if (char === quote) {
      return index + 1;
    }
  }

  return source.length;
}

function skipTemplateLiteral(source, startIndex) {
  return skipQuotedString(source, startIndex, '`');
}

function skipLineComment(source, startIndex) {
  const endIndex = source.indexOf('\n', startIndex + 2);
  return endIndex < 0 ? source.length : endIndex + 1;
}

function skipBlockComment(source, startIndex) {
  const endIndex = source.indexOf('*/', startIndex + 2);
  return endIndex < 0 ? source.length : endIndex + 2;
}

function skipIgnorable(source, startIndex) {
  let index = startIndex;
  while (index < source.length) {
    const char = source[index];
    const nextChar = source[index + 1];
    if (isWhitespace(char)) {
      index += 1;
    } else if (char === '/' && nextChar === '/') {
      index = skipLineComment(source, index);
    } else if (char === '/' && nextChar === '*') {
      index = skipBlockComment(source, index);
    } else {
      return index;
    }
  }

  return index;
}

function skipScannerIgnored(source, startIndex) {
  const char = source[startIndex];
  const nextChar = source[startIndex + 1];
  if (char === '"' || char === "'") {
    return skipQuotedString(source, startIndex, char);
  }
  if (char === '`') {
    return skipTemplateLiteral(source, startIndex);
  }
  if (char === '/' && nextChar === '/') {
    return skipLineComment(source, startIndex);
  }
  if (char === '/' && nextChar === '*') {
    return skipBlockComment(source, startIndex);
  }

  return startIndex;
}

function extractBalancedBlock(source, startIndex, openChar, closeChar) {
  const openIndex = source.indexOf(openChar, startIndex);
  if (openIndex < 0) {
    return null;
  }

  let depth = 0;
  for (let index = openIndex; index < source.length; index += 1) {
    const skippedIndex = skipScannerIgnored(source, index);
    if (skippedIndex !== index) {
      index = skippedIndex - 1;
      continue;
    }

    const char = source[index];
    if (char === openChar) {
      depth += 1;
    } else if (char === closeChar) {
      depth -= 1;
      if (depth === 0) {
        return source.slice(openIndex, index + 1);
      }
    }
  }

  return null;
}

function readObjectKey(source, startIndex) {
  const char = source[startIndex];
  if (char === '"' || char === "'") {
    const endIndex = skipQuotedString(source, startIndex, char);
    if (endIndex > source.length || source[endIndex - 1] !== char) {
      return null;
    }
    return {
      key: source.slice(startIndex + 1, endIndex - 1),
      endIndex,
    };
  }

  if (!isIdentifierStart(char)) {
    return null;
  }

  let endIndex = startIndex + 1;
  while (endIndex < source.length && isIdentifierChar(source[endIndex])) {
    endIndex += 1;
  }

  return {
    key: source.slice(startIndex, endIndex),
    endIndex,
  };
}

function findTopLevelDelimiter(source, startIndex, delimiters) {
  const closerStack = [];
  const pairs = new Map([
    ['{', '}'],
    ['[', ']'],
    ['(', ')'],
  ]);
  const closers = new Set(pairs.values());

  for (let index = startIndex; index < source.length; index += 1) {
    const skippedIndex = skipScannerIgnored(source, index);
    if (skippedIndex !== index) {
      index = skippedIndex - 1;
      continue;
    }

    const char = source[index];
    if (closerStack.length === 0 && delimiters.has(char)) {
      return index;
    }

    if (pairs.has(char)) {
      closerStack.push(pairs.get(char));
    } else if (closers.has(char) && closerStack.at(-1) === char) {
      closerStack.pop();
    }
  }

  return source.length;
}

function parseObjectFields(objectBlock) {
  const fields = new Map();
  let index = 1;

  while (index < objectBlock.length - 1) {
    index = skipIgnorable(objectBlock, index);
    if (objectBlock[index] === ',') {
      index += 1;
      continue;
    }
    if (objectBlock[index] === '}') {
      break;
    }

    const key = readObjectKey(objectBlock, index);
    if (!key) {
      index = findTopLevelDelimiter(objectBlock, index, new Set([',', '}']));
      continue;
    }

    index = skipIgnorable(objectBlock, key.endIndex);
    if (objectBlock[index] !== ':') {
      index = findTopLevelDelimiter(objectBlock, index, new Set([',', '}']));
      continue;
    }

    const valueStart = skipIgnorable(objectBlock, index + 1);
    const valueEnd = findTopLevelDelimiter(
      objectBlock,
      valueStart,
      new Set([',', '}']),
    );
    fields.set(key.key, {
      source: objectBlock.slice(valueStart, valueEnd).trim(),
      sourceStart: valueStart,
      sourceEnd: valueEnd,
    });
    index = valueEnd;
  }

  return fields;
}

function parseStringLiteral(valueSource) {
  const source = valueSource.trim();
  const quote = source[0];
  if ((quote !== '"' && quote !== "'") || source[source.length - 1] !== quote) {
    return null;
  }

  return source.slice(1, -1);
}

function parseStringField(fields, fieldName) {
  const field = fields.get(fieldName);
  if (!field) {
    return { present: false, kind: 'missing', value: null };
  }

  const value = parseStringLiteral(field.source);
  return {
    present: true,
    kind: value === null ? 'invalid' : 'string',
    value,
  };
}

function parseNullableStringField(fields, fieldName) {
  const field = fields.get(fieldName);
  if (!field) {
    return { present: false, kind: 'missing', value: null };
  }

  if (field.source === 'null') {
    return { present: true, kind: 'null', value: null };
  }

  const value = parseStringLiteral(field.source);
  return {
    present: true,
    kind: value === null ? 'invalid' : 'string',
    value,
  };
}

function parseArrayElements(arrayBlock) {
  const values = [];
  let index = 1;

  while (index < arrayBlock.length - 1) {
    index = skipIgnorable(arrayBlock, index);
    if (arrayBlock[index] === ',') {
      index += 1;
      continue;
    }
    if (arrayBlock[index] === ']') {
      break;
    }

    const valueEnd = findTopLevelDelimiter(
      arrayBlock,
      index,
      new Set([',', ']']),
    );
    const valueSource = arrayBlock.slice(index, valueEnd).trim();
    if (valueSource) {
      const value = parseStringLiteral(valueSource);
      if (value === null) {
        return null;
      }
      values.push(value);
    }
    index = valueEnd;
  }

  return values;
}

function parseStringArrayField(fields, fieldName) {
  const field = fields.get(fieldName);
  if (!field) {
    return { present: false, kind: 'missing', source: null, values: [] };
  }

  if (!field.source.startsWith('[')) {
    return {
      present: true,
      kind: 'invalid',
      source: field.source,
      values: null,
    };
  }

  const arrayBlock = extractBalancedBlock(field.source, 0, '[', ']');
  if (!arrayBlock || arrayBlock.length !== field.source.length) {
    return {
      present: true,
      kind: 'invalid',
      source: field.source,
      values: null,
    };
  }

  const values = parseArrayElements(arrayBlock);
  return {
    present: true,
    kind: values === null ? 'invalid' : 'array',
    source: field.source,
    values,
  };
}

function parseObjectFieldValue(fields, fieldName) {
  const field = fields.get(fieldName);
  if (!field || !field.source.startsWith('{')) {
    return null;
  }

  const objectBlock = extractBalancedBlock(field.source, 0, '{', '}');
  return objectBlock?.length === field.source.length ? objectBlock : null;
}

function parseArrayPresence(fields, fieldName) {
  const field = fields.get(fieldName);
  return {
    present: Boolean(field),
    isArray: Boolean(field && field.source.startsWith('[')),
  };
}

function parseContractFields(contractBlock) {
  const fields = parseObjectFields(contractBlock);
  const contract = {
    present: true,
    owner: parseStringField(fields, 'owner'),
    apiDomain: parseNullableStringField(fields, 'apiDomain'),
    workspaceApiPrefixes: parseStringArrayField(fields, 'workspaceApiPrefixes'),
    workspaceSearchSource: { present: fields.has('workspaceSearchSource') },
  };

  for (const fieldName of STRING_ARRAY_FIELDS) {
    contract[fieldName] = parseStringArrayField(fields, fieldName);
  }

  return contract;
}

function findManifestObject(source) {
  for (let index = 0; index < source.length; index += 1) {
    const skippedIndex = skipScannerIgnored(source, index);
    if (skippedIndex !== index) {
      index = skippedIndex - 1;
      continue;
    }

    if (source[index] !== '{') {
      continue;
    }

    const objectBlock = extractBalancedBlock(source, index, '{', '}');
    if (!objectBlock) {
      return {
        fields: new Map(),
        diagnostics: [{ message: 'manifest object literal is not balanced.' }],
      };
    }

    const fields = parseObjectFields(objectBlock);
    if (
      fields.has('appBarItem') ||
      fields.has('moduleKind') ||
      fields.has('contract') ||
      (fields.has('navItems') && fields.has('workspaceRoutePaths'))
    ) {
      return { fields, diagnostics: [] };
    }

    index += objectBlock.length - 1;
  }

  return { fields: new Map(), diagnostics: [] };
}

export function parseManifestContractSource(source) {
  const manifest = findManifestObject(source);
  const diagnostics = [...manifest.diagnostics];
  const appBarItemBlock = parseObjectFieldValue(manifest.fields, 'appBarItem');
  const appBarItemFields = appBarItemBlock
    ? parseObjectFields(appBarItemBlock)
    : new Map();
  const contractField = manifest.fields.get('contract');
  let contractBlock = null;

  if (contractField && contractField.source.startsWith('{')) {
    contractBlock = extractBalancedBlock(contractField.source, 0, '{', '}');
    if (
      !contractBlock ||
      contractBlock.length !== contractField.source.length
    ) {
      diagnostics.push({ message: 'contract object literal is not balanced.' });
    }
  } else if (contractField) {
    diagnostics.push({ message: 'contract must be an object literal.' });
  }

  const contract = {
    appBarItemId: parseStringField(appBarItemFields, 'id'),
    moduleKind: parseStringField(manifest.fields, 'moduleKind'),
    moduleId: parseStringField(manifest.fields, 'moduleId'),
    workspaceRoutePaths: parseArrayPresence(
      manifest.fields,
      'workspaceRoutePaths',
    ),
    navItems: parseArrayPresence(manifest.fields, 'navItems'),
    contract: contractBlock
      ? parseContractFields(contractBlock)
      : { present: false },
  };

  return { contract, diagnostics };
}

function pushManifestError(errors, manifestPath, message) {
  errors.push({ manifestPath, message });
}

function validateManifestContractFields(
  manifestContract,
  { dynamicStringArrayFields = new Set(), errors, manifestPath, pathExists },
) {
  if (!manifestContract?.present) {
    pushManifestError(errors, manifestPath, 'contract is required.');
    return;
  }

  if (manifestContract.workspaceSearchSource?.present) {
    pushManifestError(
      errors,
      manifestPath,
      'contract.workspaceSearchSource is forbidden. Register SearchEntityAdapter in domains/<domain>/search_projection.py and consume workspace bootstrap.',
    );
  }

  if (
    !manifestContract.owner.present ||
    manifestContract.owner.kind !== 'string'
  ) {
    pushManifestError(errors, manifestPath, 'contract.owner is required.');
  }

  const apiDomain = manifestContract.apiDomain;
  if (
    !apiDomain.present ||
    (apiDomain.kind !== 'string' && apiDomain.kind !== 'null')
  ) {
    pushManifestError(
      errors,
      manifestPath,
      'contract.apiDomain is required and must be a string or null.',
    );
  } else if (
    apiDomain.value !== null &&
    !/^[a-z][a-z0-9_]*$/.test(apiDomain.value)
  ) {
    pushManifestError(
      errors,
      manifestPath,
      `contract.apiDomain must be snake_case or null, got "${apiDomain.value}".`,
    );
  } else if (
    apiDomain.value !== null &&
    !pathExists(`apps/api/src/open_alm_api/domains/${apiDomain.value}`)
  ) {
    pushManifestError(
      errors,
      manifestPath,
      `contract.apiDomain does not match an API domain directory: ${apiDomain.value}`,
    );
  }

  for (const fieldName of STRING_ARRAY_FIELDS) {
    const field = manifestContract[fieldName];
    if (!field.present) {
      pushManifestError(
        errors,
        manifestPath,
        `contract.${fieldName} is required.`,
      );
    } else if (
      !Array.isArray(field.values) &&
      !(
        dynamicStringArrayFields.has(fieldName) &&
        isAllowedExtensionHostDynamicStringArraySource(field.source)
      )
    ) {
      pushManifestError(
        errors,
        manifestPath,
        `contract.${fieldName} must be a string array.`,
      );
    }
  }

  const appLocalTests = manifestContract.appLocalTests;
  if (appLocalTests.present && Array.isArray(appLocalTests.values)) {
    if (appLocalTests.values.length === 0) {
      pushManifestError(
        errors,
        manifestPath,
        'contract.appLocalTests must name at least one test or fixture.',
      );
    }
    for (const testPath of appLocalTests.values) {
      if (!pathExists(testPath)) {
        pushManifestError(
          errors,
          manifestPath,
          `contract.appLocalTests path does not exist: ${testPath}`,
        );
      }
    }
  }

  for (const fieldName of [
    'permissions',
    'aiCapabilities',
    'writeAuditActions',
  ]) {
    const field = manifestContract[fieldName];
    if (!Array.isArray(field.values)) {
      continue;
    }
    for (const value of field.values) {
      if (!/^[a-z][a-z0-9_.-]*$/.test(value)) {
        pushManifestError(
          errors,
          manifestPath,
          `contract.${fieldName} contains invalid token: ${value}`,
        );
      }
    }
  }
}

function isAllowedExtensionHostDynamicStringArraySource(source) {
  return /^(?:unique\()?extension[A-Z][A-Za-z0-9]*(?:\))?$/.test(
    source?.trim() ?? '',
  );
}

function validateFeatureManifestContract(
  contract,
  {
    appId,
    manifestPath = `apps/web/src/app-modules/${appId}/manifest.ts`,
    pathExists = () => false,
  } = {},
) {
  const errors = [];
  const moduleKind = contract?.moduleKind;
  if (!moduleKind?.present || moduleKind.kind !== 'string') {
    pushManifestError(errors, manifestPath, 'moduleKind is required.');
  } else if (moduleKind.value !== 'feature') {
    pushManifestError(
      errors,
      manifestPath,
      `moduleKind must be "feature", got "${moduleKind.value}".`,
    );
  }

  const moduleId = contract?.moduleId;
  if (!moduleId?.present || moduleId.kind !== 'string') {
    pushManifestError(errors, manifestPath, 'moduleId is required.');
  } else if (moduleId.value !== appId) {
    pushManifestError(
      errors,
      manifestPath,
      `moduleId must match folder app id "${appId}", got "${moduleId.value}".`,
    );
  }

  if (contract?.appBarItemId?.present) {
    pushManifestError(
      errors,
      manifestPath,
      'feature manifests must not declare appBarItem.',
    );
  }
  if (contract?.workspaceRoutePaths?.present) {
    pushManifestError(
      errors,
      manifestPath,
      'feature manifests must not declare workspaceRoutePaths.',
    );
  }
  if (contract?.navItems?.present) {
    pushManifestError(
      errors,
      manifestPath,
      'feature manifests must not declare navItems.',
    );
  }

  validateManifestContractFields(contract?.contract, {
    errors,
    manifestPath,
    pathExists,
  });

  return errors;
}

export function validateManifestContract(
  contract,
  {
    appId,
    manifestPath = `apps/web/src/app-modules/${appId}/manifest.ts`,
    pathExists = () => false,
  } = {},
) {
  const errors = [];
  const isExtensionHostManifest =
    contract?.contract?.owner?.kind === 'string' &&
    contract.contract.owner.value === 'customer-extension-host';
  if (contract?.moduleKind?.present || contract?.moduleId?.present) {
    return validateFeatureManifestContract(contract, {
      appId,
      manifestPath,
      pathExists,
    });
  }

  if (
    !contract?.appBarItemId?.present ||
    contract.appBarItemId.kind !== 'string'
  ) {
    pushManifestError(errors, manifestPath, 'appBarItem.id is required.');
  } else if (contract.appBarItemId.value !== appId) {
    pushManifestError(
      errors,
      manifestPath,
      `appBarItem.id must match folder app id "${appId}", got "${contract.appBarItemId.value}".`,
    );
  }

  if (!contract?.workspaceRoutePaths?.isArray) {
    pushManifestError(errors, manifestPath, 'workspaceRoutePaths is required.');
  }
  if (!contract?.navItems?.isArray) {
    pushManifestError(errors, manifestPath, 'navItems is required.');
  }

  validateManifestContractFields(contract?.contract, {
    dynamicStringArrayFields: isExtensionHostManifest
      ? new Set(['aiCapabilities', 'writeAuditActions', 'appLocalTests'])
      : new Set(),
    errors,
    manifestPath,
    pathExists,
  });

  return errors;
}
