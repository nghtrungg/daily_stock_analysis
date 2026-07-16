'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { CashEntry, LedgerEvent, LedgerTrade, RealizedSale } from '../../lib/ledger';
import { valuePortfolio, type ValuedPosition } from '../../lib/quotes';
import { requireVietnamSymbol } from '../../lib/symbols';
import {
  createEmptyPortfolioSnapshot,
  createSupabasePortfolioStore,
  type AnalysisRun,
  type CashEntryInput,
  type CashEntryUpdateInput,
  type PortfolioSnapshot,
  type PortfolioStore,
  type PortfolioWallet,
  type TradeInput,
  type TradeUpdateInput,
  PortfolioStoreError
} from './portfolio-store';

export type { CashEntryInput, CashEntryUpdateInput, TradeInput, TradeUpdateInput } from './portfolio-store';

export type PortfolioContextValue = {
  wallet: PortfolioWallet;
  positions: ValuedPosition[];
  totalCostVnd: number;
  knownMarketValueVnd: number;
  marketValueVnd: number | null;
  totalAssetsVnd: number | null;
  missingQuoteSymbols: string[];
  isValuationComplete: boolean;
  cashEntries: CashEntry[];
  transactions: LedgerTrade[];
  realizedSales: RealizedSale[];
  ledgerEvents: LedgerEvent[];
  watchlistSymbols: string[];
  analysisRuns: AnalysisRun[];
  isLoading: boolean;
  isMutating: boolean;
  errorMessage: string | null;
  latestAnalysisFor: (symbol: string) => AnalysisRun | undefined;
  analysisRequestStateFor: (symbol: string) => 'ready' | 'requesting' | 'in-progress' | 'cooldown';
  recordCashEntry: (input: CashEntryInput) => Promise<void>;
  updateCashEntry: (input: CashEntryUpdateInput) => Promise<void>;
  deleteCashEntry: (entry: Pick<CashEntry, 'id' | 'updatedAt'>) => Promise<void>;
  recordTrade: (input: TradeInput) => Promise<void>;
  updateTrade: (input: TradeUpdateInput) => Promise<void>;
  deleteTrade: (trade: Pick<LedgerTrade, 'id' | 'updatedAt'>) => Promise<void>;
  addWatchlistSymbol: (value: string) => Promise<void>;
  requestAnalysis: (symbol: string) => Promise<void>;
};

const analysisStatusPollIntervalMs = 10_000;
const PortfolioContext = createContext<PortfolioContextValue | null>(null);

function validateTimestamp(value: string, label: string) {
  if (Number.isNaN(Date.parse(value))) throw new Error(`${label} không hợp lệ.`);
}

function validateVnd(value: number, label: string, allowZero = false) {
  if (!Number.isSafeInteger(value) || (allowZero ? value < 0 : value <= 0)) {
    throw new Error(`${label} phải là số VND ${allowZero ? 'không âm' : 'lớn hơn 0'}.`);
  }
}

function validateCashEntry(input: CashEntryInput) {
  validateVnd(input.amountVnd, 'Số tiền');
  validateTimestamp(input.occurredAt, 'Thời điểm bút toán');
  if (input.note && input.note.trim().length > 500) throw new Error('Ghi chú không được vượt quá 500 ký tự.');
}

function validateTrade(input: TradeInput) {
  if (!Number.isFinite(input.quantity) || input.quantity <= 0) {
    throw new Error('Khối lượng phải lớn hơn 0.');
  }
  const scaledQuantity = input.quantity * 10_000;
  if (Math.abs(Math.round(scaledQuantity) - scaledQuantity) > 1e-8) {
    throw new Error('Khối lượng chỉ được có tối đa 4 chữ số thập phân.');
  }
  validateVnd(input.unitPriceVnd, 'Đơn giá');
  validateVnd(input.feeVnd, 'Phí', true);
  validateVnd(input.taxVnd, 'Thuế', true);
  validateTimestamp(input.occurredAt, 'Thời điểm giao dịch');
}

function requireUserVietnamSymbol(value: string): string {
  try {
    return requireVietnamSymbol(value);
  } catch {
    throw new Error('Mã chứng khoán phải có hậu tố .VN.');
  }
}

function safeStoreMessage(error: unknown, fallback: string): string {
  return error instanceof PortfolioStoreError ? error.message : fallback;
}

export function PortfolioProvider({ children, store }: { children: ReactNode; store?: PortfolioStore }) {
  const activeStore = useMemo(() => store ?? createSupabasePortfolioStore(), [store]);
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot>(() => createEmptyPortfolioSnapshot());
  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [analysisSymbolsBeingRequested, setAnalysisSymbolsBeingRequested] = useState<string[]>([]);
  const [analysisClock, setAnalysisClock] = useState(() => Date.now());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const nextSnapshot = await activeStore.load();
    setSnapshot(nextSnapshot);
  }, [activeStore]);

  useEffect(() => {
    let current = true;

    void activeStore.load()
      .then((nextSnapshot) => {
        if (current) {
          setSnapshot(nextSnapshot);
          setErrorMessage(null);
        }
      })
      .catch(() => {
        if (current) setErrorMessage('Không thể tải dữ liệu danh mục. Vui lòng làm mới và thử lại.');
      })
      .finally(() => {
        if (current) setIsLoading(false);
      });

    return () => {
      current = false;
    };
  }, [activeStore]);

  const hasAnalysisInProgress = snapshot.analysisRuns.some(
    (run) => run.status === 'queued' || run.status === 'dispatched' || run.status === 'running'
  );

  useEffect(() => {
    if (!hasAnalysisInProgress) return;

    const interval = window.setInterval(() => {
      void reload().catch(() => {
        // Preserve the last coherent snapshot when background polling fails.
      });
    }, analysisStatusPollIntervalMs);

    return () => window.clearInterval(interval);
  }, [hasAnalysisInProgress, reload]);

  const valuation = useMemo(
    () => valuePortfolio(snapshot.wallet.availableCashVnd, snapshot.positions, snapshot.latestQuotes),
    [snapshot.latestQuotes, snapshot.positions, snapshot.wallet.availableCashVnd]
  );
  const totalCostVnd = valuation.positions.reduce((total, position) => total + position.totalCostVnd, 0);

  useEffect(() => {
    const nextCooldownExpiry = snapshot.analysisRuns
      .map((run) => Date.parse(run.requestedAt) + 60_000)
      .filter((expiry) => Number.isFinite(expiry) && expiry > Date.now())
      .sort((left, right) => left - right)[0];

    if (!nextCooldownExpiry) return;

    const timeout = window.setTimeout(() => setAnalysisClock(Date.now()), nextCooldownExpiry - Date.now());
    return () => window.clearTimeout(timeout);
  }, [analysisClock, snapshot.analysisRuns]);

  const mutate = useCallback(async (operation: () => Promise<void>) => {
    setIsMutating(true);
    setErrorMessage(null);

    try {
      await operation();
      await reload();
    } catch (error) {
      const message = safeStoreMessage(error, 'Không thể lưu thay đổi. Dữ liệu hiện tại vẫn được giữ nguyên.');
      setErrorMessage(message);
      throw new Error(message, { cause: error });
    } finally {
      setIsMutating(false);
    }
  }, [reload]);

  const recordCashEntry = useCallback(async (input: CashEntryInput) => {
    validateCashEntry(input);
    await mutate(() => activeStore.recordCashEntry({ ...input, note: input.note?.trim() || undefined }));
  }, [activeStore, mutate]);

  const updateCashEntry = useCallback(async (input: CashEntryUpdateInput) => {
    validateCashEntry(input);
    validateTimestamp(input.expectedUpdatedAt, 'Phiên bản bút toán');
    await mutate(() => activeStore.updateCashEntry({ ...input, note: input.note?.trim() || undefined }));
  }, [activeStore, mutate]);

  const deleteCashEntry = useCallback(async (entry: Pick<CashEntry, 'id' | 'updatedAt'>) => {
    validateTimestamp(entry.updatedAt, 'Phiên bản bút toán');
    await mutate(() => activeStore.deleteCashEntry(entry.id, entry.updatedAt));
  }, [activeStore, mutate]);

  const recordTrade = useCallback(async (input: TradeInput) => {
    validateTrade(input);
    const trade = { ...input, symbol: requireUserVietnamSymbol(input.symbol) };
    await mutate(() => activeStore.recordTrade(trade));
  }, [activeStore, mutate]);

  const updateTrade = useCallback(async (input: TradeUpdateInput) => {
    validateTrade(input);
    validateTimestamp(input.expectedUpdatedAt, 'Phiên bản giao dịch');
    const trade = { ...input, symbol: requireUserVietnamSymbol(input.symbol) };
    await mutate(() => activeStore.updateTrade(trade));
  }, [activeStore, mutate]);

  const deleteTrade = useCallback(async (trade: Pick<LedgerTrade, 'id' | 'updatedAt'>) => {
    validateTimestamp(trade.updatedAt, 'Phiên bản giao dịch');
    await mutate(() => activeStore.deleteTrade(trade.id, trade.updatedAt));
  }, [activeStore, mutate]);

  const addWatchlistSymbol = useCallback(async (value: string) => {
    const symbol = requireUserVietnamSymbol(value);
    await mutate(() => activeStore.addWatchlistSymbol(symbol));
  }, [activeStore, mutate]);

  const requestAnalysis = useCallback(async (value: string) => {
    const symbol = requireUserVietnamSymbol(value);
    setAnalysisSymbolsBeingRequested((symbols) => [...new Set([...symbols, symbol])]);
    setErrorMessage(null);

    try {
      await activeStore.requestAnalysis(symbol);
      await reload();
    } catch (error) {
      const message = safeStoreMessage(error, 'Không thể yêu cầu phân tích. Vui lòng thử lại sau.');
      setErrorMessage(message);
      throw new Error(message, { cause: error });
    } finally {
      setAnalysisSymbolsBeingRequested((symbols) => symbols.filter((requestingSymbol) => requestingSymbol !== symbol));
    }
  }, [activeStore, reload]);

  const latestAnalysisFor = useCallback(
    (symbol: string) => snapshot.analysisRuns.find((run) => run.symbol === symbol),
    [snapshot.analysisRuns]
  );
  const analysisRequestStateFor = useCallback((symbol: string) => {
    if (analysisSymbolsBeingRequested.includes(symbol)) return 'requesting' as const;

    const run = snapshot.analysisRuns.find((analysisRun) => analysisRun.symbol === symbol);
    if (!run) return 'ready' as const;
    if (run.status === 'queued' || run.status === 'dispatched' || run.status === 'running') return 'in-progress' as const;
    if (Date.parse(run.requestedAt) + 60_000 > analysisClock) return 'cooldown' as const;
    return 'ready' as const;
  }, [analysisClock, analysisSymbolsBeingRequested, snapshot.analysisRuns]);

  return (
    <PortfolioContext.Provider
      value={{
        wallet: snapshot.wallet,
        positions: valuation.positions,
        totalCostVnd,
        knownMarketValueVnd: valuation.knownMarketValueVnd,
        marketValueVnd: valuation.marketValueVnd,
        totalAssetsVnd: valuation.totalAssetsVnd,
        missingQuoteSymbols: valuation.missingSymbols,
        isValuationComplete: valuation.isComplete,
        cashEntries: snapshot.cashEntries,
        transactions: snapshot.transactions,
        realizedSales: snapshot.realizedSales,
        ledgerEvents: snapshot.ledgerEvents,
        watchlistSymbols: snapshot.watchlistSymbols,
        analysisRuns: snapshot.analysisRuns,
        isLoading,
        isMutating,
        errorMessage,
        latestAnalysisFor,
        analysisRequestStateFor,
        recordCashEntry,
        updateCashEntry,
        deleteCashEntry,
        recordTrade,
        updateTrade,
        deleteTrade,
        addWatchlistSymbol,
        requestAnalysis
      }}
    >
      {children}
    </PortfolioContext.Provider>
  );
}

export function usePortfolio() {
  const portfolio = useContext(PortfolioContext);
  if (!portfolio) throw new Error('usePortfolio must be used inside PortfolioProvider.');
  return portfolio;
}
