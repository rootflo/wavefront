import { CURRENT_PATH_KEY, TOKEN_KEY } from '@app/lib/constants';

export const clearSession = () => {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(CURRENT_PATH_KEY);
  } catch {
    // Storage can be blocked; there is then nothing stored to clear.
  }
};
