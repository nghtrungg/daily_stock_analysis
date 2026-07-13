import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { AlertRuleForm } from '../AlertRuleForm';

const { getAccounts } = vi.hoisted(() => ({
  getAccounts: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
  },
}));

describe('AlertRuleForm English Vietnam contract', () => {
  const onSubmit = vi.fn();

  beforeEach(() => {
    onSubmit.mockReset();
    onSubmit.mockResolvedValue(undefined);
    getAccounts.mockReset();
    getAccounts.mockResolvedValue({
      accounts: [{ id: 9, name: 'Vietnam account', market: 'vn', baseCurrency: 'VND', isActive: true }],
    });
  });

  function renderForm() {
    render(
      <UiLanguageProvider lockedLanguage="en">
        <AlertRuleForm onSubmit={onSubmit} />
      </UiLanguageProvider>,
    );
  }

  it('renders the rule editor in English and excludes the legacy market scope', () => {
    renderForm();

    expect(screen.getByRole('heading', { name: 'Create alert rule' })).toBeInTheDocument();
    expect(screen.getByLabelText('Target scope')).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /Market/i })).not.toBeInTheDocument();
    expect(screen.queryByText('创建告警规则')).not.toBeInTheDocument();
  });

  it('normalizes a bare Vietnam ticker in a price-cross rule', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Rule name'), { target: { value: 'Vinamilk price crossing' } });
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'vnm' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '58000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: 'Vinamilk price crossing',
        targetScope: 'single_symbol',
        target: 'VNM.VN',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 58000 },
        severity: 'warning',
        enabled: true,
      });
    });
  });

  it('submits a Vietnam price-change rule', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'FPT.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'price_change_percent' } });
    fireEvent.change(screen.getByLabelText('Direction'), { target: { value: 'down' } });
    fireEvent.change(screen.getByLabelText('Change threshold (%)'), { target: { value: '3.5' } });
    fireEvent.change(screen.getByLabelText('Severity'), { target: { value: 'critical' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'FPT.VN',
        alertType: 'price_change_percent',
        parameters: { direction: 'down', changePct: 3.5 },
        severity: 'critical',
      }));
    });
  });

  it('submits a volume-spike rule and supports disabled creation', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'MBB.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'volume_spike' } });
    fireEvent.change(screen.getByLabelText('Volume multiplier'), { target: { value: '2.5' } });
    fireEvent.click(screen.getByLabelText('Enable immediately'));
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'MBB.VN',
        alertType: 'volume_spike',
        parameters: { multiplier: 2.5 },
        enabled: false,
      }));
    });
  });

  it('submits technical indicator parameters for a Vietnam ticker', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'HPG.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('Cross direction'), { target: { value: 'bearish_cross' } });
    fireEvent.change(screen.getByLabelText('Fast period'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('Slow period'), { target: { value: '13' } });
    fireEvent.change(screen.getByLabelText('Signal period'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'HPG.VN',
        alertType: 'macd_cross',
        parameters: {
          direction: 'bearish_cross',
          fastPeriod: 6,
          slowPeriod: 13,
          signalPeriod: 5,
        },
      }));
    });
  });

  it('rejects an out-of-range RSI threshold before submit', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'SSI.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'rsi_threshold' } });
    fireEvent.change(screen.getByLabelText('RSI threshold'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(screen.getByRole('alert')).toHaveTextContent('RSI threshold must be between 0 and 100');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects indicator history requirements above the supported limit', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'SSI.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('Fast period'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Slow period'), { target: { value: '250' } });
    fireEvent.change(screen.getByLabelText('Signal period'), { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(screen.getByRole('alert')).toHaveTextContent('MACD requires 501 daily bars, up to 365 are supported');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects missing indicator thresholds before submit', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'VCI.VN' } });
    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'rsi_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));
    expect(screen.getByRole('alert')).toHaveTextContent('RSI threshold is required');

    fireEvent.change(screen.getByLabelText('Rule type'), { target: { value: 'cci_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));
    expect(screen.getByRole('alert')).toHaveTextContent('CCI threshold is required');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects foreign stock codes before submit', () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'AAPL.US' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Invalid stock code format');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('submits a watchlist rule without a foreign market selector', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Target scope'), { target: { value: 'watchlist' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '58000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'watchlist',
        target: 'default',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 58000 },
      }));
    });
  });

  it('loads VND accounts and submits a portfolio stop-loss rule', async () => {
    renderForm();

    fireEvent.change(screen.getByLabelText('Target scope'), { target: { value: 'portfolio_account' } });
    await waitFor(() => expect(getAccounts).toHaveBeenCalledWith(false));
    expect(screen.queryByRole('option', { name: 'Price crossing' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Account'), { target: { value: '9' } });
    fireEvent.change(screen.getByLabelText('Stop-loss mode'), { target: { value: 'breach' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'portfolio_account',
        target: '9',
        alertType: 'portfolio_stop_loss',
        parameters: { mode: 'breach' },
      }));
    });
  });

  it('keeps the all-accounts option when account loading fails', async () => {
    getAccounts.mockRejectedValueOnce(new Error('Account provider unavailable'));
    renderForm();

    fireEvent.change(screen.getByLabelText('Target scope'), { target: { value: 'portfolio_holdings' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('Account provider unavailable');
    expect(screen.getByLabelText('Account')).toHaveValue('all');
  });

  it('keeps form values when submit reports failure', async () => {
    onSubmit.mockResolvedValueOnce(false);
    renderForm();

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'VNM.VN' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '58000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(screen.getByLabelText('Symbol')).toHaveValue('VNM.VN');
    expect(screen.getByLabelText('Price threshold')).toHaveValue(58000);
  });
});
