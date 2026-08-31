#!/usr/bin/env node

import { readFileSync } from 'node:fs';
import { isIP } from 'node:net';
import { pathToFileURL } from 'node:url';

import { normalizePublicBaseUrl } from './live-uat-preflight.mjs';

const ENV_KEY_PATTERN = /^[A-Z][A-Z0-9_]*$/;
const FALSE_VALUES = new Set(['0', 'false', 'no', 'off']);
const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on']);
const DEFAULT_DM_ATTACHMENT_SIGNING_KEY = 'dev-dm-attachment-signing-key';
const PORT_KEYS = [
  'OPEN_WORK_HUB_API_DEV_PORT',
  'OPEN_WORK_HUB_BENTO_PORT',
  'OPEN_WORK_HUB_DRAWIO_PORT',
  'OPEN_WORK_HUB_INFRA_MINIO_CONSOLE_PORT',
  'OPEN_WORK_HUB_INFRA_MINIO_PORT',
  'OPEN_WORK_HUB_INFRA_NGINX_PORT',
  'OPEN_WORK_HUB_INFRA_OPENSEARCH_PERF_PORT',
  'OPEN_WORK_HUB_INFRA_OPENSEARCH_PORT',
  'OPEN_WORK_HUB_INFRA_POSTGRES_PORT',
  'OPEN_WORK_HUB_INFRA_QDRANT_GRPC_PORT',
  'OPEN_WORK_HUB_INFRA_QDRANT_PORT',
  'OPEN_WORK_HUB_INFRA_REDIS_PORT',
  'OPEN_WORK_HUB_WEB_DEV_PORT',
];

function unquoteEnvValue(rawValue) {
  const value = rawValue.trim();
  if (value.length < 2) {
    return value;
  }
  const quote = value[0];
  if ((quote === '"' || quote === "'") && value.at(-1) === quote) {
    return value.slice(1, -1);
  }
  return value;
}

export function parseEnvText(text) {
  const values = new Map();
  for (const rawLine of text.split(/\r?\n/)) {
    let line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }
    if (line.startsWith('export ')) {
      line = line.slice(7).trim();
    }
    const separator = line.indexOf('=');
    if (separator < 1) {
      continue;
    }
    const key = line.slice(0, separator).trim();
    if (!ENV_KEY_PATTERN.test(key)) {
      continue;
    }
    values.set(key, unquoteEnvValue(line.slice(separator + 1)));
  }
  return values;
}

export function readEnvFile(path) {
  return parseEnvText(readFileSync(path, 'utf8'));
}

function requireExact(values, key, expected) {
  if ((values.get(key) ?? '').trim().toLowerCase() !== expected) {
    throw new Error(`${key} must be ${expected} for production deployment`);
  }
}

function requireBoolean(values, key, expected) {
  const normalized = (values.get(key) ?? '').trim().toLowerCase();
  const accepted = expected ? TRUE_VALUES : FALSE_VALUES;
  if (!accepted.has(normalized)) {
    throw new Error(`${key} must be ${expected ? 'enabled' : 'disabled'}`);
  }
}

function parsePort(values, key, { required = false } = {}) {
  const rawValue = (values.get(key) ?? '').trim();
  if (!rawValue && !required) {
    return null;
  }
  if (!/^\d+$/.test(rawValue)) {
    throw new Error(`${key} must be a valid TCP port`);
  }
  const port = Number(rawValue);
  if (port < 1 || port > 65_535) {
    throw new Error(`${key} must be a valid TCP port`);
  }
  return port;
}

function isPrivateOrLoopbackIpv4(value) {
  if (isIP(value) !== 4) {
    return false;
  }
  const [first, second] = value.split('.').map(Number);
  return (
    first === 10 ||
    first === 127 ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168)
  );
}

export function assertProductionAppEnv(values) {
  requireExact(values, 'OPEN_WORK_HUB_ENV_PROFILE', 'prod');
  requireExact(values, 'OPEN_WORK_HUB_API_ENVIRONMENT', 'production');
  requireBoolean(values, 'OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN', false);
  requireBoolean(values, 'OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT', false);
  requireBoolean(values, 'OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED', true);
  requireBoolean(values, 'OPEN_WORK_HUB_OPF_ENABLED', true);
  requireBoolean(values, 'OPEN_WORK_HUB_OPF_REQUIRED', true);

  const bindHost = (values.get('OPEN_WORK_HUB_APP_BIND_HOST') ?? '').trim();
  if (!['0.0.0.0', '127.0.0.1'].includes(bindHost)) {
    throw new Error('OPEN_WORK_HUB_APP_BIND_HOST must be 0.0.0.0 or 127.0.0.1');
  }
  const forwardedAllowIps = (
    values.get('OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS') ?? ''
  ).trim();
  if (!forwardedAllowIps) {
    throw new Error('OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS is required');
  }
  const trustedProxyIps = forwardedAllowIps
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  if (
    trustedProxyIps.length === 0 ||
    trustedProxyIps.some((value) => isIP(value) === 0)
  ) {
    throw new Error(
      'OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS must list exact proxy IP addresses',
    );
  }

  const signingKey = (
    values.get('OPEN_WORK_HUB_DM_ATTACHMENT_SIGNING_KEY') ?? ''
  ).trim();
  if (!signingKey || signingKey === DEFAULT_DM_ATTACHMENT_SIGNING_KEY) {
    throw new Error(
      'OPEN_WORK_HUB_DM_ATTACHMENT_SIGNING_KEY must use a production value',
    );
  }

  const appPort = parsePort(values, 'OPEN_WORK_HUB_APP_PORT', {
    required: true,
  });
  for (const key of PORT_KEYS) {
    const port = parsePort(values, key);
    if (port === appPort) {
      throw new Error(`OPEN_WORK_HUB_APP_PORT must not collide with ${key}`);
    }
  }

  const publicBaseUrl = normalizePublicBaseUrl(
    values.get('OPEN_WORK_HUB_APP_PUBLIC_URL'),
    'OPEN_WORK_HUB_APP_PUBLIC_URL',
  );
  const bentoServerUrl = normalizePublicBaseUrl(
    values.get('OPEN_WORK_HUB_BENTO_SERVER_URL'),
    'OPEN_WORK_HUB_BENTO_SERVER_URL',
  );
  if (bentoServerUrl.origin === publicBaseUrl.origin) {
    throw new Error(
      'OPEN_WORK_HUB_BENTO_SERVER_URL must use a dedicated origin',
    );
  }

  const bentoBindHost = (
    values.get('OPEN_WORK_HUB_BENTO_BIND_HOST') ?? ''
  ).trim();
  if (!isPrivateOrLoopbackIpv4(bentoBindHost)) {
    throw new Error(
      'OPEN_WORK_HUB_BENTO_BIND_HOST must be an exact private or loopback IPv4 address; wildcard, public, IPv6, and hostname bindings are forbidden',
    );
  }

  const opfServiceUrlValue = (
    values.get('OPEN_WORK_HUB_OPF_SERVICE_BASE_URL') ?? ''
  ).trim();
  let opfServiceBaseUrl;
  try {
    opfServiceBaseUrl = new URL(opfServiceUrlValue);
  } catch {
    throw new Error('OPEN_WORK_HUB_OPF_SERVICE_BASE_URL must be a valid URL');
  }
  if (
    opfServiceBaseUrl.protocol !== 'http:' ||
    opfServiceBaseUrl.hostname !== '127.0.0.1' ||
    !opfServiceBaseUrl.port ||
    opfServiceBaseUrl.pathname !== '/' ||
    opfServiceBaseUrl.username ||
    opfServiceBaseUrl.password ||
    opfServiceBaseUrl.search ||
    opfServiceBaseUrl.hash
  ) {
    throw new Error(
      'OPEN_WORK_HUB_OPF_SERVICE_BASE_URL must be a loopback HTTP origin with an explicit port',
    );
  }
  if (Number(opfServiceBaseUrl.port) === appPort) {
    throw new Error(
      'OPEN_WORK_HUB_OPF_SERVICE_BASE_URL must not collide with OPEN_WORK_HUB_APP_PORT',
    );
  }
  return {
    appPort,
    bentoBindHost,
    bentoServerUrl,
    bindHost,
    forwardedAllowIps,
    opfServiceBaseUrl,
    publicBaseUrl,
  };
}

function runCli() {
  const envPath = process.argv[2] ?? '.env';
  const config = assertProductionAppEnv(readEnvFile(envPath));
  const outputMode = process.argv[3];
  if (outputMode === '--print-bento-server-url') {
    process.stdout.write(config.bentoServerUrl.href);
    return;
  }
  if (outputMode) {
    throw new Error(`unsupported argument: ${outputMode}`);
  }
  process.stdout.write(
    'Production app environment preflight passed: runtime identity, security flags, port separation, proxy trust, and public origins are configured.\n',
  );
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  try {
    runCli();
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    process.stderr.write(
      `Production app environment preflight failed: ${detail}\n`,
    );
    process.exitCode = 1;
  }
}
