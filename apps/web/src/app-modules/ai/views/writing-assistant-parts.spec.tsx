import { act, renderHook } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { WritingResult } from '../api/writing-assistant-api';
import { useSyncedText } from './writing-assistant-parts';

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => undefined;
  let reject: (reason?: unknown) => void = () => undefined;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const apiHarness = vi.hoisted(() => ({ translateWriting: vi.fn() }));

vi.mock('../api/writing-assistant-api', async () => {
  const actual = await vi.importActual<
    typeof import('../api/writing-assistant-api')
  >('../api/writing-assistant-api');
  return { ...actual, translateWriting: apiHarness.translateWriting };
});

const SYNC_DEBOUNCE_MS = 1500;

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  apiHarness.translateWriting.mockReset();
});

describe('useSyncedText', () => {
  it('reseeds local text from external source changes when not dirty (generation/sibling sync)', () => {
    const { result, rerender } = renderHook(
      (props: { source: string }) =>
        useSyncedText({
          source: props.source,
          translateTo: null,
          token: 'token',
          workspaceSlug: 'ws',
        }),
      { initialProps: { source: 'first' } },
    );

    expect(result.current.text).toBe('first');
    rerender({ source: 'second' });
    expect(result.current.text).toBe('second');
  });

  it('translates a user edit after the debounce and pushes the result to the sibling', async () => {
    vi.useFakeTimers();
    apiHarness.translateWriting.mockResolvedValue({
      result: 'translated',
    } satisfies WritingResult);
    const onTranslated = vi.fn();

    const { result } = renderHook(() =>
      useSyncedText({
        source: 'orig',
        translateTo: 'ko',
        token: 'token',
        workspaceSlug: 'ws',
        onTranslated,
      }),
    );

    act(() => result.current.edit('user text'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(SYNC_DEBOUNCE_MS);
    });

    expect(apiHarness.translateWriting).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'user text', targetLang: 'ko' }),
    );
    expect(onTranslated).toHaveBeenCalledWith('translated');
  });

  // Regression for MR !43 MERGE_BLOCKED: editing both panels within the debounce
  // window must not let one panel's late-arriving translation clobber the other
  // panel's newer, still-dirty edit.
  it('does not overwrite a dirty panel when the sibling translation arrives (concurrent edit)', async () => {
    vi.useFakeTimers();
    const enToKo = deferred<WritingResult>();
    const koToEn = deferred<WritingResult>();
    apiHarness.translateWriting.mockImplementation(
      (args: { targetLang: string }) =>
        args.targetLang === 'ko' ? enToKo.promise : koToEn.promise,
    );

    // Model the bidirectional EmailAssistantView wiring: the foreign result
    // (translateTo 'ko' → updates the Korean reference) and the Korean reference
    // (translateTo 'en' → updates the foreign result) share parent state.
    const { result } = renderHook(() => {
      const [main, setMain] = useState('EN original');
      const [reference, setReference] = useState('KO original');
      const en = useSyncedText({
        source: main,
        translateTo: 'ko',
        token: 'token',
        workspaceSlug: 'ws',
        onTranslated: setReference,
        onChange: setMain,
      });
      const ko = useSyncedText({
        source: reference,
        translateTo: 'en',
        token: 'token',
        workspaceSlug: 'ws',
        onTranslated: setMain,
        onChange: setReference,
      });
      return { en, ko };
    });

    // User edits the English result, then the Korean reference, both before any
    // translation returns.
    act(() => result.current.en.edit('EN edited'));
    act(() => result.current.ko.edit('KO edited'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SYNC_DEBOUNCE_MS);
    });

    // The English edit's translation (EN→KO) arrives first and tries to update
    // the Korean reference panel — which the user has since edited (dirty).
    await act(async () => {
      enToKo.resolve({ result: 'KO from EN' });
    });

    // The dirty Korean panel keeps the user's edit; it is NOT clobbered.
    expect(result.current.ko.text).toBe('KO edited');

    // Cleanup the other in-flight request.
    await act(async () => {
      koToEn.resolve({ result: 'EN from KO' });
    });
  });
});
