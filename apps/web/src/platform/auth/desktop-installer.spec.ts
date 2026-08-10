import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildDesktopInstallerRows,
  DEFAULT_DESKTOP_INSTALLER_URLS,
  detectDesktopInstallPlatform,
  DESKTOP_INSTALLER_PLATFORMS,
  downloadDesktopInstaller,
  resolveDesktopInstallerDownload,
  resolveDesktopInstallerUrls,
} from './desktop-installer';

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('desktop installer platform detection', () => {
  it('detects macOS and Linux from browser platform signals', () => {
    expect(detectDesktopInstallPlatform({ platform: 'MacIntel' })).toBe('mac');
    expect(
      detectDesktopInstallPlatform({ userAgent: 'Mozilla/5.0 (Mac OS X)' }),
    ).toBe('mac');
    expect(detectDesktopInstallPlatform({ platform: 'Linux x86_64' })).toBe(
      'linux',
    );
    expect(
      detectDesktopInstallPlatform({ userAgent: 'X11; Linux x86_64' }),
    ).toBe('linux');
  });

  it('falls back to Windows for unknown or server-side signals', () => {
    expect(detectDesktopInstallPlatform({ platform: 'Win32' })).toBe('win');
    expect(detectDesktopInstallPlatform({})).toBe('win');
  });
});

describe('desktop installer URL resolution', () => {
  it('uses shared contract defaults when no env override is present', () => {
    expect(resolveDesktopInstallerUrls({})).toEqual(
      DEFAULT_DESKTOP_INSTALLER_URLS,
    );
  });

  it('uses generic Windows env fallback without affecting macOS or Linux', () => {
    expect(
      resolveDesktopInstallerUrls({
        VITE_AI_DO_DESKTOP_INSTALLER_URL:
          'https://downloads.example.com/windows.exe',
      }),
    ).toEqual({
      ...DEFAULT_DESKTOP_INSTALLER_URLS,
      win: 'https://downloads.example.com/windows.exe',
    });
  });

  it('uses platform-specific env overrides before defaults', () => {
    expect(
      resolveDesktopInstallerUrls({
        VITE_AI_DO_DESKTOP_INSTALLER_URL:
          'https://downloads.example.com/windows-fallback.exe',
        VITE_AI_DO_DESKTOP_INSTALLER_URL_WIN:
          'https://downloads.example.com/windows.exe',
        VITE_AI_DO_DESKTOP_INSTALLER_URL_MAC:
          'https://downloads.example.com/mac.dmg',
        VITE_AI_DO_DESKTOP_INSTALLER_URL_LINUX:
          'https://downloads.example.com/linux.deb',
      }),
    ).toEqual({
      win: 'https://downloads.example.com/windows.exe',
      mac: 'https://downloads.example.com/mac.dmg',
      linux: 'https://downloads.example.com/linux.deb',
    });
  });
});

describe('desktop installer catalog', () => {
  it('builds platform rows with installer urls and current platform state', () => {
    const rows = buildDesktopInstallerRows(
      {
        win: 'https://downloads.example.com/windows.exe',
        mac: 'https://downloads.example.com/mac.dmg',
        linux: 'https://downloads.example.com/linux.deb',
      },
      'linux',
    );

    expect(rows.map((row) => row.platform)).toEqual(
      DESKTOP_INSTALLER_PLATFORMS.map((item) => item.platform),
    );
    expect(rows.map((row) => [row.platform, row.installerUrl, row.isCurrent])).toEqual([
      ['win', 'https://downloads.example.com/windows.exe', false],
      ['mac', 'https://downloads.example.com/mac.dmg', false],
      ['linux', 'https://downloads.example.com/linux.deb', true],
    ]);
  });
});

describe('desktop installer download', () => {
  it('resolves relative installer URLs against the current page', () => {
    expect(
      resolveDesktopInstallerDownload(
        '/api/v1/ai-do-desktop/updates/win/AI-DO%20Desktop%20Setup.exe',
        'https://app.example.com/settings',
      ),
    ).toEqual({
      href: 'https://app.example.com/api/v1/ai-do-desktop/updates/win/AI-DO%20Desktop%20Setup.exe',
      fileName: 'AI-DO Desktop Setup.exe',
    });
  });

  it('clicks a temporary anchor and removes it', () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    downloadDesktopInstaller(
      '/api/v1/ai-do-desktop/updates/linux/AI-DO-Desktop-latest.deb',
      document,
      'https://app.example.com/settings',
    );

    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a')).toBeNull();
  });
});
