import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { assertProductionAppEnv, parseEnvText } from './prod-app-config.mjs';
import { cleanup, diskHeadroom, retirementPlan } from './docker-storage.mjs';

const oldImage = (id, tags, extra = {}) => ({
  Id: id,
  RepoTags: tags,
  Created: '2020-01-01T00:00:00Z',
  Config: { Labels: { 'org.opencontainers.image.title': 'Open Work Hub' } },
  ...extra,
});
const appTag = (id) => `open-work-hub-app:${id.repeat(12)}`;

test('build command substitution stops on storage, build or image-verification failure', async () => {
  const script = await readFile(
    new URL('./prod-app.sh', import.meta.url),
    'utf8',
  );
  const build = script.slice(
    script.indexOf('build_release_image()'),
    script.indexOf('verify_release_image()'),
  );
  for (const failed of ['storage', 'build', 'verify']) {
    const result = spawnSync(
      'bash',
      [
        '-c',
        `
      set -euo pipefail
      ROOT_DIR=/synthetic ENV_FILE=/synthetic/env IMAGE_REPOSITORY=synthetic
      node() { return ${failed === 'storage' ? 1 : 0}; }
      git() { printf 'aaaaaaaaaaaa'; }
      docker() { return ${failed === 'build' ? 1 : 0}; }
      verify_release_image() { return ${failed === 'verify' ? 1 : 0}; }
      ${build}
      image="$(build_release_image)"
      exit 99
    `,
      ],
      { encoding: 'utf8', env: { PATH: process.env.PATH } },
    );
    assert.equal(result.status, 1, `${failed}: ${result.stderr}`);
    assert.equal(result.stdout, '');
  }
});
const storageImages = () => [
  oldImage('current', ['open-work-hub-app:prod', appTag('a')]),
  oldImage('previous', ['open-work-hub-app:prod-previous', appTag('b')]),
  oldImage('ci', [
    'open-work-hub-validation:node22-python312',
    'open-work-hub-validation:redis64-impact-release',
  ]),
  oldImage('retired', [appTag('c')]),
];

test('storage requires both absolute and proportional disk headroom', () => {
  const stats = (available, total) => ({
    bavail: available,
    blocks: total,
    bsize: 1024 ** 3,
  });
  assert.equal(diskHeadroom(stats(20, 100)).ok, true);
  assert.equal(diskHeadroom(stats(15, 100)).ok, true);
  assert.equal(diskHeadroom(stats(14, 50)).ok, false);
  assert.equal(diskHeadroom(stats(20, 200)).ok, false);
  assert.equal(diskHeadroom(stats(20, 0)).ok, false);
  assert.equal(diskHeadroom(stats(NaN, 100)).ok, false);
});

test('retention preserves current, rollback, CI, container refs, recent and unknown images', () => {
  const images = [
    ...storageImages(),
    oldImage('running', [appTag('d')]),
    oldImage('stopped', [appTag('e')]),
    oldImage('manual', [
      appTag('f'),
      'open-work-hub-app:keep-for-investigation',
    ]),
    oldImage('foreign', ['another-project:old']),
    oldImage('unlabeled', [appTag('1')], { Config: {} }),
    oldImage('recent', [appTag('2')], { Created: new Date().toISOString() }),
    oldImage('undated', [appTag('3')], { Created: 'unknown' }),
    oldImage('dangling', []),
    oldImage('old-ci', ['open-work-hub-validation:deps-aaaaaaaaaaaa']),
  ];
  assert.deepEqual(
    retirementPlan(images, [{ Image: 'running' }, { Image: 'stopped' }]).map(
      (i) => i.id,
    ),
    ['retired', 'old-ci'],
  );
  assert.deepEqual(retirementPlan([images[3]], []), []);
});

test('cleanup is read-only by default and uses only scoped non-force image removal', () => {
  const state = { images: storageImages(), containers: [] };
  const calls = [];
  const options = { inspect: () => state, invoke: (args) => calls.push(args) };
  cleanup(options);
  assert.deepEqual(calls, []);
  cleanup({ ...options, apply: true });
  assert.deepEqual(calls, [
    ['image', 'rm', '--no-prune', appTag('c')],
    [
      'image',
      'prune',
      '--force',
      '--filter',
      'label=io.open-work-hub.build-cache=true',
      '--filter',
      'until=48h',
    ],
    [
      'image',
      'prune',
      '--force',
      '--filter',
      'label=org.opencontainers.image.title=Open Work Hub',
      '--filter',
      'until=48h',
    ],
  ]);
});

test('cleanup stops if a candidate gains a reference or tag after inspection', () => {
  for (const change of ['container', 'tag']) {
    let count = 0;
    assert.throws(
      () =>
        cleanup({
          apply: true,
          inspect: () => {
            const state = { images: storageImages(), containers: [] };
            if (count++ > 0) {
              if (change === 'container')
                state.containers.push({ Image: 'retired' });
              else
                state.images[3].RepoTags.push(
                  'open-work-hub-app:prod-previous',
                );
            }
            return state;
          },
          invoke: () =>
            assert.fail('changed references must prevent any deletion'),
        }),
      /references changed/,
    );
  }
});

test('production dependency layers exclude revision churn, uv cache and local test artifacts', async () => {
  const dockerfile = await readFile(
    new URL('../ops/app/Dockerfile', import.meta.url),
    'utf8',
  );
  const ignore = await readFile(
    new URL('../.dockerignore', import.meta.url),
    'utf8',
  );
  const [buildStages, runtime] = dockerfile.split('AS runtime');
  assert.equal(
    (buildStages.match(/uv sync --no-cache --frozen/g) ?? []).length,
    4,
  );
  assert.ok(
    buildStages.indexOf('ARG OPEN_WORK_HUB_BENTO_SERVER_URL') >
      buildStages.indexOf('RUN pnpm install'),
  );
  assert.equal(
    (buildStages.match(/io.open-work-hub.build-cache="true"/g) ?? []).length,
    2,
  );
  assert.ok(
    runtime.indexOf('ARG OPEN_WORK_HUB_BUILD_REVISION') >
      runtime.lastIndexOf('COPY '),
  );
  assert.ok(
    runtime.indexOf('ARG OPEN_WORK_HUB_BUILD_REVISION') >
      runtime.lastIndexOf('RUN '),
  );
  assert.match(
    runtime,
    /org.opencontainers.image.revision="\$\{OPEN_WORK_HUB_BUILD_REVISION\}"/,
  );
  assert.doesNotMatch(runtime, /io.open-work-hub.build-cache/);
  for (const entry of [
    '.runtime',
    '.dev',
    '**/test-results',
    '**/playwright-report',
    '**/blob-report',
    '**/celerybeat-schedule*',
    '**/celerybeat-heartbeat',
  ]) {
    assert.ok(
      ignore.split('\n').includes(entry),
      `missing Docker context exclusion: ${entry}`,
    );
  }
  const release = await readFile(
    new URL('./prod-app.sh', import.meta.url),
    'utf8',
  );
  const build = release.slice(
    release.indexOf('build_release_image()'),
    release.indexOf('verify_release_image()'),
  );
  assert.ok(
    build.indexOf('docker-storage.mjs" check') < build.indexOf('docker build'),
  );
  const deploy = release.slice(
    release.indexOf('deploy()'),
    release.indexOf('COMMAND='),
  );
  assert.match(deploy, /cleanup --apply[\s\S]+build_release_image/);
  assert.match(deploy, /passed public smoke[\s\S]+cleanup --apply/);
});

function validEnv(overrides = {}) {
  return new Map(
    Object.entries({
      OPENROUTER_API_KEY: 'sk-or-v1-production-test-key',
      OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN: '0',
      OPEN_WORK_HUB_API_DEV_PORT: '8001',
      OPEN_WORK_HUB_API_ENVIRONMENT: 'production',
      OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED: 'true',
      OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT: 'false',
      OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY:
        'production-test-content-signing-key',
      OPEN_WORK_HUB_APP_BIND_HOST: '127.0.0.1',
      OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS: '127.0.0.1',
      OPEN_WORK_HUB_APP_PORT: '8000',
      OPEN_WORK_HUB_APP_PUBLIC_URL: 'https://prod.example.com',
      OPEN_WORK_HUB_BENTO_BIND_HOST: '127.0.0.1',
      OPEN_WORK_HUB_BENTO_PORT: '18084',
      OPEN_WORK_HUB_BENTO_SERVER_URL: 'https://bento.example.com',
      OPEN_WORK_HUB_DRAWIO_PORT: '18083',
      OPEN_WORK_HUB_ENV_PROFILE: 'prod',
      OPEN_WORK_HUB_HERMES_API_KEY: 'production-hermes-runtime-secret-00000001',
      OPEN_WORK_HUB_HERMES_ENABLED: 'true',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_BASE_URL: 'http://127.0.0.1:9119',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_PORT: '9119',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN:
        'production-hermes-management-secret-0001',
      OPEN_WORK_HUB_HERMES_MCP_SERVER_URL:
        'http://127.0.0.1:8000/api/v1/internal/hermes/mcp',
      OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET:
        'production-hermes-mcp-secret-0000000001',
      OPEN_WORK_HUB_HERMES_PROFILE_CLONE_SOURCE: 'default',
      OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL: 'http://127.0.0.1:8642',
      OPEN_WORK_HUB_HERMES_RUNTIME_PORT: '8642',
      OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_BASE_URL: 'http://127.0.0.1:8765',
      OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT: '8765',
      OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE: 'prod',
      OPEN_WORK_HUB_INFRA_NGINX_PORT: '14200',
      OPEN_WORK_HUB_OPF_ENABLED: 'true',
      OPEN_WORK_HUB_OPF_REQUIRED: 'true',
      OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:18081',
      OPEN_WORK_HUB_WEB_DEV_PORT: '4200',
      ...overrides,
    }),
  );
}

test('parses dotenv assignments without evaluating shell syntax', () => {
  const values = parseEnvText(`
    # comment
    export OPEN_WORK_HUB_ENV_PROFILE=prod
    OPEN_WORK_HUB_APP_PUBLIC_URL="https://prod.example.com"
    ignored shell text
  `);
  assert.equal(values.get('OPEN_WORK_HUB_ENV_PROFILE'), 'prod');
  assert.equal(
    values.get('OPEN_WORK_HUB_APP_PUBLIC_URL'),
    'https://prod.example.com',
  );
  assert.equal(values.has('ignored shell text'), false);
});

test('accepts a separated production runtime configuration', () => {
  const config = assertProductionAppEnv(validEnv());
  assert.equal(config.appPort, 8000);
  assert.equal(config.bentoBindHost, '127.0.0.1');
  assert.equal(config.bentoServerUrl.href, 'https://bento.example.com/');
  assert.equal(config.hermesRuntimeBaseUrl.href, 'http://127.0.0.1:8642/');
  assert.equal(
    config.hermesTerminalBrokerBaseUrl.href,
    'http://127.0.0.1:8765/',
  );
  assert.equal(config.hermesTerminalBrokerPort, 8765);
  assert.equal(config.publicBaseUrl.href, 'https://prod.example.com/');
});

test('requires an exact private or loopback Bento IPv4 bind address', () => {
  for (const value of [
    '',
    '0.0.0.0',
    '::',
    '::1',
    'fd00::1',
    '203.0.113.10',
    'proxy.internal',
  ]) {
    assert.throws(
      () =>
        assertProductionAppEnv(
          validEnv({ OPEN_WORK_HUB_BENTO_BIND_HOST: value }),
        ),
      /exact private or loopback IPv4 address/,
    );
  }

  for (const value of ['10.20.30.40', '172.16.0.1', '192.168.1.10']) {
    assert.equal(
      assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_BENTO_BIND_HOST: value }))
        .bentoBindHost,
      value,
    );
  }
});

test('rejects development access and port collisions', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN: '1' }),
      ),
    /ALLOW_DEV_ADMIN_LOGIN/,
  );
  assert.throws(
    () => assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PORT: '4200' })),
    /WEB_DEV_PORT/,
  );
  assert.throws(
    () => assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PORT: '18084' })),
    /BENTO_PORT/,
  );
});

test('requires a credential-free HTTPS public origin', () => {
  for (const value of [
    '',
    'http://prod.example.com',
    'https://localhost:8000',
    'https://user:password@prod.example.com',
  ]) {
    assert.throws(() =>
      assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PUBLIC_URL: value })),
    );
  }
});

test('requires a separate credential-free HTTPS Bento origin', () => {
  for (const value of [
    '',
    'http://bento.example.com',
    'https://localhost:18084',
    'https://user:password@bento.example.com',
    'https://prod.example.com',
  ]) {
    assert.throws(() =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_BENTO_SERVER_URL: value }),
      ),
    );
  }
});

test('rejects unsafe production secrets and proxy trust', () => {
  for (const value of [
    '',
    'dev-content-grant-signing-key',
    'short',
    'a'.repeat(31),
    `development-${'a'.repeat(32)}`,
    `CHANGE_ME-${'a'.repeat(32)}`,
  ]) {
    assert.throws(
      () =>
        assertProductionAppEnv(
          validEnv({ OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY: value }),
        ),
      /CONTENT_GRANT_SIGNING_KEY/,
    );
  }
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS: '*' }),
      ),
    /exact proxy IP addresses/,
  );
});

test('requires a separate loopback privacy-filter origin', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:8000',
        }),
      ),
    /must not collide/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'https://opf.example.com',
        }),
      ),
    /loopback HTTP origin/,
  );
});

test('requires isolated production Hermes credentials', () => {
  for (const [key, value] of [
    ['OPENROUTER_API_KEY', 'short'],
    ['OPEN_WORK_HUB_HERMES_API_KEY', 'change-me'],
    ['OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN', 'short'],
    ['OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET', 'dev-secret'],
  ]) {
    assert.throws(() => assertProductionAppEnv(validEnv({ [key]: value })));
  }
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN:
            'production-hermes-runtime-secret-00000001',
        }),
      ),
    /must be distinct/,
  );
});

test('accepts Hermes with administrator-managed providers and no legacy OpenRouter key', () => {
  assert.doesNotThrow(() =>
    assertProductionAppEnv(validEnv({ OPENROUTER_API_KEY: '' })),
  );
});

test('requires loopback Hermes endpoints on their declared ports', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL: 'http://0.0.0.0:8642',
        }),
      ),
    /loopback HTTP endpoint/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_MCP_SERVER_URL:
            'http://127.0.0.1:8000/api/v1/tools/mcp',
        }),
      ),
    /internal Hermes MCP endpoint/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_BASE_URL:
            'http://127.0.0.1:8766',
        }),
      ),
    /Hermes Terminal broker port/,
  );
});

test('worker healthcheck uses the container hostname without spawning hostname', async () => {
  const composeText = await readFile(
    new URL('../ops/compose/open-work-hub-prod.app.yml', import.meta.url),
    'utf8',
  );
  assert.match(composeText, /--destination "prod-worker@\$\$\{HOSTNAME\}"/);
  assert.doesNotMatch(composeText, /\$\$\(hostname\)/);
});

test('production compose does not add a second ingress proxy', async () => {
  const [composeText, releaseScript] = await Promise.all([
    readFile(
      new URL('../ops/compose/open-work-hub-prod.app.yml', import.meta.url),
      'utf8',
    ),
    readFile(new URL('./prod-app.sh', import.meta.url), 'utf8'),
  ]);
  assert.doesNotMatch(composeText, /open-work-hub-edge|ops\/edge/);
  assert.match(releaseScript, /--remove-orphans/);
});

test('production image build embeds the validated Bento public URL', async () => {
  const [dockerfile, releaseScript] = await Promise.all([
    readFile(new URL('../ops/app/Dockerfile', import.meta.url), 'utf8'),
    readFile(new URL('./prod-app.sh', import.meta.url), 'utf8'),
  ]);
  assert.match(dockerfile, /ARG OPEN_WORK_HUB_BENTO_SERVER_URL/);
  assert.match(
    dockerfile,
    /OPEN_WORK_HUB_BENTO_SERVER_URL="\$\{OPEN_WORK_HUB_BENTO_SERVER_URL\}"/,
  );
  assert.match(
    releaseScript,
    /--build-arg "OPEN_WORK_HUB_BENTO_SERVER_URL=\$bento_server_url"/,
  );
});

test('production runtime checks the fixed terminal broker port before mutation', async () => {
  const releaseScript = await readFile(
    new URL('./prod-app.sh', import.meta.url),
    'utf8',
  );
  assert.match(releaseScript, /require_terminal_broker_port_available/);
  assert.match(releaseScript, /refusing before build or migration/);
  assert.match(releaseScript, /expected_binding" == "127\.0\.0\.1:\$port"/);
});

for (const namespace of [
  undefined,
  '',
  ' ',
  'dev',
  'local',
  'Prod',
  '-prod',
  'prod/team',
  'prod_team',
  'p'.repeat(33),
]) {
  test(`production rejects unsafe Hermes resource namespace ${JSON.stringify(namespace)}`, () => {
    assert.throws(
      () =>
        assertProductionAppEnv(
          validEnv({
            OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE: namespace,
          }),
        ),
      /OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE/,
    );
  });
}

for (const namespace of ['prod', 'company-prod-20260908', 'p'.repeat(32)]) {
  test(`production accepts explicit Hermes resource namespace ${namespace}`, () => {
    assert.doesNotThrow(() =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE: namespace,
        }),
      ),
    );
  });
}

test('broker Compose maps the typed namespace and production has no fallback', async () => {
  for (const [filename, expression] of [
    [
      'open-work-hub-dev.infra.yml',
      '${OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE:-dev}',
    ],
    [
      'open-work-hub-prod.app.yml',
      '${OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE:?Production Hermes resource namespace is required}',
    ],
  ]) {
    const text = await readFile(
      new URL(`../ops/compose/${filename}`, import.meta.url),
      'utf8',
    );
    const line = text
      .split('\n')
      .find((value) =>
        value.trim().startsWith('OWH_HERMES_TERMINAL_RESOURCE_NAMESPACE:'),
      );
    assert.equal(
      line?.trim(),
      `OWH_HERMES_TERMINAL_RESOURCE_NAMESPACE: ${expression}`,
    );
  }
});
