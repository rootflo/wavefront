// @vitest-environment jsdom
import { VoiceAgentToolWithAssociation } from '@app/types/tool';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AgentToolContextDialog from './AgentToolContextDialog';

const saveMutate = vi.fn();

vi.mock('@app/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@app/hooks')>()),
  useSetAgentToolOverrides: () => ({ mutate: saveMutate, isPending: false }),
}));

const makeTool = (
  method: 'GET' | 'POST',
  configOverrides?: Record<string, unknown>
): VoiceAgentToolWithAssociation => ({
  id: 'tool-1',
  name: 'get_customer',
  display_name: 'Customer lookup',
  description: 'Looks up the customer',
  tool_type: 'api',
  config: { method, url: 'https://crm.test/customer' },
  parameter_schema: {
    properties: { mobile_number: { type: 'string', description: 'Customer mobile' } },
    required: ['mobile_number'],
  },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_deleted: false,
  association: { id: 'assoc-1', is_enabled: true, priority: 0, config_overrides: configOverrides },
});

const renderDialog = (tool: VoiceAgentToolWithAssociation, onOpenChange = vi.fn()) => {
  render(<AgentToolContextDialog appId="app-1" agentId="agent-1" tool={tool} onOpenChange={onOpenChange} />);
  return onOpenChange;
};

describe('AgentToolContextDialog', () => {
  beforeEach(() => saveMutate.mockReset());

  it('starts with nothing set and explains why it cannot run early', () => {
    renderDialog(makeTool('GET'));

    expect(screen.getByText(/Works as it does today/)).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Look it up as the call starts' })).toBeDisabled();
    expect(screen.getByText(/Still set to the AI: mobile_number/)).toBeInTheDocument();
  });

  it('fills the phone from the call, runs early and keeps other overrides', async () => {
    renderDialog(makeTool('GET', { timeout: 3 }));

    await userEvent.click(screen.getByRole('button', { name: /Use caller's phone number/ }));
    expect(screen.getByText(/The server sends the caller's phone number as "mobile_number"/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('switch', { name: 'Look it up as the call starts' }));
    expect(screen.getByText(/runs as the call starts/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(saveMutate).toHaveBeenCalledWith(
      {
        toolId: 'tool-1',
        configOverrides: { timeout: 3, context: { bind: { mobile_number: 'caller.phone' }, prefetch: true } },
      },
      expect.anything()
    );
  });

  it('needs a write tool marked read-only before it can run early', async () => {
    renderDialog(makeTool('POST', { context: { bind: { mobile_number: 'caller.phone' } } }));
    const prefetch = screen.getByRole('switch', { name: 'Look it up as the call starts' });

    expect(prefetch).toBeDisabled();
    expect(screen.getByText(/sends a POST request/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('switch', { name: 'Only reads data' }));
    expect(prefetch).toBeEnabled();
  });

  it('cancels without saving', async () => {
    const onOpenChange = renderDialog(makeTool('GET'));

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(saveMutate).not.toHaveBeenCalled();
  });
});
