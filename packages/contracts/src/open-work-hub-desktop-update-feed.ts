const openWorkHubDesktopUpdatePlatforms = ['win', 'mac', 'linux'] as const;
const openWorkHubDesktopSupportedUpdatePlatforms =
  openWorkHubDesktopUpdatePlatforms.join(', ');
const openWorkHubDesktopUpdateFeedPathPrefix = '/api/v1/open-work-hub-desktop/updates';
const openWorkHubDesktopFallbackInstallerUrlEnvName =
  'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL';

export type OpenWorkHubDesktopUpdatePlatform =
  (typeof openWorkHubDesktopUpdatePlatforms)[number];

export type OpenWorkHubDesktopUpdatePlatformContract = {
  installerUrlEnvName: string;
  stableInstallerFileName: string;
};

const openWorkHubDesktopUpdatePlatformContracts = {
  win: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_WIN',
    stableInstallerFileName: 'Open Work Hub-Desktop-Setup-latest.exe',
  },
  mac: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_MAC',
    stableInstallerFileName: 'Open Work Hub-Desktop-latest.dmg',
  },
  linux: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_LINUX',
    stableInstallerFileName: 'Open Work Hub-Desktop-latest.deb',
  },
} as const satisfies Record<
  OpenWorkHubDesktopUpdatePlatform,
  OpenWorkHubDesktopUpdatePlatformContract
>;

const openWorkHubDesktopUpdatePlatformSet = new Set<string>(
  openWorkHubDesktopUpdatePlatforms,
);

export function isOpenWorkHubDesktopUpdatePlatform(
  platform: unknown,
): platform is OpenWorkHubDesktopUpdatePlatform {
  return (
    typeof platform === 'string' && openWorkHubDesktopUpdatePlatformSet.has(platform)
  );
}

export function normalizeOpenWorkHubDesktopUpdatePlatform(
  platform: unknown,
): OpenWorkHubDesktopUpdatePlatform {
  const normalized = String(platform ?? '').trim();
  if (!normalized) {
    throw new Error(
      `Open Work Hub desktop update platform is required. Supported platforms: ${openWorkHubDesktopSupportedUpdatePlatforms}.`,
    );
  }
  if (isOpenWorkHubDesktopUpdatePlatform(normalized)) {
    return normalized;
  }
  throw new Error(
    `Unsupported Open Work Hub desktop update platform: ${normalized}. Supported platforms: ${openWorkHubDesktopSupportedUpdatePlatforms}.`,
  );
}

function openWorkHubDesktopInstallerUrlEnvName(
  platform: OpenWorkHubDesktopUpdatePlatform,
): string {
  return openWorkHubDesktopUpdatePlatformContracts[
    normalizeOpenWorkHubDesktopUpdatePlatform(platform)
  ].installerUrlEnvName;
}

function openWorkHubDesktopStableInstallerFileName(
  platform: OpenWorkHubDesktopUpdatePlatform,
): string {
  return openWorkHubDesktopUpdatePlatformContracts[
    normalizeOpenWorkHubDesktopUpdatePlatform(platform)
  ].stableInstallerFileName;
}

function openWorkHubDesktopUpdateFeedInstallerUrl(
  platform: OpenWorkHubDesktopUpdatePlatform,
): string {
  const normalizedPlatform = normalizeOpenWorkHubDesktopUpdatePlatform(platform);
  return [
    openWorkHubDesktopUpdateFeedPathPrefix,
    normalizedPlatform,
    openWorkHubDesktopStableInstallerFileName(normalizedPlatform),
  ].join('/');
}

export const OpenWorkHubDesktopUpdateFeedContract = {
  platforms: openWorkHubDesktopUpdatePlatforms,
  feedPathPrefix: openWorkHubDesktopUpdateFeedPathPrefix,
  fallbackInstallerUrlEnvName: openWorkHubDesktopFallbackInstallerUrlEnvName,
  platformContracts: openWorkHubDesktopUpdatePlatformContracts,
  normalizePlatform: normalizeOpenWorkHubDesktopUpdatePlatform,
  installerUrlEnvName: openWorkHubDesktopInstallerUrlEnvName,
  stableInstallerFileName: openWorkHubDesktopStableInstallerFileName,
  installerUrl: openWorkHubDesktopUpdateFeedInstallerUrl,
} as const;

export const OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS =
  OpenWorkHubDesktopUpdateFeedContract.platforms;

export const OPEN_WORK_HUB_DESKTOP_UPDATE_FEED_PATH_PREFIX =
  OpenWorkHubDesktopUpdateFeedContract.feedPathPrefix;

export const OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_ENV_NAMES: Record<
  OpenWorkHubDesktopUpdatePlatform,
  string
> = {
  win: OpenWorkHubDesktopUpdateFeedContract.installerUrlEnvName('win'),
  mac: OpenWorkHubDesktopUpdateFeedContract.installerUrlEnvName('mac'),
  linux: OpenWorkHubDesktopUpdateFeedContract.installerUrlEnvName('linux'),
};

export const OPEN_WORK_HUB_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME =
  OpenWorkHubDesktopUpdateFeedContract.fallbackInstallerUrlEnvName;

export const OPEN_WORK_HUB_DESKTOP_STABLE_INSTALLER_FILE_NAMES: Record<
  OpenWorkHubDesktopUpdatePlatform,
  string
> = {
  win: OpenWorkHubDesktopUpdateFeedContract.stableInstallerFileName('win'),
  mac: OpenWorkHubDesktopUpdateFeedContract.stableInstallerFileName('mac'),
  linux: OpenWorkHubDesktopUpdateFeedContract.stableInstallerFileName('linux'),
};

export function openWorkHubDesktopInstallerUrl(
  platform: OpenWorkHubDesktopUpdatePlatform,
): string {
  return OpenWorkHubDesktopUpdateFeedContract.installerUrl(platform);
}
