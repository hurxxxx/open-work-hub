import { describe, expect, it } from 'vitest';

import {
  OpenWorkHubDesktopUpdateFeedContract,
  OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_ENV_NAMES,
  OPEN_WORK_HUB_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME,
  OPEN_WORK_HUB_DESKTOP_STABLE_INSTALLER_FILE_NAMES,
  OPEN_WORK_HUB_DESKTOP_UPDATE_FEED_PATH_PREFIX,
  OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS,
  openWorkHubDesktopInstallerUrl,
  isOpenWorkHubDesktopUpdatePlatform,
  normalizeOpenWorkHubDesktopUpdatePlatform,
  type OpenWorkHubDesktopUpdatePlatform,
} from './open-work-hub-desktop-update-feed';

const expectedPlatformContracts = {
  win: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_WIN',
    stableInstallerFileName: 'Open Work Hub-Desktop-Setup-latest.exe',
    installerUrl:
      '/api/v1/open-work-hub-desktop/updates/win/Open Work Hub-Desktop-Setup-latest.exe',
  },
  mac: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_MAC',
    stableInstallerFileName: 'Open Work Hub-Desktop-latest.dmg',
    installerUrl: '/api/v1/open-work-hub-desktop/updates/mac/Open Work Hub-Desktop-latest.dmg',
  },
  linux: {
    installerUrlEnvName: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_LINUX',
    stableInstallerFileName: 'Open Work Hub-Desktop-latest.deb',
    installerUrl:
      '/api/v1/open-work-hub-desktop/updates/linux/Open Work Hub-Desktop-latest.deb',
  },
} as const satisfies Record<
  OpenWorkHubDesktopUpdatePlatform,
  {
    installerUrlEnvName: string;
    stableInstallerFileName: string;
    installerUrl: string;
  }
>;

describe('Open Work Hub desktop update feed contract', () => {
  it('keeps the existing exported constants on the contract values', () => {
    expect(OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS).toEqual(['win', 'mac', 'linux']);
    expect(OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS).toBe(
      OpenWorkHubDesktopUpdateFeedContract.platforms,
    );
    expect(OPEN_WORK_HUB_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      '/api/v1/open-work-hub-desktop/updates',
    );
    expect(OPEN_WORK_HUB_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      OpenWorkHubDesktopUpdateFeedContract.feedPathPrefix,
    );
    expect(OPEN_WORK_HUB_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL',
    );
    expect(OPEN_WORK_HUB_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      OpenWorkHubDesktopUpdateFeedContract.fallbackInstallerUrlEnvName,
    );
  });

  it('exports complete env and stable installer maps for each platform', () => {
    const platforms = [...OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS];

    expect(Object.keys(OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_ENV_NAMES).sort()).toEqual(
      [...platforms].sort(),
    );
    expect(
      Object.keys(OPEN_WORK_HUB_DESKTOP_STABLE_INSTALLER_FILE_NAMES).sort(),
    ).toEqual([...platforms].sort());

    expect(OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_ENV_NAMES).toEqual({
      win: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_WIN',
      mac: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_MAC',
      linux: 'VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_LINUX',
    });
    expect(OPEN_WORK_HUB_DESKTOP_STABLE_INSTALLER_FILE_NAMES).toEqual({
      win: 'Open Work Hub-Desktop-Setup-latest.exe',
      mac: 'Open Work Hub-Desktop-latest.dmg',
      linux: 'Open Work Hub-Desktop-latest.deb',
    });

    for (const platform of platforms) {
      expect(OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_ENV_NAMES[platform]).toBe(
        expectedPlatformContracts[platform].installerUrlEnvName,
      );
      expect(OPEN_WORK_HUB_DESKTOP_STABLE_INSTALLER_FILE_NAMES[platform]).toBe(
        expectedPlatformContracts[platform].stableInstallerFileName,
      );
      expect(OpenWorkHubDesktopUpdateFeedContract.platformContracts[platform]).toEqual(
        {
          installerUrlEnvName:
            expectedPlatformContracts[platform].installerUrlEnvName,
          stableInstallerFileName:
            expectedPlatformContracts[platform].stableInstallerFileName,
        },
      );
    }
  });

  it('constructs each platform installer URL through the contract', () => {
    for (const platform of OPEN_WORK_HUB_DESKTOP_UPDATE_PLATFORMS) {
      expect(openWorkHubDesktopInstallerUrl(platform)).toBe(
        expectedPlatformContracts[platform].installerUrl,
      );
      expect(OpenWorkHubDesktopUpdateFeedContract.installerUrl(platform)).toBe(
        expectedPlatformContracts[platform].installerUrl,
      );
    }
  });

  it('normalizes known platforms and rejects unsupported platform input', () => {
    expect(normalizeOpenWorkHubDesktopUpdatePlatform(' mac ')).toBe('mac');
    expect(isOpenWorkHubDesktopUpdatePlatform('win')).toBe(true);
    expect(isOpenWorkHubDesktopUpdatePlatform('darwin')).toBe(false);

    expect(() => normalizeOpenWorkHubDesktopUpdatePlatform('')).toThrow(
      'Open Work Hub desktop update platform is required. Supported platforms: win, mac, linux.',
    );

    const unsupportedPlatform = 'darwin' as OpenWorkHubDesktopUpdatePlatform;
    expect(() =>
      normalizeOpenWorkHubDesktopUpdatePlatform(unsupportedPlatform),
    ).toThrow(
      'Unsupported Open Work Hub desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
    expect(() => openWorkHubDesktopInstallerUrl(unsupportedPlatform)).toThrow(
      'Unsupported Open Work Hub desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
  });
});
