# -*- coding: utf-8 -*-
"""
===================================
Stock data models
===================================

Defines real-time quote and historical candlestick response models.
"""

from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


class StockQuote(BaseModel):
    """Real-time stock quote."""
    
    stock_code: str = Field(..., description="Stock symbol")
    stock_name: Optional[str] = Field(None, description="Stock name")
    current_price: float = Field(..., description="Current price in the market currency")
    change: Optional[float] = Field(None, description="Price change")
    change_percent: Optional[float] = Field(None, description="Percentage change")
    open: Optional[float] = Field(None, description="Open price")
    high: Optional[float] = Field(None, description="High price")
    low: Optional[float] = Field(None, description="Low price")
    prev_close: Optional[float] = Field(None, description="Previous close")
    volume: Optional[float] = Field(None, description="Trading volume in shares")
    amount: Optional[float] = Field(None, description="Trading value in the market currency")
    update_time: Optional[str] = Field(None, description="Last update time")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "VNM.VN",
            "stock_name": "Vinamilk",
            "current_price": 62000.0,
            "change": 500.0,
            "change_percent": 0.81,
            "open": 61500.0,
            "high": 62500.0,
            "low": 61000.0,
            "prev_close": 61500.0,
            "volume": 10000000,
            "amount": 620000000000,
            "update_time": "2024-01-01T15:00:00"
        }
    })


class KLineData(BaseModel):
    """Candlestick data point."""
    
    date: str = Field(..., description="Date")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    volume: Optional[float] = Field(None, description="Trading volume")
    amount: Optional[float] = Field(None, description="Trading value")
    change_percent: Optional[float] = Field(None, description="Percentage change")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "2024-01-01",
            "open": 61500.0,
            "high": 62500.0,
            "low": 61000.0,
            "close": 62000.0,
            "volume": 10000000,
            "amount": 620000000000,
            "change_percent": 0.81
        }
    })


class ExtractItem(BaseModel):
    """One image-extraction result with symbol, name, and confidence."""

    code: Optional[str] = Field(None, description="Stock symbol; None when extraction failed")
    name: Optional[str] = Field(None, description="Stock name when available")
    confidence: str = Field("medium", description="Confidence: high, medium, or low")


class ExtractFromImageResponse(BaseModel):
    """Image stock-symbol extraction response."""

    codes: List[str] = Field(..., description="Unique extracted stock symbols")
    items: List[ExtractItem] = Field(default_factory=list, description="Detailed extraction results")
    raw_text: Optional[str] = Field(None, description="Raw LLM response for debugging")


class StockHistoryResponse(BaseModel):
    """Historical quote response."""
    
    stock_code: str = Field(..., description="Stock symbol")
    stock_name: Optional[str] = Field(None, description="Stock name")
    period: str = Field(..., description="Candlestick period")
    data: List[KLineData] = Field(default_factory=list, description="Candlestick data")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "VNM.VN",
            "stock_name": "Vinamilk",
            "period": "daily",
            "data": []
        }
    })
