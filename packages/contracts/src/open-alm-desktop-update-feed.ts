const aiDoDesktopUpdatePlatforms = ['win', 'mac', 'linux'] as const;
const aiDoDesktopSupportedUpdatePlatforms =
  aiDoDesktopUpdatePlatforms.join(', ');
const aiDoDesktopUpdateFeedPathPrefix = '/api/v1/open-alm-desktop/updates';
const aiDoDesktopFallbackInstallerUrlEnvName =
  'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL';

export type AiDoDesktopUpdatePlatform =
  (typeof aiDoDesktopUpdatePlatforms)[number];

export type AiDoDesktopUpdatePlatformContract = {
  installerUrlEnvName: string;
  stableInstallerFileName: string;
};

const aiDoDesktopUpdatePlatformContracts = {
  win: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_WIN',
    stableInstallerFileName: 'Open ALM-Desktop-Setup-latest.exe',
  },
  mac: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_MAC',
    stableInstallerFileName: 'Open ALM-Desktop-latest.dmg',
  },
  linux: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_LINUX',
    stableInstallerFileName: 'Open ALM-Desktop-latest.deb',
  },
} as const satisfies Record<
  AiDoDesktopUpdatePlatform,
  AiDoDesktopUpdatePlatformContract
>;

const aiDoDesktopUpdatePlatformSet = new Set<string>(
  aiDoDesktopUpdatePlatforms,
);

export function isAiDoDesktopUpdatePlatform(
  platform: unknown,
): platform is AiDoDesktopUpdatePlatform {
  return (
    typeof platform === 'string' && aiDoDesktopUpdatePlatformSet.has(platform)
  );
}

export function normalizeAiDoDesktopUpdatePlatform(
  platform: unknown,
): AiDoDesktopUpdatePlatform {
  const normalized = String(platform ?? '').trim();
  if (!normalized) {
    throw new Error(
      `Open ALM desktop update platform is required. Supported platforms: ${aiDoDesktopSupportedUpdatePlatforms}.`,
    );
  }
  if (isAiDoDesktopUpdatePlatform(normalized)) {
    return normalized;
  }
  throw new Error(
    `Unsupported Open ALM desktop update platform: ${normalized}. Supported platforms: ${aiDoDesktopSupportedUpdatePlatforms}.`,
  );
}

function aiDoDesktopInstallerUrlEnvName(
  platform: AiDoDesktopUpdatePlatform,
): string {
  return aiDoDesktopUpdatePlatformContracts[
    normalizeAiDoDesktopUpdatePlatform(platform)
  ].installerUrlEnvName;
}

function aiDoDesktopStableInstallerFileName(
  platform: AiDoDesktopUpdatePlatform,
): string {
  return aiDoDesktopUpdatePlatformContracts[
    normalizeAiDoDesktopUpdatePlatform(platform)
  ].stableInstallerFileName;
}

function aiDoDesktopUpdateFeedInstallerUrl(
  platform: AiDoDesktopUpdatePlatform,
): string {
  const normalizedPlatform = normalizeAiDoDesktopUpdatePlatform(platform);
  return [
    aiDoDesktopUpdateFeedPathPrefix,
    normalizedPlatform,
    aiDoDesktopStableInstallerFileName(normalizedPlatform),
  ].join('/');
}

export const AiDoDesktopUpdateFeedContract = {
  platforms: aiDoDesktopUpdatePlatforms,
  feedPathPrefix: aiDoDesktopUpdateFeedPathPrefix,
  fallbackInstallerUrlEnvName: aiDoDesktopFallbackInstallerUrlEnvName,
  platformContracts: aiDoDesktopUpdatePlatformContracts,
  normalizePlatform: normalizeAiDoDesktopUpdatePlatform,
  installerUrlEnvName: aiDoDesktopInstallerUrlEnvName,
  stableInstallerFileName: aiDoDesktopStableInstallerFileName,
  installerUrl: aiDoDesktopUpdateFeedInstallerUrl,
} as const;

export const OPEN_ALM_DESKTOP_UPDATE_PLATFORMS =
  AiDoDesktopUpdateFeedContract.platforms;

export const OPEN_ALM_DESKTOP_UPDATE_FEED_PATH_PREFIX =
  AiDoDesktopUpdateFeedContract.feedPathPrefix;

export const OPEN_ALM_DESKTOP_INSTALLER_URL_ENV_NAMES: Record<
  AiDoDesktopUpdatePlatform,
  string
> = {
  win: AiDoDesktopUpdateFeedContract.installerUrlEnvName('win'),
  mac: AiDoDesktopUpdateFeedContract.installerUrlEnvName('mac'),
  linux: AiDoDesktopUpdateFeedContract.installerUrlEnvName('linux'),
};

export const OPEN_ALM_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME =
  AiDoDesktopUpdateFeedContract.fallbackInstallerUrlEnvName;

export const OPEN_ALM_DESKTOP_STABLE_INSTALLER_FILE_NAMES: Record<
  AiDoDesktopUpdatePlatform,
  string
> = {
  win: AiDoDesktopUpdateFeedContract.stableInstallerFileName('win'),
  mac: AiDoDesktopUpdateFeedContract.stableInstallerFileName('mac'),
  linux: AiDoDesktopUpdateFeedContract.stableInstallerFileName('linux'),
};

export function aiDoDesktopInstallerUrl(
  platform: AiDoDesktopUpdatePlatform,
): string {
  return AiDoDesktopUpdateFeedContract.installerUrl(platform);
}
