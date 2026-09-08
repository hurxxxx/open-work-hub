#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import {
  closeSync,
  constants,
  existsSync,
  fstatSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const IMAGE_ID = /^sha256:[a-f0-9]{64}$/;
const REVISION = /^[a-f0-9]{40}$/;

function invoke(command, args) {
  return execFileSync(command, args, {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

function checked(run, command, args, label) {
  try {
    return run(command, args).trim();
  } catch {
    // Child diagnostics can include environment values. Only describe the stage.
    throw new Error(`Rollback ${label} failed.`);
  }
}

function readSecureEnv(file) {
  let descriptor;
  try {
    descriptor = openSync(
      file,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
    );
    const stat = fstatSync(descriptor);
    if (
      !stat.isFile() ||
      (stat.mode & 0o7777) !== 0o600 ||
      stat.uid !== process.getuid()
    ) {
      throw new Error('insecure');
    }
    return { contents: readFileSync(descriptor), stat };
  } catch {
    throw new Error(
      'Rollback environment must be an owned regular non-symlink file with mode 0600.',
    );
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function ensurePrivateDirectory(directory) {
  if (!existsSync(directory)) mkdirSync(directory, { mode: 0o700 });
  const stat = lstatSync(directory);
  if (
    !stat.isDirectory() ||
    stat.isSymbolicLink() ||
    stat.uid !== process.getuid() ||
    stat.mode & 0o022
  ) {
    throw new Error(
      'Rollback directory must be owned and not writable by other users.',
    );
  }
}

function checkSnapshotTree(directory) {
  for (const entry of readdirSync(directory)) {
    const candidate = path.join(directory, entry);
    const stat = lstatSync(candidate);
    if (stat.isDirectory()) checkSnapshotTree(candidate);
    else if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error(
        'Rollback deployment assets must contain only regular files and directories.',
      );
    }
  }
}

function envDigest(contents) {
  return createHash('sha256').update(contents).digest('hex');
}

export function prepareRollbackBundle(
  { rootDir, envFile, image, expectedImage },
  { run = invoke } = {},
) {
  if (!IMAGE_ID.test(image))
    throw new Error('Rollback image must be a full immutable sha256 image ID.');
  const actualId = checked(
    run,
    'docker',
    ['image', 'inspect', '--format', '{{.Id}}', image],
    'image inspection',
  );
  const expectedId = checked(
    run,
    'docker',
    ['image', 'inspect', '--format', '{{.Id}}', expectedImage],
    'expected image inspection',
  );
  if (actualId !== image || expectedId !== image) {
    throw new Error(
      'Rollback image does not match the required production image.',
    );
  }
  const revision = checked(
    run,
    'docker',
    [
      'image',
      'inspect',
      '--format',
      '{{ index .Config.Labels "org.opencontainers.image.revision" }}',
      image,
    ],
    'image revision inspection',
  );
  if (!REVISION.test(revision))
    throw new Error(
      'Rollback image must declare a full 40-character Git revision.',
    );
  const commit = checked(
    run,
    'git',
    ['-C', rootDir, 'rev-parse', '--verify', `${revision}^{commit}`],
    'Git commit verification',
  );
  if (commit !== revision)
    throw new Error(
      'Rollback image revision is not the expected local Git commit.',
    );
  const { contents, stat } = readSecureEnv(envFile);
  const activeEnv = path.join(rootDir, '.env');
  if (existsSync(activeEnv)) {
    const activeStat = lstatSync(activeEnv);
    if (activeStat.dev === stat.dev && activeStat.ino === stat.ino) {
      throw new Error(
        'Rollback environment must be a separate backup of the previous environment.',
      );
    }
  }
  let parent = rootDir;
  for (const segment of ['.runtime', 'prod-app', 'rollback']) {
    parent = path.join(parent, segment);
    ensurePrivateDirectory(parent);
  }
  const bundle = mkdtempSync(path.join(parent, `${image.slice(7, 19)}-`));
  try {
    const archive = path.join(bundle, 'assets.tar');
    checked(
      run,
      'git',
      [
        '-C',
        rootDir,
        'archive',
        '--format=tar',
        `--output=${archive}`,
        revision,
        'ops',
        'scripts',
        'package.json',
      ],
      'deployment asset snapshot',
    );
    checked(
      run,
      'tar',
      [
        '--extract',
        '--file',
        archive,
        '--directory',
        bundle,
        '--no-same-owner',
        '--no-same-permissions',
      ],
      'deployment asset extraction',
    );
    rmSync(archive);
    checkSnapshotTree(bundle);
    for (const relative of [
      'ops/compose/open-work-hub-prod.app.yml',
      'scripts/prod-app-config.mjs',
      'scripts/prod-app-smoke.mjs',
      'package.json',
    ]) {
      if (!lstatSync(path.join(bundle, relative)).isFile())
        throw new Error('Rollback deployment assets are incomplete.');
    }
    writeFileSync(path.join(bundle, '.env'), contents, {
      flag: 'wx',
      mode: 0o600,
    });
    checked(
      run,
      'node',
      [
        path.join(bundle, 'scripts/prod-app-config.mjs'),
        path.join(bundle, '.env'),
      ],
      'previous environment validation',
    );
    writeFileSync(
      path.join(bundle, 'rollback.json'),
      JSON.stringify({
        version: 1,
        image,
        revision,
        envSha256: envDigest(contents),
      }),
      { flag: 'wx', mode: 0o600 },
    );
    return bundle;
  } catch (error) {
    rmSync(bundle, { recursive: true, force: true });
    throw error;
  }
}

export function restoreRollbackEnvironment({ rootDir, bundle, image }) {
  const parent = path.join(rootDir, '.runtime', 'prod-app', 'rollback');
  if (path.dirname(path.resolve(bundle)) !== path.resolve(parent)) {
    throw new Error('Rollback bundle must belong to this production checkout.');
  }
  for (const directory of [
    path.join(rootDir, '.runtime'),
    path.join(rootDir, '.runtime', 'prod-app'),
    parent,
    bundle,
  ]) {
    ensurePrivateDirectory(directory);
  }
  const manifest = JSON.parse(
    readSecureEnv(path.join(bundle, 'rollback.json')).contents.toString('utf8'),
  );
  if (
    manifest.version !== 1 ||
    manifest.image !== image ||
    !IMAGE_ID.test(image) ||
    !REVISION.test(manifest.revision)
  ) {
    throw new Error('Rollback bundle image identity does not match.');
  }
  const { contents } = readSecureEnv(path.join(bundle, '.env'));
  if (envDigest(contents) !== manifest.envSha256)
    throw new Error('Rollback environment snapshot has changed.');
  const destination = path.join(rootDir, '.env');
  const destinationStat = lstatSync(destination, { throwIfNoEntry: false });
  if (
    destinationStat &&
    (!destinationStat.isFile() || destinationStat.isSymbolicLink())
  ) {
    throw new Error(
      'Production environment destination must be a regular non-symlink file.',
    );
  }
  const temporary = path.join(rootDir, `.env.rollback-${randomUUID()}`);
  let descriptor;
  try {
    descriptor = openSync(temporary, 'wx', 0o600);
    writeFileSync(descriptor, contents);
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    renameSync(temporary, destination);
    const directory = openSync(rootDir, constants.O_RDONLY);
    try {
      fsyncSync(directory);
    } finally {
      closeSync(directory);
    }
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
    rmSync(temporary, { force: true });
  }
}

function main(args) {
  const [command, rootDir, envOrBundle, image, expectedImage] = args;
  if (command === 'prepare' && args.length === 5) {
    process.stdout.write(
      `${prepareRollbackBundle({ rootDir, envFile: envOrBundle, image, expectedImage })}\n`,
    );
  } else if (command === 'restore-env' && args.length === 4) {
    restoreRollbackEnvironment({ rootDir, bundle: envOrBundle, image });
  } else {
    throw new Error('Invalid rollback helper command.');
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    main(process.argv.slice(2));
  } catch {
    process.stderr.write(
      'Production rollback preparation or environment restoration failed; no environment values were logged.\n',
    );
    process.exitCode = 1;
  }
}
