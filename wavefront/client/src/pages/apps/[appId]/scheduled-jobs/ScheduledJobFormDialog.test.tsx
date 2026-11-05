// @vitest-environment jsdom
import { ScheduledJob } from '@app/types/scheduled-job';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ScheduledJobFormDialog from './ScheduledJobFormDialog';
import { buildEmailPayload } from './scheduled-job-utils';

const createMutate = vi.fn();
const updateMutate = vi.fn();

vi.mock('@app/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@app/hooks')>()),
  useGetAllDatasources: () => ({ data: [{ id: 'ds-1', name: 'Warehouse', type: 'postgres' }] }),
  useGetAllDynamicQueries: () => ({ data: [{ file: 'sales.yaml' }, { file: 'refunds.yaml' }], isLoading: false }),
  useGetAppUsers: () => ({
    data: [{ id: 'user-1', email: 'ana@example.com', first_name: 'Ana', last_name: 'Lee', role: 'app_admin' }],
    isLoading: false,
  }),
  useGetEmailConnections: () => ({
    data: [{ id: 'conn-1', name: 'Reports', mailbox_email: 'reports@example.com', status: 'active' }],
  }),
  useCreateScheduledJob: () => ({ mutate: createMutate, isPending: false }),
  useUpdateScheduledJob: () => ({ mutate: updateMutate, isPending: false }),
}));

const payload = buildEmailPayload({
  datasourceId: 'ds-1',
  queryIds: ['sales'],
  recipientUserIds: ['user-1'],
  emailConnectionId: 'conn-1',
  subject: 'Daily sales',
  emailContent: 'Attached are yesterday’s numbers.',
  params: { region: 'eu' },
  filter: "status eq 'paid'",
  limit: 500,
  offset: 0,
});

const job: ScheduledJob = {
  id: 'job-1',
  job_type: 'email_dynamic_query',
  cron_expr: '0 9 * * *',
  timezone: 'Europe/Berlin',
  status: 'active',
  payload: payload as unknown as Record<string, unknown>,
  next_run_at: null,
  last_run_at: null,
  last_error: null,
  retry_count: 0,
  max_retries: 2,
  created_at: null,
  updated_at: null,
};

const renderDialog = (props: Partial<React.ComponentProps<typeof ScheduledJobFormDialog>> = {}) => {
  const onOpenChange = vi.fn();
  render(<ScheduledJobFormDialog isOpen appId="app-1" onOpenChange={onOpenChange} {...props} />);
  return { onOpenChange };
};

describe('ScheduledJobFormDialog', () => {
  beforeEach(() => {
    createMutate.mockReset();
    updateMutate.mockReset();
  });

  it('saves an unchanged job exactly as it was loaded', async () => {
    renderDialog({ job });
    await userEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate.mock.calls[0][0]).toEqual({
      jobId: 'job-1',
      request: { cron_expr: '0 9 * * *', timezone: 'Europe/Berlin', max_retries: 2, payload },
    });
  });

  it('sends an edited subject from the Email tab', async () => {
    renderDialog({ job });
    await userEvent.click(screen.getByRole('tab', { name: 'Email' }));
    const subject = screen.getByDisplayValue('Daily sales');
    await userEvent.clear(subject);
    await userEvent.type(subject, 'Weekly sales');
    await userEvent.click(screen.getByRole('button', { name: 'Update' }));

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate.mock.calls[0][0].request.payload.subject).toBe('Weekly sales');
  });

  it('rejects invalid JSON params and shows where the problem is', async () => {
    renderDialog({ job });
    await userEvent.click(screen.getByRole('button', { name: /Job-level query defaults/ }));
    const params = screen.getByDisplayValue(/"region": "eu"/);
    await userEvent.clear(params);
    // Pasted: userEvent.type reads "[" as the start of a key name
    await userEvent.paste('[1]');
    await userEvent.click(screen.getByRole('button', { name: 'Update' }));

    expect(await screen.findByText('Query params must be a JSON object')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Job setup' })).toHaveAttribute('data-state', 'active');
    expect(updateMutate).not.toHaveBeenCalled();
  });

  it('needs a datasource before a new job can be created', async () => {
    renderDialog();
    await userEvent.click(screen.getByRole('button', { name: 'Create' }));

    expect(await screen.findByText('Datasource is required')).toBeInTheDocument();
    expect(createMutate).not.toHaveBeenCalled();
  });

  it('shows the inline error when the server rejects the save', async () => {
    updateMutate.mockImplementation((_vars, callbacks) => callbacks.onError(new Error('boom')));
    const { onOpenChange } = renderDialog({ job });
    await userEvent.click(screen.getByRole('button', { name: 'Update' }));

    expect(
      await screen.findByText('Unable to save scheduled job. Please verify the details and try again.')
    ).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
