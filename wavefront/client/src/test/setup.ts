// Adds DOM matchers such as toBeInTheDocument to expect. Harmless in the node environment.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => cleanup());
