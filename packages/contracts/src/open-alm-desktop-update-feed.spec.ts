import { describe, expect, it } from 'vitest';

import {
  AiDoDesktopUpdateFeedContract,
  OPEN_ALM_DESKTOP_INSTALLER_URL_ENV_NAMES,
  OPEN_ALM_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME,
  OPEN_ALM_DESKTOP_STABLE_INSTALLER_FILE_NAMES,
  OPEN_ALM_DESKTOP_UPDATE_FEED_PATH_PREFIX,
  OPEN_ALM_DESKTOP_UPDATE_PLATFORMS,
  aiDoDesktopInstallerUrl,
  isAiDoDesktopUpdatePlatform,
  normalizeAiDoDesktopUpdatePlatform,
  type AiDoDesktopUpdatePlatform,
} from './open-alm-desktop-update-feed';

const expectedPlatformContracts = {
  win: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_WIN',
    stableInstallerFileName: 'Open ALM-Desktop-Setup-latest.exe',
    installerUrl:
      '/api/v1/open-alm-desktop/updates/win/Open ALM-Desktop-Setup-latest.exe',
  },
  mac: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_MAC',
    stableInstallerFileName: 'Open ALM-Desktop-latest.dmg',
    installerUrl: '/api/v1/open-alm-desktop/updates/mac/Open ALM-Desktop-latest.dmg',
  },
  linux: {
    installerUrlEnvName: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_LINUX',
    stableInstallerFileName: 'Open ALM-Desktop-latest.deb',
    installerUrl:
      '/api/v1/open-alm-desktop/updates/linux/Open ALM-Desktop-latest.deb',
  },
} as const satisfies Record<
  AiDoDesktopUpdatePlatform,
  {
    installerUrlEnvName: string;
    stableInstallerFileName: string;
    installerUrl: string;
  }
>;

describe('Open ALM desktop update feed contract', () => {
  it('keeps the existing exported constants on the contract values', () => {
    expect(OPEN_ALM_DESKTOP_UPDATE_PLATFORMS).toEqual(['win', 'mac', 'linux']);
    expect(OPEN_ALM_DESKTOP_UPDATE_PLATFORMS).toBe(
      AiDoDesktopUpdateFeedContract.platforms,
    );
    expect(OPEN_ALM_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      '/api/v1/open-alm-desktop/updates',
    );
    expect(OPEN_ALM_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      AiDoDesktopUpdateFeedContract.feedPathPrefix,
    );
    expect(OPEN_ALM_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL',
    );
    expect(OPEN_ALM_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      AiDoDesktopUpdateFeedContract.fallbackInstallerUrlEnvName,
    );
  });

  it('exports complete env and stable installer maps for each platform', () => {
    const platforms = [...OPEN_ALM_DESKTOP_UPDATE_PLATFORMS];

    expect(Object.keys(OPEN_ALM_DESKTOP_INSTALLER_URL_ENV_NAMES).sort()).toEqual(
      [...platforms].sort(),
    );
    expect(
      Object.keys(OPEN_ALM_DESKTOP_STABLE_INSTALLER_FILE_NAMES).sort(),
    ).toEqual([...platforms].sort());

    expect(OPEN_ALM_DESKTOP_INSTALLER_URL_ENV_NAMES).toEqual({
      win: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_WIN',
      mac: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_MAC',
      linux: 'VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_LINUX',
    });
    expect(OPEN_ALM_DESKTOP_STABLE_INSTALLER_FILE_NAMES).toEqual({
      win: 'Open ALM-Desktop-Setup-latest.exe',
      mac: 'Open ALM-Desktop-latest.dmg',
      linux: 'Open ALM-Desktop-latest.deb',
    });

    for (const platform of platforms) {
      expect(OPEN_ALM_DESKTOP_INSTALLER_URL_ENV_NAMES[platform]).toBe(
        expectedPlatformContracts[platform].installerUrlEnvName,
      );
      expect(OPEN_ALM_DESKTOP_STABLE_INSTALLER_FILE_NAMES[platform]).toBe(
        expectedPlatformContracts[platform].stableInstallerFileName,
      );
      expect(AiDoDesktopUpdateFeedContract.platformContracts[platform]).toEqual(
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
    for (const platform of OPEN_ALM_DESKTOP_UPDATE_PLATFORMS) {
      expect(aiDoDesktopInstallerUrl(platform)).toBe(
        expectedPlatformContracts[platform].installerUrl,
      );
      expect(AiDoDesktopUpdateFeedContract.installerUrl(platform)).toBe(
        expectedPlatformContracts[platform].installerUrl,
      );
    }
  });

  it('normalizes known platforms and rejects unsupported platform input', () => {
    expect(normalizeAiDoDesktopUpdatePlatform(' mac ')).toBe('mac');
    expect(isAiDoDesktopUpdatePlatform('win')).toBe(true);
    expect(isAiDoDesktopUpdatePlatform('darwin')).toBe(false);

    expect(() => normalizeAiDoDesktopUpdatePlatform('')).toThrow(
      'Open ALM desktop update platform is required. Supported platforms: win, mac, linux.',
    );

    const unsupportedPlatform = 'darwin' as AiDoDesktopUpdatePlatform;
    expect(() =>
      normalizeAiDoDesktopUpdatePlatform(unsupportedPlatform),
    ).toThrow(
      'Unsupported Open ALM desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
    expect(() => aiDoDesktopInstallerUrl(unsupportedPlatform)).toThrow(
      'Unsupported Open ALM desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
  });
});
