// @vitest-environment jsdom
import { renderWithClient } from '@app/test/render';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DatasourceOperations from './DatasourceOperations';

// vi.mock factories are hoisted above imports, so the mocks they use are too
const { service, refetchTables } = vi.hoisted(() => ({
  service: { getDatasourceResourceData: vi.fn(), deleteDatasourceResourceRows: vi.fn() },
  refetchTables: vi.fn(),
}));
vi.mock('@app/api', () => ({ default: { datasourcesService: service } }));

vi.mock('@app/hooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@app/hooks')>()),
  useGetDatasourceResources: () => ({ data: ['orders', 'customers'], isLoading: false, refetch: refetchTables }),
}));

const renderPanel = () =>
  renderWithClient(
    <MemoryRouter initialEntries={['/apps/app-1/datasources/ds-1']}>
      <Routes>
        <Route path="/apps/:app/datasources/:datasourceId" element={<DatasourceOperations datasourceId="ds-1" />} />
      </Routes>
    </MemoryRouter>
  );

const pickTable = async (name: string) => {
  // The table picker is the dropdown showing its placeholder; the same words also appear as the run hint
  const picker = screen.getAllByRole('combobox').find((box) => box.textContent?.includes('Pick a table'));
  await userEvent.click(picker!);
  await userEvent.click(await screen.findByRole('option', { name }));
};

describe('DatasourceOperations', () => {
  beforeEach(() => {
    Object.values(service).forEach((fn) => fn.mockReset());
    refetchTables.mockReset();
    // The sample-row read that suggests columns
    service.getDatasourceResourceData.mockResolvedValue({ data: { data: { records: [{ id: 1, status: 'paid' }] } } });
  });

  it('lists the tables', async () => {
    refetchTables.mockResolvedValue({ data: ['orders', 'customers'] });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /List tables.*every table/i }));
    await userEvent.click(screen.getByRole('button', { name: 'List tables' }));

    await waitFor(() => expect(refetchTables).toHaveBeenCalled());
    expect(await screen.findByText('customers')).toBeInTheDocument();
  });

  it('cannot run a query until a table is picked', () => {
    renderPanel();
    expect(screen.getByRole('button', { name: 'Run query' })).toBeDisabled();
  });

  it('queries the picked table with the default page', async () => {
    renderPanel();
    await pickTable('orders');
    service.getDatasourceResourceData.mockClear();
    await userEvent.click(screen.getByRole('button', { name: 'Run query' }));

    await waitFor(() => expect(service.getDatasourceResourceData).toHaveBeenCalled());
    const [datasourceId, table, params] = service.getDatasourceResourceData.mock.calls[0];
    expect([datasourceId, table]).toEqual(['ds-1', 'orders']);
    expect(params).toMatchObject({ limit: 25, offset: 0 });
  });

  it('sends a join from the labelled fields, with help behind their info icons', async () => {
    renderPanel();
    await pickTable('orders');
    await userEvent.click(screen.getByRole('button', { name: /More options/ }));
    await userEvent.type(screen.getByLabelText('Join another table'), 'customers');
    await userEvent.type(screen.getByLabelText('Join on'), 'customer_id');

    await userEvent.hover(screen.getByRole('button', { name: 'About Join on' }));
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Column names only');

    service.getDatasourceResourceData.mockClear();
    await userEvent.click(screen.getByRole('button', { name: 'Run query' }));
    await waitFor(() => expect(service.getDatasourceResourceData).toHaveBeenCalled());
    expect(service.getDatasourceResourceData.mock.calls[0][2]).toMatchObject({
      $expand: 'customers',
      $join: 'customer_id',
    });
  });

  it('asks before deleting, then deletes only the matching rows', async () => {
    service.deleteDatasourceResourceRows.mockResolvedValue({ data: { data: { deleted_rows: 2 } } });
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /Delete rows/i, pressed: false }));
    await pickTable('orders');
    await userEvent.click(screen.getByRole('button', { name: 'Edit as text' }));
    await userEvent.type(screen.getByPlaceholderText("e.g. status eq 'active'"), "status eq 'void'");
    await userEvent.click(screen.getByRole('button', { name: 'Delete rows' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(service.deleteDatasourceResourceRows).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(service.deleteDatasourceResourceRows).toHaveBeenCalledWith('ds-1', 'orders', "status eq 'void'")
    );
    expect(await screen.findByText('Deleted 2 rows')).toBeInTheDocument();
  });
});
