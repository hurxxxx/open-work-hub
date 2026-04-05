import { fireEvent } from '@testing-library/react';
import { render } from '@testing-library/react';

import App from './app';

describe('App', () => {
  it('should render successfully', () => {
    const { baseElement } = render(<App />);
    expect(baseElement).toBeTruthy();
  });

  it('should render the portal heading', () => {
    const { getByText } = render(<App />);
    expect(getByText(/Engineering knowledge workbench/i)).toBeTruthy();
  });

  it('should open the document detail drawer from the shared data table', () => {
    const { getByText, queryByText } = render(<App />);

    expect(queryByText(/citation required/i)).toBeNull();
    fireEvent.click(getByText(/Seal Material Change Notice/i));

    expect(getByText(/citation required/i)).toBeTruthy();
    expect(getByText(/초안에 근거 추가/i)).toBeTruthy();
  });
});
