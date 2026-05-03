import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { ImageResultTurn } from './ImageResultTurn';

const baseProps = {
  imageUrl: 'blob:test-image',
  loading: false,
  loadError: null,
  failureReason: null,
  sourceImageUrl: null,
  sourceImageLoadError: null,
  editingImage: false,
  isTemplate: false,
  templateBusy: false,
  onClone: vi.fn(),
  onDiscard: vi.fn(),
  onEditImage: vi.fn(),
  onTemplateToggle: vi.fn(),
};

describe('ImageResultTurn', () => {
  it('does not show the edit prompt while the generated image is still loading', () => {
    render(
      <ImageResultTurn
        {...baseProps}
        imageUrl={null}
        loading
      />,
    );

    expect(screen.queryByLabelText('이미지 수정 요청')).toBeNull();
  });

  it('shows the edit prompt after a generated image is available', () => {
    render(<ImageResultTurn {...baseProps} />);

    expect(screen.getByLabelText('이미지 수정 요청')).toBeTruthy();
  });
});
