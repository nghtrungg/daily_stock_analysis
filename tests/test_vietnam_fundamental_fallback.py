from src.services.vietnam_fundamental_fallback import (
    apply_vietnam_fundamental_fallback,
)


def _snapshot(
    *,
    created_at: str,
    pe: float,
    pb: float,
    active_buy: float,
    active_sell: float,
    foreign_net: float | None = None,
):
    foreign_status = "ok" if foreign_net is not None else "not_configured"
    flow = {
        "active_buy_volume": active_buy,
        "active_sell_volume": active_sell,
        "active_net_volume": active_buy - active_sell,
    }
    if foreign_net is not None:
        flow["foreign_net_value"] = foreign_net
    return {
        "created_at": created_at,
        "payload": {
            "valuation": {
                "status": "ok",
                "data": {"pe_ratio": pe, "pb_ratio": pb},
            },
            "capital_flow": {
                "status": "ok",
                "data": {
                    "as_of": created_at,
                    "coverage": {
                        "active_order_flow": "ok",
                        "foreign_flow": foreign_status,
                        "proprietary_flow": "not_configured",
                    },
                    "stock_flow": flow,
                },
            },
        },
    }


def test_vietnam_fallback_averages_distinct_sessions_and_reuses_latest_flow() -> None:
    current = {
        "market": "vn",
        "valuation": {
            "status": "failed",
            "data": {"pe_ratio": None, "pb_ratio": None},
            "source_chain": [],
        },
        "capital_flow": {
            "status": "partial",
            "data": {
                "coverage": {
                    "active_order_flow": "missing",
                    "foreign_flow": "not_configured",
                    "proprietary_flow": "not_configured",
                },
                "stock_flow": {
                    "active_buy_volume": 0,
                    "active_sell_volume": 0,
                },
            },
            "source_chain": [],
        },
        "coverage": {"valuation": "failed", "capital_flow": "partial"},
    }
    snapshots = [
        _snapshot(
            created_at="2026-07-17T15:10:00",
            pe=10,
            pb=2,
            active_buy=700,
            active_sell=200,
            foreign_net=5_000_000,
        ),
        # Same session must not receive a second weight in the five-session mean.
        _snapshot(
            created_at="2026-07-17T09:20:00",
            pe=100,
            pb=20,
            active_buy=1,
            active_sell=1,
        ),
        _snapshot(
            created_at="2026-07-16T15:10:00",
            pe=14,
            pb=4,
            active_buy=400,
            active_sell=300,
        ),
    ]

    result = apply_vietnam_fundamental_fallback(current, snapshots)

    assert result["valuation"]["data"]["pe_ratio"] == 12
    assert result["valuation"]["data"]["pb_ratio"] == 3
    assert result["valuation"]["fallback"]["method"] == "recent_session_average"
    flow_data = result["capital_flow"]["data"]
    assert flow_data["stock_flow"]["active_buy_volume"] == 700
    assert flow_data["stock_flow"]["active_sell_volume"] == 200
    assert flow_data["stock_flow"]["foreign_net_value"] == 5_000_000
    assert flow_data["coverage"]["active_order_flow"] == "fallback"
    assert flow_data["coverage"]["foreign_flow"] == "fallback"
    assert flow_data["fallback_as_of"] == "2026-07-17T15:10:00"


def test_flow_fallback_scans_past_stale_holiday_snapshots() -> None:
    current = {
        "market": "vn",
        "valuation": {"status": "ok", "data": {"pe_ratio": 12, "pb_ratio": 3}},
        "capital_flow": {
            "status": "partial",
            "data": {
                "coverage": {"active_order_flow": "missing"},
                "stock_flow": {},
            },
        },
        "coverage": {"valuation": "ok", "capital_flow": "partial"},
    }
    stale_snapshots = []
    for day in range(17, 12, -1):
        snapshot = _snapshot(
            created_at=f"2026-07-{day:02d}T15:10:00",
            pe=12,
            pb=3,
            active_buy=1,
            active_sell=1,
        )
        snapshot["payload"]["capital_flow"]["data"]["coverage"]["active_order_flow"] = "fallback"
        stale_snapshots.append(snapshot)
    original_trading_session = _snapshot(
        created_at="2026-07-10T15:10:00",
        pe=11,
        pb=2.8,
        active_buy=900,
        active_sell=300,
    )

    result = apply_vietnam_fundamental_fallback(
        current,
        [*stale_snapshots, original_trading_session],
    )

    flow_data = result["capital_flow"]["data"]
    assert flow_data["stock_flow"]["active_buy_volume"] == 900
    assert flow_data["stock_flow"]["active_sell_volume"] == 300
    assert flow_data["fallback_as_of"] == "2026-07-10T15:10:00"
