import { useCallback, useEffect, useReducer } from 'react';
import { useTranslation } from 'react-i18next';

import { getLlmHealth, type LlmHealthResponse } from '../api/chatbot-api';

export type AiHealthState = {
  health: LlmHealthResponse | null;
  healthError: string | null;
  isCheckingHealth: boolean;
};

type AiHealthAction =
  | { type: 'refresh-started' }
  | { type: 'refresh-succeeded'; health: LlmHealthResponse }
  | { type: 'refresh-failed'; errorMessage: string };

type AiHealthDispatch = (action: AiHealthAction) => void;
type ResolveHealthError = (error: unknown) => string;

export const INITIAL_AI_HEALTH_STATE: AiHealthState = {
  health: null,
  healthError: null,
  isCheckingHealth: false,
};

export function aiHealthReducer(
  state: AiHealthState,
  action: AiHealthAction,
): AiHealthState {
  if (action.type === 'refresh-started') {
    return { ...state, isCheckingHealth: true };
  }
  if (action.type === 'refresh-succeeded') {
    return {
      health: action.health,
      healthError: null,
      isCheckingHealth: false,
    };
  }
  return {
    health: null,
    healthError: action.errorMessage,
    isCheckingHealth: false,
  };
}

async function dispatchHealthRefreshResult({
  dispatch,
  resolveHealthError,
  shouldDispatch = () => true,
  token,
}: {
  dispatch: AiHealthDispatch;
  resolveHealthError: ResolveHealthError;
  shouldDispatch?: () => boolean;
  token: string;
}): Promise<void> {
  try {
    const nextHealth = await getLlmHealth(token, {});
    if (shouldDispatch()) {
      dispatch({ type: 'refresh-succeeded', health: nextHealth });
    }
  } catch (error) {
    if (shouldDispatch()) {
      dispatch({
        type: 'refresh-failed',
        errorMessage: resolveHealthError(error),
      });
    }
  }
}

export function useChatbotHealth(token: string | null): AiHealthState & {
  refreshHealth: () => Promise<void>;
} {
  const { t } = useTranslation('apps');
  const [state, dispatch] = useReducer(
    aiHealthReducer,
    INITIAL_AI_HEALTH_STATE,
  );
  const resolveHealthError = useCallback(
    (error: unknown) =>
      error instanceof Error ? error.message : t('ai.view.modelStatusFailed'),
    [t],
  );

  const refreshHealth = useCallback(async () => {
    if (!token) {
      return;
    }

    dispatch({ type: 'refresh-started' });
    await dispatchHealthRefreshResult({
      dispatch,
      resolveHealthError,
      token,
    });
  }, [resolveHealthError, token]);

  useEffect(() => {
    if (!token) {
      return;
    }

    let cancelled = false;
    void dispatchHealthRefreshResult({
      dispatch,
      resolveHealthError,
      shouldDispatch: () => !cancelled,
      token,
    });

    return () => {
      cancelled = true;
    };
  }, [resolveHealthError, token]);

  return {
    ...state,
    refreshHealth,
  };
}
