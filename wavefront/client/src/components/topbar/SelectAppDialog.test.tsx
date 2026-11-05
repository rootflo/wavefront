// @vitest-environment jsdom
import { App } from '@app/types/app';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import SelectAppDialog from './SelectAppDialog';

const app = (id: string, app_name: string, public_url: string, status = 'active') =>
  ({ id, app_name, public_url, status, created_at: '2025-01-01T10:00:00Z' }) as unknown as App;

const APPS = [app('2', 'zeta-loans', 'https://zeta.example.com'), app('1', 'alpha-kyc', 'https://kyc.example.com')];

const renderDialog = (onSelect = vi.fn()) => {
  render(<SelectAppDialog open onOpenChange={vi.fn()} apps={APPS} selectedAppId="2" onSelect={onSelect} />);
  return onSelect;
};

const rowNames = () => screen.getAllByRole('listitem').map((item) => item.querySelector('.font-semibold')?.textContent);

describe('SelectAppDialog', () => {
  it('lists apps by name and marks the current one', () => {
    renderDialog();
    expect(screen.getByText('2 apps. You stay on the same section in the one you pick.')).toBeInTheDocument();
    expect(rowNames()).toHaveLength(2);
    expect(screen.getAllByRole('button', { current: true })).toHaveLength(1);
    expect(screen.getByRole('button', { current: true })).toHaveTextContent('zeta.example.com');
  });

  it('selects an app when its row is clicked', async () => {
    const onSelect = renderDialog();
    await userEvent.click(screen.getByRole('button', { name: /kyc\.example\.com/ }));
    expect(onSelect).toHaveBeenCalledWith(APPS[1]);
  });

  it('filters by name or URL and opens the top match on Enter', async () => {
    const onSelect = renderDialog();
    await userEvent.type(screen.getByRole('textbox', { name: 'Search apps' }), 'zeta{Enter}');
    expect(rowNames()).toHaveLength(1);
    expect(onSelect).toHaveBeenCalledWith(APPS[0]);
  });

  it('says when nothing matches', async () => {
    renderDialog();
    await userEvent.type(screen.getByRole('textbox', { name: 'Search apps' }), 'nope');
    expect(screen.getByText('No apps match “nope”.')).toBeInTheDocument();
  });
});
