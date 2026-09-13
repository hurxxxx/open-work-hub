import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LlmHealthResponse } from '../../api/chatbot-api';
import { AgentControlMenu } from './AgentControlMenu';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: null }),
}));
afterEach(cleanup);

describe('Hermes model display', () => {
  it('follows the server model and avoids claiming a model when unavailable', () => {
    const { rerender } = render(
      <AgentControlMenu health={null} healthError={null} />,
    );
    expect(screen.getByRole('button', { name: 'Hermes' })).toBeTruthy();
    const health = {
      ready: true,
      local: { model: 'administrator-selected-model' },
      external: null,
    } as LlmHealthResponse;
    rerender(<AgentControlMenu health={health} healthError={null} />);
    expect(
      screen.getByRole('button', {
        name: 'Hermes · administrator-selected-model',
      }),
    ).toBeTruthy();
    rerender(<AgentControlMenu health={null} healthError="unavailable" />);
    expect(screen.getByRole('button', { name: 'Hermes' })).toBeTruthy();
  });
});
