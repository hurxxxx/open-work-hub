import { describe, expect, it } from 'vitest';

import {
  AiDoDesktopUpdateFeedContract,
  AI_DO_DESKTOP_INSTALLER_URL_ENV_NAMES,
  AI_DO_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME,
  AI_DO_DESKTOP_STABLE_INSTALLER_FILE_NAMES,
  AI_DO_DESKTOP_UPDATE_FEED_PATH_PREFIX,
  AI_DO_DESKTOP_UPDATE_PLATFORMS,
  aiDoDesktopInstallerUrl,
  isAiDoDesktopUpdatePlatform,
  normalizeAiDoDesktopUpdatePlatform,
  type AiDoDesktopUpdatePlatform,
} from './ai-do-desktop-update-feed';

const expectedPlatformContracts = {
  win: {
    installerUrlEnvName: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_WIN',
    stableInstallerFileName: 'AI-DO-Desktop-Setup-latest.exe',
    installerUrl:
      '/api/v1/ai-do-desktop/updates/win/AI-DO-Desktop-Setup-latest.exe',
  },
  mac: {
    installerUrlEnvName: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_MAC',
    stableInstallerFileName: 'AI-DO-Desktop-latest.dmg',
    installerUrl: '/api/v1/ai-do-desktop/updates/mac/AI-DO-Desktop-latest.dmg',
  },
  linux: {
    installerUrlEnvName: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_LINUX',
    stableInstallerFileName: 'AI-DO-Desktop-latest.deb',
    installerUrl:
      '/api/v1/ai-do-desktop/updates/linux/AI-DO-Desktop-latest.deb',
  },
} as const satisfies Record<
  AiDoDesktopUpdatePlatform,
  {
    installerUrlEnvName: string;
    stableInstallerFileName: string;
    installerUrl: string;
  }
>;

describe('AI-DO desktop update feed contract', () => {
  it('keeps the existing exported constants on the contract values', () => {
    expect(AI_DO_DESKTOP_UPDATE_PLATFORMS).toEqual(['win', 'mac', 'linux']);
    expect(AI_DO_DESKTOP_UPDATE_PLATFORMS).toBe(
      AiDoDesktopUpdateFeedContract.platforms,
    );
    expect(AI_DO_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      '/api/v1/ai-do-desktop/updates',
    );
    expect(AI_DO_DESKTOP_UPDATE_FEED_PATH_PREFIX).toBe(
      AiDoDesktopUpdateFeedContract.feedPathPrefix,
    );
    expect(AI_DO_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      'VITE_AI_DO_DESKTOP_INSTALLER_URL',
    );
    expect(AI_DO_DESKTOP_FALLBACK_INSTALLER_URL_ENV_NAME).toBe(
      AiDoDesktopUpdateFeedContract.fallbackInstallerUrlEnvName,
    );
  });

  it('exports complete env and stable installer maps for each platform', () => {
    const platforms = [...AI_DO_DESKTOP_UPDATE_PLATFORMS];

    expect(Object.keys(AI_DO_DESKTOP_INSTALLER_URL_ENV_NAMES).sort()).toEqual(
      [...platforms].sort(),
    );
    expect(
      Object.keys(AI_DO_DESKTOP_STABLE_INSTALLER_FILE_NAMES).sort(),
    ).toEqual([...platforms].sort());

    expect(AI_DO_DESKTOP_INSTALLER_URL_ENV_NAMES).toEqual({
      win: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_WIN',
      mac: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_MAC',
      linux: 'VITE_AI_DO_DESKTOP_INSTALLER_URL_LINUX',
    });
    expect(AI_DO_DESKTOP_STABLE_INSTALLER_FILE_NAMES).toEqual({
      win: 'AI-DO-Desktop-Setup-latest.exe',
      mac: 'AI-DO-Desktop-latest.dmg',
      linux: 'AI-DO-Desktop-latest.deb',
    });

    for (const platform of platforms) {
      expect(AI_DO_DESKTOP_INSTALLER_URL_ENV_NAMES[platform]).toBe(
        expectedPlatformContracts[platform].installerUrlEnvName,
      );
      expect(AI_DO_DESKTOP_STABLE_INSTALLER_FILE_NAMES[platform]).toBe(
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
    for (const platform of AI_DO_DESKTOP_UPDATE_PLATFORMS) {
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
      'AI-DO desktop update platform is required. Supported platforms: win, mac, linux.',
    );

    const unsupportedPlatform = 'darwin' as AiDoDesktopUpdatePlatform;
    expect(() =>
      normalizeAiDoDesktopUpdatePlatform(unsupportedPlatform),
    ).toThrow(
      'Unsupported AI-DO desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
    expect(() => aiDoDesktopInstallerUrl(unsupportedPlatform)).toThrow(
      'Unsupported AI-DO desktop update platform: darwin. Supported platforms: win, mac, linux.',
    );
  });
});
