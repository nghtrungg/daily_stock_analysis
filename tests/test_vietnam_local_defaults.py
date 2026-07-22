"""Vietnam-local database and portfolio default contracts."""
from src.core.pipeline import _sanitize_vietnam_history_payload
from src.services.portfolio_service import PortfolioService
from src.storage import (
    IntelligenceItem,
    IntelligenceSource,
    PortfolioAccount,
    PortfolioCashLedger,
    PortfolioCorporateAction,
    PortfolioDailySnapshot,
    PortfolioPosition,
    PortfolioPositionLot,
    PortfolioTrade,
)


def _column_default(model: type, column: str) -> str:
    default = model.__table__.columns[column].default
    assert default is not None
    return str(default.arg)


def test_portfolio_service_defaults_to_vnd() -> None:
    assert PortfolioService._default_currency_for_market("vn") == "VND"


def test_new_database_rows_default_to_vietnam_and_vnd() -> None:
    assert _column_default(IntelligenceSource, "market") == "vn"
    assert _column_default(IntelligenceItem, "market") == "vn"
    assert _column_default(PortfolioAccount, "market") == "vn"
    assert _column_default(PortfolioAccount, "base_currency") == "VND"
    assert _column_default(PortfolioTrade, "market") == "vn"
    assert _column_default(PortfolioTrade, "currency") == "VND"
    assert _column_default(PortfolioCashLedger, "currency") == "VND"
    assert _column_default(PortfolioCorporateAction, "market") == "vn"
    assert _column_default(PortfolioCorporateAction, "currency") == "VND"
    assert _column_default(PortfolioPosition, "market") == "vn"
    assert _column_default(PortfolioPosition, "currency") == "VND"
    assert _column_default(PortfolioPosition, "valuation_currency") == "VND"
    assert _column_default(PortfolioPositionLot, "market") == "vn"
    assert _column_default(PortfolioPositionLot, "currency") == "VND"
    assert _column_default(PortfolioDailySnapshot, "base_currency") == "VND"


def test_vietnam_history_payload_drops_han_and_zero_relevance_news() -> None:
    news = """Results
  1. Unrelated US company
     关联度: macro_market_news; score=0
  2. Vinamilk earnings (VNM)
     Direct company evidence.
     关联度: direct_company_news; score=100
"""
    snapshot = {
        "trend": "弱势多头",
        "summary": "Phục hồi kỹ thuật",
        "nested": {"buy_signal": "买入", "score": 64},
    }

    sanitized_news, sanitized_snapshot = _sanitize_vietnam_history_payload(
        "VNM.VN",
        news,
        snapshot,
    )

    assert sanitized_news is not None
    assert "Unrelated US company" not in sanitized_news
    assert "Vinamilk earnings" in sanitized_news
    assert "关联度" not in sanitized_news
    assert sanitized_snapshot == {
        "summary": "Phục hồi kỹ thuật",
        "nested": {"score": 64},
    }
