// @vitest-environment jsdom
import { getDefaultTtsVoiceId } from '@app/config/tts-voice-catalogs';
import { useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VoiceAgentFormDialog from './VoiceAgentFormDialog';

const createMutate = vi.fn();
const updateMutate = vi.fn();

vi.mock('@app/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@app/hooks')>()),
  useGetLLMConfigs: () => ({ data: [{ id: 'llm-1', display_name: 'GPT', type: 'openai' }] }),
  useGetTtsConfigs: () => ({ data: [{ id: 'tts-1', display_name: 'Deepgram TTS', provider: 'deepgram' }] }),
  useGetSttConfigs: () => ({ data: [{ id: 'stt-1', display_name: 'Sarvam STT', provider: 'sarvam' }] }),
  useGetTelephonyConfigs: () => ({ data: [{ id: 'tel-1', display_name: 'Twilio', provider: 'twilio' }] }),
  useCreateVoiceAgent: () => ({ mutate: createMutate, isPending: false }),
  useUpdateVoiceAgent: () => ({ mutate: updateMutate, isPending: false }),
}));
// The tools tab talks to its own endpoints; it isn't what these tests cover
vi.mock('./VoiceAgentToolsManager', () => ({ default: () => <div>tools manager</div> }));

const voiceId = getDefaultTtsVoiceId('deepgram', undefined) || 'aura-2-thalia-en';

const agent: VoiceAgent = {
  id: 'agent-1',
  name: 'Support line',
  description: 'Answers billing questions',
  status: 'active',
  supported_languages: ['en'],
  default_language: 'en',
  is_deleted: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  llm_config_id: 'llm-1',
  tts_config_id: 'tts-1',
  stt_config_id: 'stt-1',
  telephony_config_id: 'tel-1',
  system_prompt: 'You are helpful.',
  welcome_message: 'Hello!',
  tts_voice_ids: { en: voiceId },
  tts_parameters: { sample_rate: 16000 },
  stt_parameters: null,
  conversation_config: null,
  inbound_numbers: [],
  outbound_numbers: [],
};

const renderDialog = (props: Partial<React.ComponentProps<typeof VoiceAgentFormDialog>> = {}) =>
  render(
    <MemoryRouter>
      <VoiceAgentFormDialog isOpen onOpenChange={vi.fn()} appId="app-1" {...props} />
    </MemoryRouter>
  );

describe('VoiceAgentFormDialog', () => {
  beforeEach(() => {
    createMutate.mockReset();
    updateMutate.mockReset();
    useNotifyStore.getState().reset();
  });

  describe('editing', () => {
    it('saves nothing and says so when nothing changed', async () => {
      renderDialog({ agent });
      await userEvent.click(screen.getByRole('button', { name: 'Update Voice Agent' }));

      await waitFor(() => expect(useNotifyStore.getState().message).toBe('No changes to update'));
      expect(updateMutate).not.toHaveBeenCalled();
    });

    it('sends only the fields that changed', async () => {
      renderDialog({ agent });
      const name = screen.getByDisplayValue('Support line');
      await userEvent.clear(name);
      await userEvent.type(name, 'Billing line');
      await userEvent.click(screen.getByRole('button', { name: 'Update Voice Agent' }));

      await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
      expect(updateMutate.mock.calls[0][0]).toEqual({ agentId: 'agent-1', data: { name: 'Billing line' } });
    });

    it("shows the provider's settings, without a second language control", async () => {
      renderDialog({ agent });
      await userEvent.click(screen.getByRole('tab', { name: 'Configurations' }));

      expect(await screen.findByLabelText('Audio sample rate in Hz')).toHaveValue(16000);
      expect(screen.queryByText(/Language code/)).not.toBeInTheDocument();
    });

    it('leaves a cleared number setting unset instead of saving 0', async () => {
      renderDialog({ agent });
      await userEvent.click(screen.getByRole('tab', { name: 'Configurations' }));
      await userEvent.clear(await screen.findByLabelText('Audio sample rate in Hz'));
      await userEvent.click(screen.getByRole('button', { name: 'Update Voice Agent' }));

      await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
      const { data } = updateMutate.mock.calls[0][0];
      expect(data.tts_parameters?.sample_rate).toBeUndefined();
    });
  });

  describe('creating', () => {
    it('does not submit an incomplete agent, and opens the tab with the first missing field', async () => {
      renderDialog();
      await userEvent.click(screen.getByRole('tab', { name: 'Behavior' }));
      await userEvent.click(screen.getByRole('button', { name: 'Create Voice Agent' }));

      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Basic Info' })).toHaveAttribute('data-state', 'active')
      );
      expect(await screen.findByText('Name is required')).toBeInTheDocument();
      expect(createMutate).not.toHaveBeenCalled();
    });
  });
});
