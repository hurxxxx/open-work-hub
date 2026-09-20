import { afterEach, expect, it } from 'vitest';
import { consumeOwhSessionHandoff } from './api';

afterEach(() => window.history.replaceState(null, '', '/'));

it('consumes a valid Open Work Hub handoff without retaining it in the URL', () => {
  const code = `cc1_${'a'.repeat(32)}`;
  window.history.replaceState(
    { preserved: true },
    '',
    `/?task=1#${new URLSearchParams({
      owh_issuer: 'https://dev.example.test',
      owh_code: code,
    })}`,
  );

  expect(consumeOwhSessionHandoff()).toEqual({
    issuer: 'https://dev.example.test',
    code,
  });
  expect(window.location.href).toBe('http://localhost:3000/?task=1');
  expect(window.history.state).toEqual({ preserved: true });
});

it('removes an invalid handoff and refuses to exchange it', () => {
  window.history.replaceState(null, '', '/#owh_issuer=x&owh_code=bad');
  expect(consumeOwhSessionHandoff()).toBeNull();
  expect(window.location.hash).toBe('');
});
