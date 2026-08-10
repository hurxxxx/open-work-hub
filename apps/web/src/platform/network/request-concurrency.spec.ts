import { describe, expect, it } from 'vitest';

import { runRequestsWithConcurrency } from './request-concurrency';

describe('runRequestsWithConcurrency', () => {
  it('preserves result order while limiting concurrent work', async () => {
    let activeCount = 0;
    let maxActiveCount = 0;

    const results = await runRequestsWithConcurrency(
      [1, 2, 3, 4, 5],
      2,
      async (item) => {
        activeCount += 1;
        maxActiveCount = Math.max(maxActiveCount, activeCount);
        await new Promise((resolve) =>
          setTimeout(resolve, item === 1 ? 10 : 1),
        );
        activeCount -= 1;
        return item * 10;
      },
    );

    expect(results).toEqual([10, 20, 30, 40, 50]);
    expect(maxActiveCount).toBe(2);
  });

  it('handles empty input', async () => {
    await expect(
      runRequestsWithConcurrency([], 2, async () => 'unused'),
    ).resolves.toEqual([]);
  });
});
