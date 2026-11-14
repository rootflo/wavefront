// @vitest-environment jsdom
import { VoiceAgentService } from '@app/api/voice-agent-service';
import { useNotifyStore } from '@app/store';
import { VoiceAgent } from '@app/types/voice-agent';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OutboundCallDialog from './OutboundCallDialog';

const agent = {
  id: 'agent-1',
  name: 'Water helpline',
  status: 'active',
  outbound_numbers: [],
} as unknown as VoiceAgent;

describe('OutboundCallDialog caller context', () => {
  beforeEach(() => {
    useNotifyStore.getState().reset();
    vi.restoreAllMocks();
  });

  it('sends the typed context with the call', async () => {
    const initiate = vi
      .spyOn(VoiceAgentService.prototype, 'initiateCall')
      .mockResolvedValue({ data: { data: { call: { call_sid: 'CA1' } } } } as never);
    render(<OutboundCallDialog isOpen onOpenChange={vi.fn()} agent={agent} />);

    await userEvent.type(screen.getByLabelText(/To Number/), '+911234567890');
    await userEvent.click(screen.getByRole('button', { name: /Add context/ }));
    await userEvent.type(screen.getByLabelText('Context key 1'), 'reason_for_call');
    await userEvent.type(screen.getByLabelText('Context value 1'), 'overdue bill');
    await userEvent.click(screen.getByRole('button', { name: 'Make Call' }));

    expect(initiate).toHaveBeenCalledWith('agent-1', {
      to_number: '+911234567890',
      context: { reason_for_call: 'overdue bill' },
    });
  });

  it('does not call with an invalid key', async () => {
    const initiate = vi.spyOn(VoiceAgentService.prototype, 'initiateCall');
    render(<OutboundCallDialog isOpen onOpenChange={vi.fn()} agent={agent} />);

    await userEvent.type(screen.getByLabelText(/To Number/), '+911234567890');
    await userEvent.click(screen.getByRole('button', { name: /Add context/ }));
    await userEvent.type(screen.getByLabelText('Context key 1'), 'Reason For Call');
    await userEvent.click(screen.getByRole('button', { name: 'Make Call' }));

    expect(initiate).not.toHaveBeenCalled();
  });
});
