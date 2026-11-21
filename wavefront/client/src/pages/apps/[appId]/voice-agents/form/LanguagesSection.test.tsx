// @vitest-environment jsdom
import { Form } from '@app/components/ui/form';
import { getLanguageDisplayName } from '@app/constants/languages';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { describe, expect, it } from 'vitest';
import LanguagesSection from './LanguagesSection';
import { VoiceAgentInput } from './voice-agent-form';

const CONFIG = JSON.stringify({ language_prompts: { hi: 'Hindi rules' } }, null, 2);

const Harness = () => {
  const form = useForm<VoiceAgentInput>({
    defaultValues: { supported_languages: ['en', 'hi'], default_language: 'en', conversation_config: CONFIG },
  });
  return (
    <Form {...form}>
      <LanguagesSection isEdit={false} />
      <output data-testid="config">{form.watch('conversation_config')}</output>
    </Form>
  );
};

describe('LanguagesSection', () => {
  it("keeps an unchecked language's instructions, so rechecking brings them back", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const hindi = getLanguageDisplayName('hi');
    expect(screen.getByLabelText(`${hindi} instructions`)).toHaveValue('Hindi rules');

    await user.click(screen.getByRole('checkbox', { name: hindi }));
    expect(screen.queryByLabelText(`${hindi} instructions`)).not.toBeInTheDocument();
    expect(screen.getByTestId('config')).toHaveTextContent('Hindi rules');

    await user.click(screen.getByRole('checkbox', { name: hindi }));
    expect(screen.getByLabelText(`${hindi} instructions`)).toHaveValue('Hindi rules');
  });
});
