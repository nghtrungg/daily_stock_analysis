import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import AlertsPage from '../AlertsPage';

const {
  listRules,
  createRule,
  deleteRule,
  enableRule,
  disableRule,
  testRule,
  listTriggers,
  listNotifications,
} = vi.hoisted(() => ({
  listRules: vi.fn(),
  createRule: vi.fn(),
  deleteRule: vi.fn(),
  enableRule: vi.fn(),
  disableRule: vi.fn(),
  testRule: vi.fn(),
  listTriggers: vi.fn(),
  listNotifications: vi.fn(),
}));

vi.mock('../../api/alerts', () => ({
  alertsApi: {
    listRules,
    createRule,
    deleteRule,
    enableRule,
    disableRule,
    testRule,
    listTriggers,
    listNotifications,
  },
}));

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts: vi.fn().mockResolvedValue({ accounts: [] }),
  },
}));

const parsedError = {
  title: 'Loading failed',
  message: 'Alert API unavailable',
  rawMessage: 'Alert API unavailable',
  category: 'http_error' as const,
  status: 500,
};

const rule = {
  id: 1,
  name: 'Vinamilk price crossing',
  targetScope: 'single_symbol' as const,
  target: 'VNM.VN',
  alertType: 'price_cross' as const,
  parameters: { direction: 'above' as const, price: 58000 },
  severity: 'warning' as const,
  enabled: true,
  source: 'api',
  createdAt: '2026-05-18T09:00:00',
  updatedAt: '2026-05-18T09:30:00',
};

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function renderPage() {
  return render(
    <UiLanguageProvider lockedLanguage="en">
      <AlertsPage />
    </UiLanguageProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listRules.mockResolvedValue({ items: [rule], total: 1, page: 1, pageSize: 20 });
  listTriggers.mockResolvedValue({
    items: [
      {
        id: 10,
        ruleId: 1,
        target: 'VNM.VN',
        observedValue: 58600,
        threshold: 58000,
        reason: 'VNM.VN price above 58,000 VND',
        dataSource: 'realtime_quote',
        dataTimestamp: '2026-05-18T09:30:00',
        triggeredAt: '2026-05-18T09:30:01',
        status: 'triggered',
      },
    ],
    total: 1,
    page: 1,
    pageSize: 20,
  });
  listNotifications.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
  testRule.mockResolvedValue({
    ruleId: 1,
    status: 'triggered',
    triggered: true,
    observedValue: 58600,
    message: 'VNM.VN price above 58,000 VND',
  });
  createRule.mockResolvedValue(rule);
  disableRule.mockResolvedValue({ ...rule, enabled: false });
  enableRule.mockResolvedValue(rule);
  deleteRule.mockResolvedValue({ deleted: 1 });
});

describe('AlertsPage English Vietnam contract', () => {
  it('loads rules, trigger history, and notification empty state in English', async () => {
    renderPage();

    expect(screen.getByText('Manage event, daily-indicator, watchlist, and portfolio alerts; run one-time tests; and review triggers recorded by background evaluations.')).toBeInTheDocument();
    expect(await screen.findByText('Vinamilk price crossing')).toBeInTheDocument();
    expect(await screen.findByText('VNM.VN price above 58,000 VND')).toBeInTheDocument();
    expect(await screen.findByText('No notification attempts')).toBeInTheDocument();
    expect(listRules).toHaveBeenCalledWith({
      enabled: undefined,
      alertType: undefined,
      page: 1,
      pageSize: 20,
    });
    expect(listTriggers).toHaveBeenCalledWith({ page: 1, pageSize: 20 });
    expect(listNotifications).toHaveBeenCalledWith({ page: 1, pageSize: 20 });
  });

  it('runs a dry-run test and renders only declared response fields', async () => {
    listTriggers.mockResolvedValueOnce({ items: [], total: 0, page: 1, pageSize: 20 });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Test' }));

    await waitFor(() => expect(testRule).toHaveBeenCalledWith(1));
    expect(await screen.findByText('Test result')).toBeInTheDocument();
    expect(screen.getByText(/VNM.VN price above 58,000 VND/)).toBeInTheDocument();
    expect(screen.getByText(/Observed value: 58600/)).toBeInTheDocument();
    expect(screen.queryByText(/realtime_quote/)).not.toBeInTheDocument();
  });

  it('renders batch dry-run summary and Vietnam target results', async () => {
    testRule.mockResolvedValueOnce({
      ruleId: 1,
      targetScope: 'watchlist',
      status: 'triggered',
      triggered: true,
      observedValue: 11,
      message: 'Evaluated 2 targets',
      evaluatedCount: 2,
      triggeredCount: 1,
      degradedCount: 1,
      skippedCount: 0,
      targetResults: [
        {
          target: 'VNM.VN',
          displayTarget: 'Watchlist - VNM.VN',
          status: 'triggered',
          recordStatus: 'triggered',
          triggered: true,
          observedValue: 58600,
          message: 'triggered',
        },
        {
          target: 'FPT.VN',
          displayTarget: 'Watchlist - FPT.VN',
          status: 'not_triggered',
          recordStatus: 'degraded',
          triggered: false,
          observedValue: null,
          message: 'degraded',
        },
      ],
    });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Test' }));

    expect(await screen.findByText(/Evaluated 2 · Triggered 1 · Degraded 1 · Skipped 0/)).toBeInTheDocument();
    expect(screen.getByText('Watchlist - VNM.VN')).toBeInTheDocument();
    expect(screen.getByText(/not_triggered \/ degraded/)).toBeInTheDocument();
  });

  it('creates a Vietnam rule through the page form and reloads rules', async () => {
    renderPage();

    await screen.findByText('Vinamilk price crossing');
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'FPT.VN' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '120000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(createRule).toHaveBeenCalledWith(expect.objectContaining({
        target: 'FPT.VN',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 120000 },
      }));
    });
    expect(await screen.findByText(/Created alert rule/)).toBeInTheDocument();
  });

  it('keeps create form values when create API fails', async () => {
    createRule.mockRejectedValueOnce({ parsedError });
    renderPage();

    await screen.findByText('Vinamilk price crossing');
    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'FPT.VN' } });
    fireEvent.change(screen.getByLabelText('Price threshold'), { target: { value: '120000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(await screen.findByText('Loading failed')).toBeInTheDocument();
    expect(screen.getByLabelText('Symbol')).toHaveValue('FPT.VN');
    expect(screen.getByLabelText('Price threshold')).toHaveValue(120000);
  });

  it('clamps rules pagination when a mutation leaves the current page empty', async () => {
    const page2Rule = { ...rule, id: 2, name: 'Second-page rule', target: 'FPT.VN' };
    listRules
      .mockResolvedValueOnce({ items: [rule], total: 21, page: 1, pageSize: 20 })
      .mockResolvedValueOnce({ items: [page2Rule], total: 21, page: 2, pageSize: 20 })
      .mockResolvedValueOnce({ items: [], total: 20, page: 2, pageSize: 20 })
      .mockResolvedValue({ items: [rule], total: 20, page: 1, pageSize: 20 });

    renderPage();

    expect(await screen.findByText('Vinamilk price crossing')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '2' }));
    expect(await screen.findByText('Second-page rule')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Delete Second-page rule'));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteRule).toHaveBeenCalledWith(2));
    await waitFor(() => {
      expect(listRules).toHaveBeenCalledWith({
        enabled: undefined,
        alertType: undefined,
        page: 1,
        pageSize: 20,
      });
    });
    expect(await screen.findByText('Vinamilk price crossing')).toBeInTheDocument();
  });

  it('keeps the latest rules response when filter requests resolve out of order', async () => {
    const initialRequest = createDeferred<{ items: Array<typeof rule>; total: number; page: number; pageSize: number }>();
    const filteredRequest = createDeferred<{ items: Array<typeof rule>; total: number; page: number; pageSize: number }>();
    const staleRule = { ...rule, id: 3, name: 'Stale filtered rule', enabled: true };
    const filteredRule = { ...rule, id: 4, name: 'Disabled rule', enabled: false };
    listRules
      .mockReset()
      .mockReturnValueOnce(initialRequest.promise)
      .mockReturnValueOnce(filteredRequest.promise);

    renderPage();

    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'disabled' } });
    await waitFor(() => expect(listRules).toHaveBeenCalledTimes(2));

    filteredRequest.resolve({ items: [filteredRule], total: 1, page: 1, pageSize: 20 });
    expect(await screen.findByText('Disabled rule')).toBeInTheDocument();

    initialRequest.resolve({ items: [staleRule], total: 1, page: 1, pageSize: 20 });
    await waitFor(() => expect(screen.queryByText('Stale filtered rule')).not.toBeInTheDocument());
    expect(screen.getByText('Disabled rule')).toBeInTheDocument();
  });

  it('renders API errors through ApiErrorAlert', async () => {
    listRules.mockRejectedValueOnce({ parsedError });

    renderPage();

    expect(await screen.findByText('Loading failed')).toBeInTheDocument();
    expect(screen.getByText('Alert API unavailable')).toBeInTheDocument();
  });
});
