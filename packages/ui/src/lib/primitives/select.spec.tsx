import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Select } from './select';

describe('Select enterprise styling', () => {
  it('keeps the trigger on the shared compact control chrome', () => {
    render(
      <Select
        onValueChange={() => undefined}
        options={[
          {
            label: 'A deliberately long option label for overflow coverage',
            value: 'long',
          },
        ]}
        value="long"
      />,
    );

    const trigger = screen.getByRole('combobox');
    expect(trigger.className).toContain('h-[var(--ui-density-dense)]');
    expect(trigger.className).toContain('min-w-[148px]');
    expect(trigger.className).toContain('px-2');
    expect(trigger.className).toContain(
      'focus:border-[var(--ui-color-accent)]',
    );
    expect(trigger.firstElementChild?.className).toContain('truncate');
  });
});
