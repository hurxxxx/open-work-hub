import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PlanChipEditor } from './PlanChipEditor';

describe('PlanChipEditor', () => {
  it('exposes keyboard editing and an accessible remove control', () => {
    const onAdd = vi.fn();
    const onRemove = vi.fn();
    render(
      <PlanChipEditor
        field="keywords_en"
        label="English keywords"
        maxValueChars={256}
        maxValuesPerField={30}
        onAdd={onAdd}
        onRemove={onRemove}
        searchValues={{ source: 'input_derived', values: ['heat exchanger'] }}
      />,
    );

    const input = screen.getByLabelText('English keywords');
    fireEvent.change(input, { target: { value: 'thermal management' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onAdd).toHaveBeenCalledWith('keywords_en', 'thermal management');

    fireEvent.click(screen.getByRole('button', { name: /heat exchanger/i }));
    expect(onRemove).toHaveBeenCalledWith('keywords_en', 'heat exchanger');
  });

  it('does not add a value beyond the configured character limit', () => {
    const onAdd = vi.fn();
    render(
      <PlanChipEditor
        field="keywords_en"
        label="English keywords"
        maxValueChars={256}
        maxValuesPerField={30}
        onAdd={onAdd}
        onRemove={vi.fn()}
        searchValues={{ source: 'input_derived', values: [] }}
      />,
    );

    const input = screen.getByLabelText('English keywords');
    expect((input as HTMLInputElement).maxLength).toBe(256);
    fireEvent.change(input, { target: { value: 'x'.repeat(257) } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onAdd).not.toHaveBeenCalled();
    expect(
      (
        screen.getByRole('button', {
          name: /English keywords/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it('does not add a thirty-first value and displays the configured limit', () => {
    const onAdd = vi.fn();
    render(
      <PlanChipEditor
        field="applicants"
        label="Applicants"
        maxValueChars={256}
        maxValuesPerField={30}
        onAdd={onAdd}
        onRemove={vi.fn()}
        searchValues={{
          source: 'user',
          values: Array.from(
            { length: 30 },
            (_, index) => `Applicant ${index}`,
          ),
        }}
      />,
    );

    const input = screen.getByLabelText('Applicants');
    fireEvent.change(input, { target: { value: 'Applicant 31' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onAdd).not.toHaveBeenCalled();
    expect(screen.getByText(/30 \/ 30/)).toBeTruthy();
  });
});
