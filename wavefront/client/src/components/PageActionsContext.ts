import { createContext } from 'react';

/**
 * Lets a layout that owns a page's title offer a slot beside it. A `ListHeader` without a title of its own
 * renders its controls into that slot, so they sit on the title's row like on every other listing page.
 */
export const PageActionsContext = createContext<{ element: HTMLElement | null } | null>(null);
