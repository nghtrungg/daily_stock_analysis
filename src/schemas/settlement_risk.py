# -*- coding: utf-8 -*-
"""Schemas for deterministic Vietnam settlement-window risk estimates."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReturnQuantiles(BaseModel):
    """Historical close-to-close return quantiles, expressed as percentages."""

    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


class SettlementRiskEstimate(BaseModel):
    """Versioned heuristic estimate; this is not a future-price probability."""

    model_config = ConfigDict(extra="forbid")

    lookback_sessions: int = Field(ge=1)
    settlement_sessions: int = Field(ge=1)
    two_session_return_quantiles: Optional[ReturnQuantiles] = None
    three_session_return_quantiles: Optional[ReturnQuantiles] = None
    atr_pct: Optional[float] = Field(None, ge=0)
    expected_adverse_move_pct: Optional[float] = Field(None, ge=0)
    expected_favorable_move_pct: Optional[float] = Field(None, ge=0)
    maximum_adverse_excursion_pct: Optional[float] = Field(None, ge=0)
    gap_down_frequency: Optional[float] = Field(None, ge=0, le=1)
    support_buffer_pct: Optional[float] = Field(None, ge=0)
    invalidation_buffer_pct: Optional[float] = Field(None, ge=0)
    historical_invalidation_touch_frequency: Optional[float] = Field(
        None,
        ge=0,
        le=1,
    )
    liquidity_quality: Optional[Literal["good", "limited", "poor"]] = None
    survivability_score: Optional[float] = Field(None, ge=0, le=100)
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    survivability_status: Literal[
        "survivable",
        "caution",
        "unsafe",
        "insufficient_history",
    ]
    sample_count: int = Field(ge=0)
    data_quality: Literal["good", "limited", "insufficient"]
    warnings: List[str] = Field(default_factory=list)
    policy_version: str
    component_weights: Dict[str, float] = Field(default_factory=dict)
