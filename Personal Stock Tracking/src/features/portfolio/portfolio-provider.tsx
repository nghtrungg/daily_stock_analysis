'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { derivePositions, type PortfolioTransaction, type Position } from '../../lib/positions';
import { requireVietnamSymbol } from '../../lib/symbols';
import {
  createSupabasePortfolioStore,
  type AnalysisRun,
  type BuyTransactionInput,
  type PortfolioSnapshot,
  type PortfolioStore
} from './portfolio-store';

export type { BuyTransactionInput } from './portfolio-store';

type PortfolioContextValue = {
  positions: Position[];
  totalCostVnd: number;
  transactions: PortfolioTransaction[];
  watchlistSymbols: string[];
  analysisRuns: AnalysisRun[];
  isLoading: boolean;
  isMutating: boolean;
  errorMessage: string | null;
  latestAnalysisFor: (symbol: string) => AnalysisRun | undefined;
  analysisRequestStateFor: (symbol: string) => 'ready' | 'requesting' | 'in-progress' | 'cooldown';
  addBuyTransaction: (input: BuyTransactionInput) => Promise<void>;
  addWatchlistSymbol: (value: string) => Promise<void>;
  requestAnalysis: (symbol: string) => Promise<void>;
};

const emptySnapshot: PortfolioSnapshot = { transactions: [], watchlistSymbols: [], analysisRuns: [] };
const analysisStatusPollIntervalMs = 10_000;
const PortfolioContext = createContext<PortfolioContextValue | null>(null);

function validateTransaction(input: BuyTransactionInput) {
  if (!Number.isFinite(input.quantity) || input.quantity <= 0) {
    throw new Error('Quantity must be greater than zero.');
  }
  if (!Number.isFinite(input.unitPriceVnd) || input.unitPriceVnd <= 0) {
    throw new Error('Unit price must be greater than zero.');
  }
  if (!Number.isFinite(input.feeVnd) || input.feeVnd < 0) {
    throw new Error('Fees cannot be negative.');
  }
}

export function PortfolioProvider({ children, store }: { children: ReactNode; store?: PortfolioStore }) {
  const activeStore = useMemo(() => store ?? createSupabasePortfolioStore(), [store]);
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot>(emptySnapshot);
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
      .catch((error) => {
        if (current) {
          setErrorMessage(error instanceof Error ? error.message : 'Your portfolio data could not be loaded.');
        }
      })
      .finally(() => {
        if (current) {
          setIsLoading(false);
        }
      });

    return () => {
      current = false;
    };
  }, [activeStore]);

  const hasAnalysisInProgress = snapshot.analysisRuns.some(
    (run) => run.status === 'queued' || run.status === 'dispatched' || run.status === 'running'
  );

  useEffect(() => {
    if (!hasAnalysisInProgress) {
      return;
    }

    const interval = window.setInterval(() => {
      void reload().catch(() => {
        // Keep the last known run status visible if a background refresh fails.
      });
    }, analysisStatusPollIntervalMs);

    return () => window.clearInterval(interval);
  }, [hasAnalysisInProgress, reload]);

  const positions = useMemo(() => derivePositions(snapshot.transactions), [snapshot.transactions]);
  const totalCostVnd = positions.reduce((total, position) => total + position.totalCostVnd, 0);

  useEffect(() => {
    const nextCooldownExpiry = snapshot.analysisRuns
      .map((run) => Date.parse(run.requestedAt) + 60_000)
      .filter((expiry) => Number.isFinite(expiry) && expiry > Date.now())
      .sort((left, right) => left - right)[0];

    if (!nextCooldownExpiry) {
      return;
    }

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
      const message = error instanceof Error ? error.message : 'Your change could not be saved.';
      setErrorMessage(message);
      throw new Error(message, { cause: error });
    } finally {
      setIsMutating(false);
    }
  }, [reload]);

  const addBuyTransaction = useCallback(async (input: BuyTransactionInput) => {
    validateTransaction(input);
    const transaction = { ...input, symbol: requireVietnamSymbol(input.symbol) };
    await mutate(() => activeStore.addBuyTransaction(transaction));
  }, [activeStore, mutate]);

  const addWatchlistSymbol = useCallback(async (value: string) => {
    const symbol = requireVietnamSymbol(value);
    await mutate(() => activeStore.addWatchlistSymbol(symbol));
  }, [activeStore, mutate]);

  const requestAnalysis = useCallback(async (value: string) => {
    const symbol = requireVietnamSymbol(value);
    setAnalysisSymbolsBeingRequested((symbols) => [...new Set([...symbols, symbol])]);
    setErrorMessage(null);

    try {
      await activeStore.requestAnalysis(symbol);
      await reload();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Analysis could not be requested.';
      setErrorMessage(message);
      throw new Error(message, { cause: error });
    } finally {
      setAnalysisSymbolsBeingRequested((symbols) => symbols.filter((requestingSymbol) => requestingSymbol !== symbol));
    }
  }, [activeStore, reload]);

  const latestAnalysisFor = useCallback((symbol: string) => snapshot.analysisRuns.find((run) => run.symbol === symbol), [snapshot.analysisRuns]);
  const analysisRequestStateFor = useCallback((symbol: string) => {
    if (analysisSymbolsBeingRequested.includes(symbol)) {
      return 'requesting' as const;
    }

    const run = snapshot.analysisRuns.find((analysisRun) => analysisRun.symbol === symbol);
    if (!run) {
      return 'ready' as const;
    }
    if (run.status === 'queued' || run.status === 'dispatched' || run.status === 'running') {
      return 'in-progress' as const;
    }
    if (Date.parse(run.requestedAt) + 60_000 > analysisClock) {
      return 'cooldown' as const;
    }

    return 'ready' as const;
  }, [analysisClock, analysisSymbolsBeingRequested, snapshot.analysisRuns]);

  return (
    <PortfolioContext.Provider
      value={{
        positions,
        totalCostVnd,
        transactions: snapshot.transactions,
        watchlistSymbols: snapshot.watchlistSymbols,
        analysisRuns: snapshot.analysisRuns,
        isLoading,
        isMutating,
        errorMessage,
        latestAnalysisFor,
        analysisRequestStateFor,
        addBuyTransaction,
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

  if (!portfolio) {
    throw new Error('usePortfolio must be used inside PortfolioProvider.');
  }

  return portfolio;
}
