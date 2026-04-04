import { render } from '@testing-library/react';

import App from './app';

describe('App', () => {
  it('should render successfully', () => {
    const { baseElement } = render(<App />);
    expect(baseElement).toBeTruthy();
  });

  it('should render the portal heading', () => {
    const { getByText } = render(<App />);
    expect(
      getByText(/근거형 검색과 작업면 중심의 AI 업무 포털/i),
    ).toBeTruthy();
  });
});
