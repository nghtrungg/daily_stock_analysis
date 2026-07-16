import { replayLedger, type CashEntry, type LedgerEvent, type LedgerPosition, type LedgerTrade, type RealizedSale } from '../../lib/ledger';
import type { Quote } from '../../lib/quotes';
import { createSupabaseBrowserClient } from '../../lib/supabase/client';

export type CashEntryInput = {
  type: 'deposit' | 'withdrawal';
  amountVnd: number;
  occurredAt: string;
  note?: string;
};

export type CashEntryUpdateInput = CashEntryInput & {
  id: string;
  expectedUpdatedAt: string;
};

export type TradeInput = {
  type: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
  taxVnd: number;
  occurredAt: string;
};

export type TradeUpdateInput = TradeInput & {
  id: string;
  expectedUpdatedAt: string;
};

export type AnalysisStatus = 'queued' | 'dispatched' | 'running' | 'succeeded' | 'failed';

export type AnalysisRun = {
  id: string;
  symbol: string;
  status: AnalysisStatus;
  requestedAt: string;
  completedAt: string | null;
  summary: string | null;
  errorCode: string | null;
  currentPriceVnd: number | null;
  quoteAsOf: string | null;
  quoteSource: string | null;
};

export type PortfolioWallet = {
  currency: 'VND';
  availableCashVnd: number;
  createdAt: string | null;
  updatedAt: string | null;
};

export class PortfolioStoreError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PortfolioStoreError';
  }
}

export type PortfolioSnapshot = {
  wallet: PortfolioWallet;
  cashEntries: CashEntry[];
  transactions: LedgerTrade[];
  positions: LedgerPosition[];
  realizedSales: RealizedSale[];
  ledgerEvents: LedgerEvent[];
  watchlistSymbols: string[];
  analysisRuns: AnalysisRun[];
  latestQuotes: Record<string, Quote>;
};

export function createEmptyPortfolioSnapshot(): PortfolioSnapshot {
  return {
    wallet: { currency: 'VND', availableCashVnd: 0, createdAt: null, updatedAt: null },
    cashEntries: [],
    transactions: [],
    positions: [],
    realizedSales: [],
    ledgerEvents: [],
    watchlistSymbols: [],
    analysisRuns: [],
    latestQuotes: {}
  };
}

export type PortfolioStore = {
  load: () => Promise<PortfolioSnapshot>;
  recordCashEntry: (input: CashEntryInput) => Promise<void>;
  updateCashEntry: (input: CashEntryUpdateInput) => Promise<void>;
  deleteCashEntry: (id: string, expectedUpdatedAt: string) => Promise<void>;
  recordTrade: (input: TradeInput) => Promise<void>;
  updateTrade: (input: TradeUpdateInput) => Promise<void>;
  deleteTrade: (id: string, expectedUpdatedAt: string) => Promise<void>;
  addWatchlistSymbol: (symbol: string) => Promise<void>;
  requestAnalysis: (symbol: string) => Promise<void>;
};

type WalletRow = {
  currency: string;
  available_cash_vnd: number | string;
  created_at: string;
  updated_at: string;
};

type CashEntryRow = {
  id: string;
  entry_type: CashEntry['type'];
  amount_vnd: number | string;
  note: string | null;
  occurred_at: string;
  created_at: string;
  updated_at: string;
};

type TransactionRow = {
  id: string;
  transaction_type: 'buy' | 'sell';
  symbol: string;
  quantity: number | string;
  unit_price_vnd: number | string;
  fee_vnd: number | string;
  tax_vnd: number | string;
  occurred_at: string;
  created_at: string;
  updated_at: string;
};

type WatchlistRow = { symbol: string };

type AnalysisRunRow = {
  id: string;
  symbol: string;
  status: AnalysisStatus;
  requested_at: string;
  completed_at: string | null;
  summary: string | null;
  error_code: string | null;
  current_price_vnd: number | string | null;
  quote_as_of: string | null;
  quote_source: string | null;
};

const analysisErrorMessages: Record<string, string> = {
  ACTIVE_RUN_EXISTS: 'Một yêu cầu phân tích cho mã này đang được xử lý.',
  CALLBACK_TIMEOUT: 'Lần phân tích trước không phản hồi đúng hạn. Bạn có thể yêu cầu lại.',
  COOLDOWN_ACTIVE: 'Vui lòng chờ một phút trước khi phân tích lại mã này.',
  DISPATCH_FAILED: 'Không thể bắt đầu phân tích. Vui lòng thử lại sau.',
  NOT_WATCHED: 'Hãy thêm mã này vào danh sách theo dõi hoặc danh mục trước khi phân tích.',
  ORIGIN_NOT_ALLOWED: 'Nguồn truy cập ứng dụng không được phép.',
  QUOTE_UNAVAILABLE: 'Phân tích đã chạy nhưng chưa nhận được giá hợp lệ cho mã này.',
  VALIDATION_ERROR: 'Yêu cầu phân tích không hợp lệ.',
  WORKER_NOT_CONFIGURED: 'Tính năng phân tích đang tạm thời không khả dụng.'
};

const financialErrorMessages: Record<string, string> = {
  AUTH_REQUIRED: 'Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.',
  INSUFFICIENT_CASH: 'Số dư ví không đủ cho bút toán này.',
  INSUFFICIENT_SHARES: 'Khối lượng bán vượt quá số cổ phiếu đang nắm giữ tại thời điểm đó.',
  INVALID_CASH_ENTRY: 'Thông tin nạp hoặc rút tiền không hợp lệ.',
  INVALID_TRADE: 'Thông tin giao dịch không hợp lệ.',
  STALE_ENTRY: 'Bút toán đã được thay đổi ở nơi khác. Hãy tải lại trước khi chỉnh sửa.'
};

const analysisFallback = 'Không thể yêu cầu phân tích. Vui lòng thử lại sau.';
const mutationFallback = 'Không thể lưu bút toán. Dữ liệu hiện tại vẫn được giữ nguyên.';

function analysisErrorMessage(code: unknown): string {
  return typeof code === 'string' ? analysisErrorMessages[code] ?? analysisFallback : analysisFallback;
}

async function readFunctionError(error: unknown) {
  if (!error || typeof error !== 'object' || !('context' in error)) {
    return analysisFallback;
  }

  const context = error.context;
  if (!context || typeof context !== 'object' || !('json' in context) || typeof context.json !== 'function') {
    return analysisFallback;
  }

  try {
    const body = await context.json() as { error?: { code?: string } };
    return analysisErrorMessage(body.error?.code);
  } catch {
    return analysisFallback;
  }
}

function financialErrorMessage(error: unknown): string {
  const parts = error && typeof error === 'object'
    ? ['message', 'details', 'hint'].map((key) => key in error ? String((error as Record<string, unknown>)[key] ?? '') : '')
    : [String(error ?? '')];
  const diagnostic = parts.join(' ');
  const code = Object.keys(financialErrorMessages).find((candidate) => diagnostic.includes(candidate));
  return code ? financialErrorMessages[code] : mutationFallback;
}

function finiteNumber(value: number | string, field: string): number {
  const mapped = Number(value);
  if (!Number.isFinite(mapped)) throw new Error(`${field} is not finite`);
  return mapped;
}

function safeInteger(value: number | string, field: string): number {
  const mapped = Number(value);
  if (!Number.isSafeInteger(mapped)) throw new Error(`${field} is outside the supported VND range`);
  return mapped;
}

function mapWallet(row: WalletRow | null): PortfolioWallet {
  if (!row) return createEmptyPortfolioSnapshot().wallet;
  if (row.currency !== 'VND') throw new Error('wallet currency is not VND');
  const availableCashVnd = safeInteger(row.available_cash_vnd, 'available_cash_vnd');
  if (availableCashVnd < 0) throw new Error('wallet balance is negative');
  return { currency: 'VND', availableCashVnd, createdAt: row.created_at, updatedAt: row.updated_at };
}

function mapCashEntry(row: CashEntryRow): CashEntry {
  return {
    id: row.id,
    type: row.entry_type,
    amountVnd: safeInteger(row.amount_vnd, 'amount_vnd'),
    note: row.note ?? undefined,
    occurredAt: row.occurred_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function mapTransaction(row: TransactionRow): LedgerTrade {
  return {
    id: row.id,
    type: row.transaction_type,
    symbol: row.symbol,
    quantity: finiteNumber(row.quantity, 'quantity'),
    unitPriceVnd: safeInteger(row.unit_price_vnd, 'unit_price_vnd'),
    feeVnd: safeInteger(row.fee_vnd, 'fee_vnd'),
    taxVnd: safeInteger(row.tax_vnd, 'tax_vnd'),
    occurredAt: row.occurred_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function mapAnalysisRun(row: AnalysisRunRow): AnalysisRun {
  const price = row.current_price_vnd === null ? null : Number(row.current_price_vnd);
  return {
    id: row.id,
    symbol: row.symbol,
    status: row.status,
    requestedAt: row.requested_at,
    completedAt: row.completed_at,
    summary: row.summary,
    errorCode: row.error_code,
    currentPriceVnd: Number.isSafeInteger(price) && Number(price) > 0 ? Number(price) : null,
    quoteAsOf: row.quote_as_of,
    quoteSource: row.quote_source
  };
}

function latestQuotes(analysisRuns: readonly AnalysisRun[]): Record<string, Quote> {
  const candidates = analysisRuns
    .filter((run) => run.status === 'succeeded'
      && run.currentPriceVnd !== null
      && run.quoteAsOf !== null
      && !Number.isNaN(Date.parse(run.quoteAsOf))
      && run.quoteSource !== null
      && run.quoteSource.trim().length > 0
      && run.quoteSource.length <= 120)
    .sort((left, right) => Date.parse(right.quoteAsOf!) - Date.parse(left.quoteAsOf!)
      || Date.parse(right.completedAt ?? right.requestedAt) - Date.parse(left.completedAt ?? left.requestedAt)
      || Date.parse(right.requestedAt) - Date.parse(left.requestedAt)
      || right.id.localeCompare(left.id));

  return candidates.reduce<Record<string, Quote>>((quotes, run) => {
    if (!quotes[run.symbol]) {
      quotes[run.symbol] = {
        currentPriceVnd: run.currentPriceVnd!,
        asOf: run.quoteAsOf!,
        source: run.quoteSource!.trim()
      };
    }
    return quotes;
  }, {});
}

export function createSupabasePortfolioStore(
  supabase: ReturnType<typeof createSupabaseBrowserClient> = createSupabaseBrowserClient()
): PortfolioStore {

  async function financialRpc(name: string, parameters: Record<string, unknown>) {
    const { error } = await supabase.rpc(name, parameters);
    if (error) throw new PortfolioStoreError(financialErrorMessage(error));
  }

  return {
    async load() {
      const [walletResult, cashResult, transactionsResult, watchlistResult, analysisResult] = await Promise.all([
        supabase
          .from('portfolio_wallets')
          .select('currency, available_cash_vnd, created_at, updated_at')
          .limit(1)
          .maybeSingle(),
        supabase
          .from('portfolio_cash_entries')
          .select('id, entry_type, amount_vnd, note, occurred_at, created_at, updated_at')
          .order('occurred_at', { ascending: true }),
        supabase
          .from('portfolio_transactions')
          .select('id, transaction_type, symbol, quantity, unit_price_vnd, fee_vnd, tax_vnd, occurred_at, created_at, updated_at')
          .order('occurred_at', { ascending: true }),
        supabase.from('watchlist_symbols').select('symbol').order('created_at', { ascending: true }),
        supabase
          .from('analysis_runs')
          .select('id, symbol, status, requested_at, completed_at, summary, error_code, current_price_vnd, quote_as_of, quote_source')
          .order('requested_at', { ascending: false })
      ]);

      if (walletResult.error || cashResult.error || transactionsResult.error || watchlistResult.error || analysisResult.error) {
        throw new PortfolioStoreError('Không thể tải dữ liệu danh mục. Vui lòng làm mới và thử lại.');
      }

      try {
        const wallet = mapWallet((walletResult.data ?? null) as WalletRow | null);
        const cashEntries = ((cashResult.data ?? []) as CashEntryRow[]).map(mapCashEntry);
        const transactions = ((transactionsResult.data ?? []) as TransactionRow[]).map(mapTransaction);
        const ledger = replayLedger(cashEntries, transactions);
        const analysisRuns = ((analysisResult.data ?? []) as AnalysisRunRow[]).map(mapAnalysisRun);

        return {
          wallet,
          cashEntries,
          transactions,
          positions: ledger.positions,
          realizedSales: ledger.realizedSales,
          ledgerEvents: ledger.events,
          watchlistSymbols: ((watchlistResult.data ?? []) as WatchlistRow[]).map((row) => row.symbol),
          analysisRuns,
          latestQuotes: latestQuotes(analysisRuns)
        };
      } catch {
        throw new PortfolioStoreError('Dữ liệu sổ danh mục không hợp lệ. Vui lòng tải lại hoặc liên hệ hỗ trợ.');
      }
    },

    async recordCashEntry(input) {
      await financialRpc('record_cash_entry', {
        p_entry_type: input.type,
        p_amount_vnd: input.amountVnd,
        p_occurred_at: input.occurredAt,
        p_note: input.note?.trim() || null
      });
    },

    async updateCashEntry(input) {
      await financialRpc('update_cash_entry', {
        p_id: input.id,
        p_expected_updated_at: input.expectedUpdatedAt,
        p_entry_type: input.type,
        p_amount_vnd: input.amountVnd,
        p_occurred_at: input.occurredAt,
        p_note: input.note?.trim() || null
      });
    },

    async deleteCashEntry(id, expectedUpdatedAt) {
      await financialRpc('delete_cash_entry', { p_id: id, p_expected_updated_at: expectedUpdatedAt });
    },

    async recordTrade(input) {
      await financialRpc('record_portfolio_trade', {
        p_transaction_type: input.type,
        p_symbol: input.symbol,
        p_quantity: input.quantity,
        p_unit_price_vnd: input.unitPriceVnd,
        p_fee_vnd: input.feeVnd,
        p_tax_vnd: input.taxVnd,
        p_occurred_at: input.occurredAt
      });
    },

    async updateTrade(input) {
      await financialRpc('update_portfolio_trade', {
        p_id: input.id,
        p_expected_updated_at: input.expectedUpdatedAt,
        p_transaction_type: input.type,
        p_symbol: input.symbol,
        p_quantity: input.quantity,
        p_unit_price_vnd: input.unitPriceVnd,
        p_fee_vnd: input.feeVnd,
        p_tax_vnd: input.taxVnd,
        p_occurred_at: input.occurredAt
      });
    },

    async deleteTrade(id, expectedUpdatedAt) {
      await financialRpc('delete_portfolio_trade', { p_id: id, p_expected_updated_at: expectedUpdatedAt });
    },

    async addWatchlistSymbol(symbol) {
      const { error } = await supabase.from('watchlist_symbols').insert({ symbol });

      if (error?.code === '23505') {
        throw new PortfolioStoreError(`${symbol} đã có trong danh sách theo dõi.`);
      }
      if (error) {
        throw new PortfolioStoreError('Không thể lưu mã theo dõi. Vui lòng thử lại sau.');
      }
    },

    async requestAnalysis(symbol) {
      const { data, error } = await supabase.functions.invoke('request-analysis', { body: { symbol } });

      if (error) {
        throw new PortfolioStoreError(await readFunctionError(error));
      }
      if (data && typeof data === 'object' && 'error' in data) {
        const response = data as { error?: { code?: string } };
        throw new PortfolioStoreError(analysisErrorMessage(response.error?.code));
      }
    }
  };
}
