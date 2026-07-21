# -*- coding: utf-8 -*-
"""Lazy repository exports.

Keeping package imports lazy lets foundational modules such as ``database`` and
``models`` load without importing the temporary ``src.storage`` facade back
through every domain repository.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "AnalysisRepository",
    "BacktestRepository",
    "DecisionSignalRepository",
    "DecisionSignalOutcomeRepository",
    "StockRepository",
    "SettlementOutcomeRepository",
]

_EXPORT_MODULES = {
    "AnalysisRepository": "analysis_repo",
    "BacktestRepository": "backtest_repo",
    "DecisionSignalRepository": "decision_signal_repo",
    "DecisionSignalOutcomeRepository": "decision_signal_outcome_repo",
    "StockRepository": "stock_repo",
    "SettlementOutcomeRepository": "settlement_outcome_repo",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(f"src.repositories.{module_name}"), name)
