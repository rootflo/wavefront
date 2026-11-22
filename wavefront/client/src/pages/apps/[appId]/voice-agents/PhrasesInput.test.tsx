// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { PhrasesInput } from './ConversationConfigField';

/** Holds the value as the config form does, so the input re-renders with what it reports. */
const renderTamil = (keepEmpty: boolean, onChange = vi.fn()) => {
  const Harness = () => {
    const [value, setValue] = useState<Record<string, string[]> | undefined>({ ta: ['la'] });
    return (
      <PhrasesInput
        id="words"
        value={value ?? {}}
        builtIn={{ ta: ['la'] }}
        noun={{ one: 'word', many: 'words' }}
        keepEmpty={keepEmpty}
        onChange={(next) => {
          setValue(next);
          onChange(next);
        }}
      />
    );
  };
  render(<Harness />);
  return onChange;
};

describe('PhrasesInput', () => {
  it('keeps an emptied list when empty is a real setting', async () => {
    const onChange = renderTamil(true);

    await userEvent.clear(screen.getByRole('textbox'));

    expect(onChange).toHaveBeenLastCalledWith({ ta: [] });
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', expect.stringContaining('No words'));
  });

  it('drops an emptied list otherwise, so the built-ins apply again', async () => {
    const onChange = renderTamil(false);

    await userEvent.clear(screen.getByRole('textbox'));

    expect(onChange).toHaveBeenLastCalledWith(undefined);
  });

  it('resets a language to the built-ins with the explicit button, even when empty is kept', async () => {
    const onChange = renderTamil(true);

    await userEvent.click(screen.getByRole('button', { name: /remove tamil words/i }));

    expect(onChange).toHaveBeenLastCalledWith(undefined);
  });
});
