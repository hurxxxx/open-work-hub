export const LANES = Object.freeze({
  PROTOTYPE: 'prototype',
  APP_SANDBOX: 'app-sandbox',
  SHARED_CAPABILITY: 'shared-capability',
  CORE_PLATFORM: 'core-platform',
  HARNESS_AND_POLICY: 'harness-and-policy',
  WINDOWS_ADMIN_DEV_ENV: 'windows-admin-dev-env',
});

export const LANE_LABELS = Object.freeze({
  [LANES.PROTOTYPE]: 'Prototype',
  [LANES.APP_SANDBOX]: 'App Sandbox',
  [LANES.SHARED_CAPABILITY]: 'Shared Capability',
  [LANES.CORE_PLATFORM]: 'Core Platform',
  [LANES.HARNESS_AND_POLICY]: 'Harness And Policy',
  [LANES.WINDOWS_ADMIN_DEV_ENV]: 'Windows Admin Dev Env',
});

export const LANE_RANK = Object.freeze({
  [LANES.PROTOTYPE]: 0,
  [LANES.APP_SANDBOX]: 1,
  [LANES.SHARED_CAPABILITY]: 2,
  [LANES.WINDOWS_ADMIN_DEV_ENV]: 2,
  [LANES.CORE_PLATFORM]: 3,
  [LANES.HARNESS_AND_POLICY]: 4,
});

export const DEFAULT_LIMITS = Object.freeze({
  maxDeletedFiles: 20,
  maxChangedFiles: 120,
  maxTopLevelDirectories: 5,
});

export const CORE_API_DOMAINS = new Set([
  'admin',
  'ai',
  'auth',
  'rag',
  'realtime',
  'search',
  'source_access',
]);

export const PROTECTED_SURFACES = Object.freeze({
  'harness-policy': {
    requiredLane: LANES.HARNESS_AND_POLICY,
    label: 'CI, agent rule, repository harness, or guardrail policy',
    reason: 'guardrail, CI, agent, policy, or repository harness surface',
    nextAction:
      'Route this change as Harness And Policy, or keep ordinary app work inside the app sandbox and leave harness files untouched.',
    pathPatterns: [
      /^\.gitlab-ci\.yml$/,
      /^\.gitignore$/,
      /^CODEOWNERS$/,
      /^\.github\//,
      /^\.agents\//,
      /^\.codex\//,
      /^agents\.md$/,
      /^CLAUDE\.md$/,
      /^docs\/agents\//,
      /^\.gitlab\/merge_request_templates\//,
      /^scripts\/check-[^/]+$/,
      /^scripts\/check-[^/]+\.mjs$/,
      /^scripts\/check-[^/]+\.py$/,
      /^scripts\/check-[^/]+\.sh$/,
      /^scripts\/tests\/test_check_[^/]+\.py$/,
      /^scripts\/fixtures\/app-platform-guardrails\//,
      /^scripts\/app-platform-guardrails\//,
      /^scripts\/ci\//,
      /^scripts\/(?:api-test-selection(?:\.test)?|run-affected-api-tests)\.mjs$/,
      /^scripts\/codex-review-ci\.sh$/,
      /^scripts\/configure-ci-validation-env\.sh$/,
      /^scripts\/install-codex-review-runner\.sh$/,
      /^scripts\/install-ci-light-validation-runner\.sh$/,
      /^scripts\/install-ci-validation-runner\.sh$/,
      /^scripts\/promote-ci-control-plane\.sh$/,
      /^ops\/ci\//,
      /^scripts\/web-i18n-message-checker\.mjs$/,
      /^apps\/api\/tests\/test_(?:ai_gateway_direct_call_guard|ai_registry|ai_runtime_contracts|ai_runtime_settings|openapi_contract|openapi_contract_rules|platform_adapter_registries|workspace_bootstrap|workspace_keyword_search_registry)\.py$/,
      /^apps\/worker\/tests\/test_(?:runtime_settings_contract|worker_task_registration)\.py$/,
      /^adr\//,
    ],
    codeownerPatterns: [
      '/.gitlab-ci.yml',
      '/.gitignore',
      '/CODEOWNERS',
      '/agents.md',
      '/CLAUDE.md',
      '/docs/agents/',
      '/.gitlab/merge_request_templates/',
      '/.agents/',
      '/adr/',
      '/scripts/check-*',
      '/scripts/tests/test_check_*.py',
      '/scripts/app-platform-guardrails/',
      '/scripts/fixtures/app-platform-guardrails/',
      '/scripts/ci/',
      '/scripts/api-test-selection*.mjs',
      '/scripts/run-affected-api-tests.mjs',
      '/scripts/configure-ci-validation-env.sh',
      '/scripts/install-ci-light-validation-runner.sh',
      '/scripts/install-ci-validation-runner.sh',
      '/scripts/promote-ci-control-plane.sh',
      '/scripts/web-i18n-message-checker.mjs',
      '/ops/ci/',
      '/apps/api/tests/test_ai_gateway_direct_call_guard.py',
      '/apps/api/tests/test_ai_*contract*.py',
      '/apps/api/tests/test_ai_registry.py',
      '/apps/api/tests/test_ai_runtime_settings.py',
      '/apps/api/tests/test_openapi_contract*.py',
      '/apps/api/tests/test_platform_adapter_registries.py',
      '/apps/api/tests/test_workspace_bootstrap.py',
      '/apps/worker/tests/test_runtime_settings_contract.py',
      '/apps/worker/tests/test_worker_task_registration.py',
    ],
  },
  'web-shell-platform': {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'web shell or platform module',
    reason: 'web shell or platform module',
    nextAction:
      'Move app UI into apps/web/src/app-modules/<appId>, or request Core Platform review for shell/platform changes.',
    pathPatterns: [
      /^apps\/web\/src\/app\//,
      /^apps\/web\/src\/platform\//,
      /^apps\/web\/src\/components\/layout\//,
      /^apps\/web\/src\/main\.tsx$/,
      /^apps\/web\/src\/styles\//,
      /^apps\/web\/vite\.config\.mts$/,
      /^apps\/web\/eslint\.config\.mjs$/,
      /^apps\/web\/tsconfig[^/]*\.json$/,
    ],
    codeownerPatterns: ['/apps/web/src/app/', '/apps/web/src/platform/'],
  },
  'api-core': {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'API core module',
    nextAction:
      'Move domain behavior into apps/api/src/ai_do_api/domains/<appDomain>, or request Core Platform review.',
    pathPatterns: [
      /^apps\/api\/src\/ai_do_api\/api_registry\.py$/,
      /^apps\/api\/src\/ai_do_api\/platform_extensions\.py$/,
      /^apps\/api\/src\/ai_do_api\/domains\/[^/]+\/search_(?:hooks|projection|registration)\.py$/,
    ],
    codeownerPatterns: [
      '/apps/api/src/ai_do_api/api_registry.py',
      '/apps/api/src/ai_do_api/platform_extensions.py',
      '/apps/api/src/ai_do_api/domains/*/search_*.py',
      '/apps/api/src/ai_do_api/core/',
      '/apps/api/src/ai_do_api/domains/auth/',
      '/apps/api/src/ai_do_api/domains/ai/',
    ],
  },
  'core-platform': {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'core platform surface',
    nextAction:
      'Move app-local work into the app sandbox, or request Core Platform review for repository-level changes.',
    pathPatterns: [
      /^apps\/worker\/src\/ai_do_worker\/(?:celery_app|queue_contract|runtime|settings)\.py$/,
      /^apps\/worker\/src\/ai_do_worker\/tasks\/__init__\.py$/,
    ],
    codeownerPatterns: ['/apps/worker/src/ai_do_worker/'],
  },
  contract: {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'contract or generated OpenAPI surface',
    reason: 'contract or generated API surface',
    nextAction:
      'Regenerate contracts with the approved generator and route contract changes through Core Platform review.',
    pathPatterns: [
      /^packages\/contracts\//,
      /^scripts\/generate-openapi-client\.mjs$/,
      /^apps\/api\/src\/ai_do_api\/openapi_contract\.py$/,
    ],
    codeownerPatterns: ['/packages/contracts/'],
  },
  'package-workspace': {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'package manager or workspace config',
    reason: 'package manager or workspace configuration',
    nextAction:
      'Split dependency/workspace changes from app work, or route them through Core Platform review.',
    pathPatterns: [
      /^package\.json$/,
      /^pnpm-lock\.yaml$/,
      /^pnpm-workspace\.yaml$/,
      /^nx\.json$/,
      /^tsconfig\.base\.json$/,
      /^eslint\.config\.mjs$/,
      /^apps\/api\/pyproject\.toml$/,
      /^apps\/api\/uv\.lock$/,
    ],
    codeownerPatterns: [
      '/package.json',
      '/pnpm-lock.yaml',
      '/pnpm-workspace.yaml',
      '/nx.json',
    ],
  },
  'prod-infra-runtime': {
    requiredLane: LANES.CORE_PLATFORM,
    label: 'production, infra, or runtime-separation path',
    reason: 'production, infra, or runtime-separation surface',
    nextAction:
      'Route runtime/deployment changes through Core Platform and keep dev/prod separation checks in the same change.',
    pathPatterns: [
      /^compose\./,
      /^ops\//,
      /^scripts\/prod-/,
      /^scripts\/infra-stack\.sh$/,
      /^scripts\/dev-infra\.sh$/,
      /^scripts\/check-runtime-separation\.py$/,
      /^\.env\.example$/,
    ],
    codeownerPatterns: [
      '/.env.example',
      '/compose.*.yml',
      '/ops/',
      '/scripts/prod-*',
      '/scripts/infra-stack.sh',
      '/scripts/dev-infra.sh',
      '/scripts/check-runtime-separation.py',
    ],
  },
  'shared-capability': {
    requiredLane: LANES.SHARED_CAPABILITY,
    label: 'shared UI/API capability surface',
    reason: 'shared UI/API capability surface',
    nextAction:
      'Keep code app-local, or promote the reusable piece through the Shared Capability lane.',
    pathPatterns: [
      /^apps\/web\/src\/components\//,
      /^apps\/web\/src\/lib\//,
      /^packages\/ui\//,
    ],
    codeownerPatterns: ['/packages/ui/'],
  },
});

export const CLASSIFICATION_SURFACE_ORDER = Object.freeze([
  'harness-policy',
  'contract',
  'package-workspace',
  'prod-infra-runtime',
  'web-shell-platform',
  'api-core',
  'core-platform',
  'shared-capability',
]);

export const WINDOWS_DEV_PATH_PATTERNS = [
  /^scripts\/dev-windows.*\.ps1$/,
  /^docs\/reference\/setup-windows\.md$/,
  /^docs\/current\/windows/i,
  /^docs\/windows/i,
];

export const APP_TEST_PATH_PATTERNS = [
  /^apps\/web\/e2e\//,
  /^apps\/api\/tests\/test_[a-z0-9_]+\.py$/,
  /^apps\/api\/tests\/fixtures\//,
  /^apps\/worker\/tests\/apps\/[a-z0-9_-]+\//,
];

export const ALEMBIC_VERSION_PATTERN =
  /^apps\/api\/alembic\/versions\/[^/]+\.py$/;

export const DESTRUCTIVE_MIGRATION_PATTERNS = [
  /\bop\.drop_table\s*\(/,
  /\bop\.drop_column\s*\(/,
  /\bbatch_op\.drop_column\s*\(/,
  /\bbatch_op\.drop_index\s*\(/,
  /\bop\.drop_index\s*\(/,
  /\bop\.execute\s*\(\s*["'][^"']*\b(?:drop|truncate|delete\s+from)\b/i,
];

export const SHARED_TABLE_PATTERN =
  /\b(?:users|workspaces|workspace_[a-z0-9_]+|auth_[a-z0-9_]+|audit_logs|llm_[a-z0-9_]+|ai_[a-z0-9_]+|rag_[a-z0-9_]+|search_[a-z0-9_]+|alembic_version)\b/;

export const WINDOWS_GUARDRAIL_FILES = [
  'scripts/dev-windows.ps1',
  'scripts/dev-windows-bootstrap.ps1',
  'scripts/dev-windows-fetch-env.ps1',
  'docs/reference/setup-windows.md',
];

export const WINDOWS_FORBIDDEN_PATTERNS = [
  {
    pattern: /\/projects\/ai-do\/prod|\\projects\\ai-do\\prod/i,
    label: 'production checkout path',
  },
  {
    pattern: /\bai-do-prod\b/i,
    label: 'production runtime/container/service name',
  },
  {
    pattern: /\b(?:prod-systemd|prod-deploy|infra:prod|pnpm\s+prod:)/i,
    label: 'production deployment command',
  },
  {
    pattern: /\bAI_DO_[A-Z0-9_]*PROD[A-Z0-9_]*\b/,
    label: 'production environment variable',
  },
  {
    pattern: /\bAI_DO_API_ENVIRONMENT\s*=\s*["']?production\b/i,
    label: 'production API environment',
  },
  {
    pattern: /--port["',\s]+8000\b|http:\/\/127\.0\.0\.1:8000\b/i,
    label: 'production API port 8000',
  },
  {
    pattern: /\b5432\b/,
    label: 'default Postgres port 5432',
  },
  {
    pattern: /:(?:80|443)\b/,
    label: 'public HTTP(S) production port',
  },
];

export const CODEOWNERS_PATH = 'CODEOWNERS';

export const CODEOWNERS_REQUIRED_RULES = Object.freeze(
  Object.values(PROTECTED_SURFACES).flatMap(
    (surface) => surface.codeownerPatterns ?? [],
  ),
);

export const GUARDRAIL_ARTIFACT_PATH = 'app-platform-guardrails.json';
