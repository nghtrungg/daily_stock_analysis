import type { PortfolioTransaction } from '../../lib/positions';
import { createSupabaseBrowserClient } from '../../lib/supabase/client';

export type BuyTransactionInput = {
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
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
};

export class PortfolioStoreError extends Error {}

export type PortfolioSnapshot = {
  transactions: PortfolioTransaction[];
  watchlistSymbols: string[];
  analysisRuns: AnalysisRun[];
};

export type PortfolioStore = {
  load: () => Promise<PortfolioSnapshot>;
  addBuyTransaction: (input: BuyTransactionInput) => Promise<void>;
  addWatchlistSymbol: (symbol: string) => Promise<void>;
  requestAnalysis: (symbol: string) => Promise<void>;
};

type TransactionRow = {
  id: string;
  transaction_type: 'buy' | 'sell';
  symbol: string;
  quantity: number | string;
  unit_price_vnd: number | string;
  fee_vnd: number | string;
  occurred_at: string;
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
};

const analysisErrorMessages: Record<string, string> = {
  ACTIVE_RUN_EXISTS: 'Một yêu cầu phân tích cho mã này đang được xử lý.',
  COOLDOWN_ACTIVE: 'Vui lòng chờ một phút trước khi phân tích lại mã này.',
  DISPATCH_FAILED: 'Không thể bắt đầu phân tích. Vui lòng thử lại sau.',
  NOT_WATCHED: 'Hãy thêm mã này vào danh sách theo dõi hoặc danh mục trước khi phân tích.',
  ORIGIN_NOT_ALLOWED: 'Nguồn truy cập ứng dụng không được phép.',
  VALIDATION_ERROR: 'Yêu cầu phân tích không hợp lệ.',
  WORKER_NOT_CONFIGURED: 'Tính năng phân tích đang tạm thời không khả dụng.'
};

const analysisFallback = 'Không thể yêu cầu phân tích. Vui lòng thử lại sau.';

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

function mapTransaction(row: TransactionRow): PortfolioTransaction {
  return {
    id: row.id,
    type: row.transaction_type,
    symbol: row.symbol,
    quantity: Number(row.quantity),
    unitPriceVnd: Number(row.unit_price_vnd),
    feeVnd: Number(row.fee_vnd),
    occurredAt: row.occurred_at
  };
}

function mapAnalysisRun(row: AnalysisRunRow): AnalysisRun {
  return {
    id: row.id,
    symbol: row.symbol,
    status: row.status,
    requestedAt: row.requested_at,
    completedAt: row.completed_at,
    summary: row.summary,
    errorCode: row.error_code
  };
}

export function createSupabasePortfolioStore(): PortfolioStore {
  const supabase = createSupabaseBrowserClient();

  return {
    async load() {
      const [transactionsResult, watchlistResult, analysisResult] = await Promise.all([
        supabase
          .from('portfolio_transactions')
          .select('id, transaction_type, symbol, quantity, unit_price_vnd, fee_vnd, occurred_at')
          .order('occurred_at', { ascending: true }),
        supabase.from('watchlist_symbols').select('symbol').order('created_at', { ascending: true }),
        supabase
          .from('analysis_runs')
          .select('id, symbol, status, requested_at, completed_at, summary, error_code')
          .order('requested_at', { ascending: false })
      ]);

      if (transactionsResult.error || watchlistResult.error || analysisResult.error) {
        throw new PortfolioStoreError('Không thể tải dữ liệu danh mục. Vui lòng làm mới và thử lại.');
      }

      return {
        transactions: ((transactionsResult.data ?? []) as TransactionRow[]).map(mapTransaction),
        watchlistSymbols: ((watchlistResult.data ?? []) as WatchlistRow[]).map((row) => row.symbol),
        analysisRuns: ((analysisResult.data ?? []) as AnalysisRunRow[]).map(mapAnalysisRun)
      };
    },

    async addBuyTransaction(input) {
      const { error } = await supabase.from('portfolio_transactions').insert({
        transaction_type: 'buy',
        symbol: input.symbol,
        quantity: input.quantity,
        unit_price_vnd: input.unitPriceVnd,
        fee_vnd: input.feeVnd,
        occurred_at: new Date().toISOString()
      });

      if (error) {
        throw new PortfolioStoreError('Không thể lưu giao dịch. Vui lòng kiểm tra thông tin và thử lại.');
      }
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
