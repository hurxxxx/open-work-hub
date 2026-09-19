import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(cleanup);
Element.prototype.scrollIntoView = vi.fn();
