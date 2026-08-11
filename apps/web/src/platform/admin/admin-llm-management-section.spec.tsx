import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import {
  AdminLlmManagementSection,
  resolveLlmManagementTab,
  withLlmManagementTab,
} from './admin-llm-management-section';

vi.mock('./admin-llm-routing-overview', () => ({
  AdminLlmRoutingOverview: () => <div>routing overview</div>,
}));

vi.mock('./admin-llm-provider-settings-section', () => ({
  AdminLlmProviderSettingsSection: () => <div>provider settings</div>,
}));

vi.mock('./admin-ai-model-settings-section', () => ({
  AdminAiModelSettingsSection: () => <div>model catalog</div>,
}));

function LocationHarness() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <AdminLlmManagementSection token="token" />
      <output aria-label="location">{location.search}</output>
      <button onClick={() => navigate(-1)} type="button">
        back
      </button>
    </>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationHarness />
    </MemoryRouter>,
  );
}

describe('LLM management tab routing', () => {
  it('defaults missing and invalid tab values to routing', () => {
    expect(resolveLlmManagementTab(null)).toBe('routing');
    expect(resolveLlmManagementTab('invalid')).toBe('routing');
    expect(resolveLlmManagementTab('providers')).toBe('providers');
    expect(resolveLlmManagementTab('obsolete')).toBe('routing');
  });

  it('preserves unrelated query parameters when changing tabs', () => {
    expect(
      withLlmManagementTab(
        new URLSearchParams('source=admin&tab=routing'),
        'models',
      ).toString(),
    ).toBe('source=admin&tab=models');
  });

  it('supports provider deep links', () => {
    renderAt('/admin/llm?tab=providers');

    expect(screen.getByText('provider settings')).toBeTruthy();
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=providers',
    );
  });

  it('pushes tab changes so browser back restores the previous tab', async () => {
    renderAt('/admin/llm?tab=routing');

    fireEvent.mouseDown(screen.getAllByRole('tab')[1], {
      button: 0,
      ctrlKey: false,
    });
    expect(await screen.findByText('provider settings')).toBeTruthy();
    expect(screen.getByLabelText('location').textContent).toBe(
      '?tab=providers',
    );

    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    await waitFor(() => {
      expect(screen.getByText('routing overview')).toBeTruthy();
    });
    expect(screen.getByLabelText('location').textContent).toBe('?tab=routing');
  });

  it('does not push the same tab twice when the tab primitive repeats a change', async () => {
    renderAt('/admin/llm?tab=routing');

    const providerTab = screen.getAllByRole('tab')[1];
    fireEvent.mouseDown(providerTab, { button: 0, ctrlKey: false });
    fireEvent.mouseDown(providerTab, { button: 0, ctrlKey: false });
    expect(await screen.findByText('provider settings')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    await waitFor(() => {
      expect(screen.getByText('routing overview')).toBeTruthy();
    });
    expect(screen.getByLabelText('location').textContent).toBe('?tab=routing');
  });
});
